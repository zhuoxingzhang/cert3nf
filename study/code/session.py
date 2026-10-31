"""
One session of the human-designer study (README).  First the 18 questions of the fixed block in
the participant's order, then the live session, in which v5study (the tolerant mode of the frozen method) asks and the
participant answers yes, no or don't know, until the method ends, the budget of 100 is used, the live part reaches
its time limit, or the participant stops.  A question that the method asks again is shown only after at least GAP
other questions; filler questions of the same relation fill the gap, and the method never reads their answers.

Every shown question is one line of <participant>_s<n>_<relation>.jsonl, written once it is answered; the line
"event": "end" holds the method's output, and replay.py recomputes it from the answers.  Several sessions run at
once (server.py): each has its own method thread, and the hook v5study.ASK passes a question to the session of the
calling thread.  A session whose file exists continues from it (the server restarted): the method is given the
logged live answers again, must ask the same questions (asserted), and goes on with the next one; the block, the
fillers and both clocks continue where the file ends.  A file with an end line is only completed by the
questionnaire.  Usage: through server.py, or test_session.py.
"""
import hashlib, json, os, queue, sys, threading, time
from collections import deque
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as K

K.setenv("full")
import v5                         # noqa: E402
import v5study                    # noqa: E402

GAP, LIVE_MINUTES = 3, 40
KINDS = {"disc_q": "disc", "max_asked": "max", "guess_q": "guess", "qx_q": "qx", "confirm_q": "confirm",
         "reask_q": "reask"}
VARIANT = K.VARIANT
LOCAL = threading.local()         # LOCAL.session: whom the method of this thread asks


def _ask(z, a, k, kind):
    return LOCAL.session.ask(z, a, k, kind)


def run_method(who, ds, b, adv):
    """v5study's run of a live session on relation ds, asking who.ask"""
    v5study.ASK = _ask
    LOCAL.session = who
    _, eps_m = v5study.VARIANTS[VARIANT]
    return v5study.run(b, adv, v5.CAP, True, True, ds, 0, 0.0, eps_m, False, None, None, True, 0.0)


def seeded(*tag):
    return int.from_bytes(hashlib.sha256(repr(tag).encode()).digest()[:8], "big")


def kit_md5s(ds):
    files = {"v5study.py": os.path.join(K.HERE, "v5study.py"), "session.py": os.path.abspath(__file__),
             "common.py": os.path.join(K.HERE, "common.py"), "v5tol.py": os.path.join(K.CONFIRM, "v5tol.py"),
             "v5.py": os.path.join(K.CONFIRM, "v5.py"), "prebuilt": os.path.join(K.PREBUILT, ds + ".pkl")}
    return {k: K.md5(p) for k, p in files.items()}


