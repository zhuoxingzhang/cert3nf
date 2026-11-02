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

A demo session (a try from the start page, now that the study has ended) skips the block, runs the method in the
trusting mode (variant v5: every premise asked once, so no fillers are needed) and ends with result() instead of the
questionnaire: the method's output, the design of the confirmed FDs, and the answers that differ from the documented
FDs.  A session on an uploaded table (upload.py) is a demo session with the statistics advisor (variant v5s) and no
documented FDs.
"""
import hashlib, itertools, json, os, queue, sys, threading, time
from collections import deque
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as K

K.setenv("full")
import auto_common as AC          # noqa: E402
import drd                        # noqa: E402
import v5                         # noqa: E402
import v5study                    # noqa: E402
import upload as U                # noqa: E402

GAP, LIVE_MINUTES = 3, 40
KINDS = {"disc_q": "disc", "max_asked": "max", "guess_q": "guess", "qx_q": "qx", "confirm_q": "confirm",
         "reask_q": "reask"}
VARIANT = K.VARIANT
DEMO_VARIANT = "v5"               # the trusting mode with the same advisor, for demo sessions
UPLOAD_VARIANT = "v5s"            # the trusting mode with the statistics advisor, for an uploaded table
LOCAL = threading.local()         # LOCAL.session: whom the method of this thread asks


def _ask(z, a, k, kind):
    return LOCAL.session.ask(z, a, k, kind)


def run_method(who, ds, b, adv, variant=VARIANT):
    """v5study's run of a live session on relation ds, asking who.ask"""
    v5study.ASK = _ask
    LOCAL.session = who
    _, eps_m = v5study.VARIANTS[variant]
    return v5study.run(b, adv, v5.CAP, True, True, ds, 0, 0.0, eps_m, False, None, None, True, 0.0)


def seeded(*tag):
    return int.from_bytes(hashlib.sha256(repr(tag).encode()).digest()[:8], "big")


def kit_md5s(ds, upload=None):
    files = {"v5study.py": os.path.join(K.HERE, "v5study.py"), "session.py": os.path.abspath(__file__),
             "common.py": os.path.join(K.HERE, "common.py"), "v5tol.py": os.path.join(K.CONFIRM, "v5tol.py"),
             "v5.py": os.path.join(K.CONFIRM, "v5.py"),
             "prebuilt": os.path.join(upload, "block.pkl") if upload else os.path.join(K.PREBUILT, ds + ".pkl")}
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
    def __init__(self, participant, session_no, out_dir=None, live_minutes=LIVE_MINUTES, on_write=None, demo=False,
                 upload=None):
        self.participant, self.session_no, self.upload = participant, session_no, upload
        self.demo = demo or upload is not None
        if upload:                                       # an uploaded table (upload.py): the statistics advisor
            self.variant, self.condition, self.test, self.ds = UPLOAD_VARIANT, None, True, "upload"
            self.rel, self.b, self.adv, self.info = U.load(upload)
            blk, self.block_md5 = {"questions": [], "fillers": []}, K.md5(os.path.join(upload, "block.pkl"))
        else:
            self.variant = DEMO_VARIANT if demo else VARIANT
            self.condition, _, self.test = K.parse(participant)
            self.ds = K.relation_of(participant, session_no)
            self.rel, self.b, self.adv = K.prebuilt(self.ds)
            self.info = None
            with open(os.path.join(K.BLOCKS, f"block_{self.ds}.json"), encoding="utf-8") as fh:
                blk = json.load(fh)
            self.block_md5 = K.md5(os.path.join(K.BLOCKS, f"block_{self.ds}.json"))
        qs = blk["questions"]
        order = sorted(range(len(qs)), key=lambda j: seeded(participant, session_no, "order", j))
        self.block = [] if self.demo else [qs[j] for j in order]
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
        self.ended_result = None                               # result() of the ended session, computed once
        self.code = kit_md5s(self.ds, upload)
        if os.path.exists(self.path):
            self.resume()
            return
        self.fh = open(self.path, "w", encoding="utf-8")
        self.write({"event": "start", "participant": participant, "condition": self.condition, "test": self.test,
                    "relation": self.ds, "session_no": session_no, "variant": self.variant, "demo": self.demo,
                    "budget": v5.BUDGET,
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
            self.qout.put(("end", run_method(self, self.ds, self.b, self.adv, self.variant)))
        except Exception as e:                                # noqa: BLE001 (reported, the session ends)
            self.qout.put(("error", repr(e)))
        finally:
            if self.upload:                                   # judge() caches by relation name: keep no upload
                for tag in ("reach", "gold"):
                    v5study.C._SA.pop((self.b["name"], tag), None)

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
            keys = ("qid", "i", "text", "lhs", "rhs", "form", "listed") + (("kind",) if self.demo else ())
            return {k: self.cur[k] for k in keys}

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

    # ---------------- the end of a demo session ----------------
    def result(self):
        """what a demo session shows at its end: the counts, the method's verdict, the design that 3NF synthesis
        returns on sigma0 and the confirmed FDs (as in v5study's output, with a minimal key per schema and the
        schemata of equivalent keys merged), its check against the documented FDs, and the answers that differ from them;
        for an uploaded table, the check against the confirmed FDs and the SQL types of the columns; every schema lists
        its other minimal keys, which the SQL declares UNIQUE; computed once, when the session has ended"""
        with self.lock:
            if not self.done:
                return {"done": False}
            if self.ended_result is not None:
                return self.ended_result
            recs = read(self.path)
        res = self.compute_result(recs)
        with self.lock:
            self.ended_result = res
        return res

    def compute_result(self, recs):
        ans = [r for r in recs if r["event"] == "answer"]
        end = next((r for r in recs if r["event"] == "end"), {})
        out = end.get("method")
        res = {"done": True, "answers": len(ans), "stop_reason": end.get("stop_reason"),
               **{k: sum(r["answer"] == k for r in ans) for k in ("yes", "no", "dk")}}
        res["differ"] = [{"text": r["text"], "answer": r["answer"], "documented": "yes" if r["truth_full"] else "no"}
                         for r in ans if r["answer"] != "dk" and r["truth_full"] is not None
                         and (r["answer"] == "yes") != r["truth_full"]]
        res["documented"] = not self.upload
        if not out:
            return res
        names, n, b = self.rel.names, self.rel.n, self.b
        idx = {x: i for i, x in enumerate(names)}
        yes = [AC.S.fd(tuple(sorted(idx[x] for x in l)), idx[a]) for l, a in out["certificate"]["yes"]]
        inst = drd.Instance(b["R"], b["sigma0"], b["P"], {p: 0.5 for p in b["P"]}, list(b["truth"]), name=b["name"])
        D = inst._synth(inst._atomic(b["sigma0"] + yes))[0]
        F = [(K.mask(l), K.mask(r)) for l, r in b["sigma0"] + yes]

        sa = drd.E2.atomic_closure(b["R"], b["sigma0"] + yes)
        memo = {}

        def keys(s):                                            # the minimal keys of schema s under the confirmed FDs
            s = frozenset(s)                                    # (Lucchesi and Osborn), smallest first
            if s not in memo:
                memo[s] = sorted((sorted(k) for k in AC.S.B.minimal_keys(s, AC.S.proj(sa, s))),
                                 key=lambda k: (len(k), k))
            return memo[s]

        def key(s):                                             # a smallest one
            return keys(s)[0]

        # the synthesis keeps one schema per atomic FD; for display, schemata whose smallest keys determine each other
        # (as in Bernstein's synthesis) are merged where the merged schema stays in 3NF under the confirmed FDs, and the
        # checks are redone on that design
        groups = {}
        for s in D:
            groups.setdefault(K.closure(K.mask(key(s)), F), []).append(s)
        M = []
        for g in groups.values():
            u = frozenset().union(*g)
            M.extend([u] if len(g) > 1 and AC.S.is_3nf(u, AC.S.proj(sa, u)) else g)
        M = [s for s in M if not any(s < t for t in M)]
        # checked against the documented FDs, as in judge(); an uploaded table has none, so against the confirmed ones
        gold = sa if self.upload else drd.E2.atomic_closure(b["R"], b["sigma0"] + b["gold"])
        m = AC.S.metrics(b["R"], [list(s) for s in M], gold, gold)
        design = []
        for s in sorted(M, key=lambda s: (-len(s), sorted(s))):
            k = key(s)
            design.append({"key": [names[i] for i in k], "other": [names[i] for i in sorted(s) if i not in k],
                           "unique": [[names[i] for i in c] for c in keys(s) if c != k]})
        res.update({"certified": out["certified"], "asked": out["questions"], "by_data": out["data_no"],
                    "confirmed": [[l, a] for l, a in out["certificate"]["yes"]], "design": design,
                    "lossless": m["lossless"], "preserving": m["u_str"] == 0, "nf3": m["nf3"]})
        res["types"] = (self.info["types"] if self.upload else      # a try's relation: the types of its sample rows
                        {a: U.sqltype([r[j] for r in self.rel.sample]) for j, a in enumerate(names)})
        return res