def read(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def status(path):
    """new (no file), open (no end line), ended (no questionnaire yet) or closed"""
    if not os.path.exists(path):
        return "new"
    ev = {r["event"] for r in read(path)}
    return "closed" if "questionnaire" in ev else "ended" if "end" in ev else "open"


class Session:
    def __init__(self, participant, session_no, out_dir=None, live_minutes=LIVE_MINUTES, on_write=None):
        self.participant, self.session_no = participant, session_no
        self.condition, _, self.test = K.parse(participant)
        self.ds = K.relation_of(participant, session_no)
        self.rel, self.b, self.adv = K.prebuilt(self.ds)
        with open(os.path.join(K.BLOCKS, f"block_{self.ds}.json"), encoding="utf-8") as fh:
            blk = json.load(fh)
        qs = blk["questions"]
        order = sorted(range(len(qs)), key=lambda j: seeded(participant, session_no, "order", j))
        self.block = [qs[j] for j in order]
        self.block_md5 = K.md5(os.path.join(K.BLOCKS, f"block_{self.ds}.json"))
        self.fillers, self.nfill = blk["fillers"], 0
        out_dir = out_dir or os.path.join(K.KIT, "sessions")
        os.makedirs(out_dir, exist_ok=True)
        self.path = os.path.join(out_dir, f"{participant}_s{session_no}_{self.ds}.jsonl")
        self.on_write = on_write or (lambda path: None)
        self.live_minutes = live_minutes
        self.t0, self.live_t0 = time.time(), None
        self.i, self.recent, self.cur, self.pending = 0, deque(maxlen=GAP), None, None
        self.qin, self.qout, self.preload = queue.Queue(), queue.Queue(), deque()
        self.thread, self.done, self.closed = None, False, False
        self.lock = threading.RLock()
        self.code = kit_md5s(self.ds)
        if os.path.exists(self.path):
            self.resume()
            return
        self.fh = open(self.path, "w", encoding="utf-8")
        self.write({"event": "start", "participant": participant, "condition": self.condition, "test": self.test,
                    "relation": self.ds, "session_no": session_no, "variant": VARIANT, "budget": v5.BUDGET,
                    "live_minutes": live_minutes, "gap": GAP, "block_md5": self.block_md5, "code": self.code,
                    "block_order": [q["id"] for q in self.block], "time": time.strftime("%Y-%m-%d %H:%M:%S")})

    def resume(self):
        recs = read(self.path)
        start = recs[0]
        assert start["event"] == "start" and start["relation"] == self.ds and start["block_md5"] == self.block_md5
        changed = [k for k in ("v5study.py", "v5.py", "prebuilt") if start["code"].get(k) != self.code[k]]
        assert not changed, ("the method changed since the session began", changed)
        ans = [r for r in recs if r["event"] == "answer"]
        self.done = any(r["event"] == "end" for r in recs)
        self.closed = any(r["event"] == "questionnaire" for r in recs)
        self.fh = None if self.closed else open(self.path, "a", encoding="utf-8")
        if self.done:
            return
        nb = sum(r["phase"] == "block" for r in ans)
        assert [r["block_id"] for r in ans[:nb]] == [q["id"] for q in self.block[:nb]], "block order"
        self.block = self.block[nb:]
        self.i, self.nfill = len(ans), sum(r["phase"] == "filler" for r in ans)
        self.recent.extend(tuple(r["key"]) for r in ans[-GAP:])
        self.preload.extend((tuple(r["key"]), r["answer"]) for r in ans if r["phase"] == "live")
        if ans:
            self.t0 = time.time() - ans[-1]["t_elapsed_s"]
            tl = [r["t_live_s"] for r in ans if r["t_live_s"] is not None]
            if tl:
                self.live_t0 = time.time() - tl[-1]
        self.write({"event": "resume", "answers": len(ans), "live_answers": len(self.preload),
                    "time": time.strftime("%Y-%m-%d %H:%M:%S")})

    # ---------------- log ----------------
    def write(self, rec):
        self.fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.fh.flush()
        os.fsync(self.fh.fileno())
        self.on_write(self.path)

    def shown(self, phase, kind, z, a, extra):
        form, listed, rhs, aq, text = self.rel.show(z, a)
        nm = [self.rel.names[i] for i in K.members(z, self.rel.n)]
        self.i += 1
        return {"qid": f"q{self.i:03d}", "i": self.i, "phase": phase, "kind": kind, "lhs": nm, "rhs": rhs,
                "form": form, "listed": listed, "a_q": aq, "text": text, "key": [z, a],
                "truth_full": self.rel.truth(z, a, "full"), "truth_sure": self.rel.truth(z, a, "sure"),
                "truth_supp": self.rel.truth(z, a, "supp"), "holds_on_data": self.rel.holds(z, a), **extra}

    # ---------------- the method ----------------
    def ask(self, z, a, k, kind):
        """the hook of v5study, in the method's thread: a logged answer while resuming, else the participant's"""
        if self.preload:
            key, ans = self.preload.popleft()
            assert key == (z, a), "resume: the method asks another question than the session file"
        else:
            self.qout.put(("q", z, a, k, kind))
            ans = self.qin.get()
        if ans == "stop":
            raise v5.Budget
        return {"yes": True, "no": False, "dk": None}[ans]

    def method(self):
        try:
            self.qout.put(("end", run_method(self, self.ds, self.b, self.adv)))
        except Exception as e:                                # noqa: BLE001 (reported, the session ends)
            self.qout.put(("error", repr(e)))

    def next_method(self):
        """the method's next question, or None once it has ended"""
        if self.pending is None:
            msg = self.qout.get()
            if msg[0] != "q":
                self.finish(msg, "budget or certificate" if msg[0] == "end" else "error")
                return None
            self.pending = msg
        return self.pending

    # ---------------- what the participant sees ----------------
    def progress(self):
        """state for the page: open / ended / closed, and the number of answers so far"""
        return {"state": "closed" if self.closed else "ended" if self.done else "open", "answered": self.i}

    def question(self):
        with self.lock:
            if self.done:
                return {"done": True}
            if self.cur is None:
                self.cur = self.prepare()
            if self.cur is None:
                return {"done": True}
            return {k: self.cur[k] for k in ("qid", "i", "text", "lhs", "rhs", "form", "listed")}

    def prepare(self):
        if self.block:
            q = self.block.pop(0)
            z, a = self.rel.key(q["lhs"], q["rhs"])
            return self.shown("block", "block_" + q["type"], z, a, {"block_id": q["id"]})
        if self.thread is None:
            if self.live_t0 is None:
                self.live_t0 = time.time()
            self.thread = threading.Thread(target=self.method, daemon=True)
            self.thread.start()
        p = self.next_method()
        if p is None:
            return None
        if time.time() - self.live_t0 >= 60 * self.live_minutes:
            return self.stop_method("time")
        _, z, a, k, kind = p
        if (z, a) in self.recent:
            for _ in range(len(self.fillers)):                 # the next filler that is neither this question
                f = self.fillers[self.nfill % len(self.fillers)]   # nor one of the last GAP shown
                self.nfill += 1
                fz, fa = self.rel.key(f["lhs"], f["rhs"])
                if (fz, fa) != (z, a) and (fz, fa) not in self.recent:
                    return self.shown("filler", "filler_" + f["type"], fz, fa, {"filler_id": f["id"]})
        return self.shown("live", KINDS[kind], z, a, {"asked_before": k})

    def answer(self, qid, ans, rt_ms=None):
        assert ans in ("yes", "no", "dk"), ans
        with self.lock:
            if self.done or self.cur is None or qid != self.cur["qid"]:
                return self.question()
            q, self.cur = self.cur, None
            q.update({"answer": ans, "rt_ms": rt_ms, "t_elapsed_s": round(time.time() - self.t0, 1),
                      "t_live_s": None if self.live_t0 is None else round(time.time() - self.live_t0, 1)})
            self.write({"event": "answer", **q})
            self.recent.append(tuple(q["key"]))
            if q["phase"] == "live":
                self.pending = None
                self.qin.put(ans)
            return self.question()

    def practice(self, data):
        with self.lock:
            if not self.closed:
                self.write({"event": "practice", **data})

    def stop(self, reason="voluntary"):
        """the participant stops (or the experimenter ends the session)"""
        with self.lock:
            if self.done:
                return {"done": True}
            self.cur = None
            if self.thread is None:
                self.finish(("end", None), reason)
            else:
                self.stop_method(reason)
            return {"done": True}

    def stop_method(self, reason):
        if self.next_method() is not None:                  # the method waits for an answer
            self.pending = None
            self.qin.put("stop")
            msg = self.qout.get()
            self.finish(msg, reason)
        return None

    def finish(self, msg, reason):
        if self.done:
            return
        self.done = True
        out = msg[1] if msg[0] == "end" else None
        rec = {"event": "end", "stop_reason": reason, "minutes": round((time.time() - self.t0) / 60, 2),
               "live_minutes_used": None if self.live_t0 is None else round((time.time() - self.live_t0) / 60, 2),
               "shown": self.i, "fillers": self.nfill, "method": out}
        if msg[0] == "error":
            rec["error"] = msg[1]
        self.write(rec)

    def questionnaire(self, data):
        with self.lock:
            if self.closed:
                return
            if not self.done:
                self.stop("questionnaire")
            self.write({"event": "questionnaire", **data})
            self.closed = True
            self.fh.close()
