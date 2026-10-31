"""
Self-test of session.py and replay.py without a browser.  A scripted participant answers the block from the sure
truth and the live questions from the full truth: exactly, with don't know at random (10%), or with wrong answers at
random (10%, so that questions are asked again at once); then a participant who stops voluntarily after 30 questions,
and one who runs into the time limit.  The answer to a question depends only on (participant, session, qid, mode).

  python test_session.py            every mode on every relation: the session ends, no two answers to the same
                                    question are closer than GAP shown questions, the block comes first, replay
                                    reproduces the method's output; then resume (the session is cut off after k
                                    answers and continued from its file) and six sessions at once, each of which must
                                    equal the same session run alone
  python test_session.py --compare  the sessions of every mode in three processes: the kit (method/ and prebuilt/) with
                                    two hash seeds, and the build (STUDY_SOURCE, objects built from all inputs);
                                    the session files must agree line for line, clocks aside
Session files go to a temporary folder.
"""
import hashlib, json, os, subprocess, sys, tempfile, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as K
import session as S
import replay as RP

CASES = (("E01", 1), ("E01", 2), ("P02", 2))           # R1, R2, R3
MODES = ("exact", "dk", "err", "stop", "time")
CLOCK = {"t_elapsed_s", "t_live_s", "rt_ms", "time", "minutes", "live_minutes_used"}


def open_session(part, sno, out, mode):
    return S.Session(part, sno, out, live_minutes=0.0 if mode == "time" else S.LIVE_MINUTES)


def drive(sess, mode, cut=None):
    """answer until the session ends, or until cut answers have been given (then the session is left as it is)"""
    dk, err = (0.1 if mode in ("dk", "stop") else 0.0), (0.1 if mode == "err" else 0.0)
    stop_after = 30 if mode == "stop" else None
    while True:
        q = sess.question()
        if q.get("done"):
            return True
        if cut is not None and sess.i - 1 >= cut:
            return False
        if stop_after is not None and q["i"] > stop_after:
            sess.stop()
            return True
        cur = sess.cur
        h = int.from_bytes(hashlib.sha256(repr((sess.participant, sess.session_no, q["qid"], mode)).encode())
                           .digest()[:8], "big") / 2 ** 64
        truth = cur["truth_sure"] if cur["phase"] == "block" else cur["truth_full"]
        if cur["phase"] == "live" and h < err:                  # a wrong answer: ties and conflicts, asked again
            truth = not truth
        ans = "dk" if dk > h - err >= 0 and cur["phase"] == "live" else ("yes" if truth else "no")
        sess.answer(q["qid"], ans, 1000)


def run_case(part, sno, out, mode):
    sess = open_session(part, sno, out, mode)
    drive(sess, mode)
    sess.questionnaire({"familiarity": 3, "fatigue": 2, "confidence": 4, "stop_reason": "test"})
    return sess.path


def norm(path):
    """the session file without clocks and resume lines"""
    out = []
    for r in S.read(path):
        if r["event"] == "resume":
            continue
        r = {k: v for k, v in r.items() if k not in CLOCK}
        if r.get("method"):
            r["method"] = {k: v for k, v in r["method"].items() if k != "secs"}
        out.append(r)
    return out


def check(path):
    recs = S.read(path)
    ans = [r for r in recs if r["event"] == "answer"]
    end = [r for r in recs if r["event"] == "end"]
    assert len(end) == 1, "no end line"
    phases = [r["phase"] for r in ans]
    nb = sum(p == "block" for p in phases)
    assert phases[:nb] == ["block"] * nb, "block not first"
    last = {}
    for r in ans:
        k = tuple(r["key"])
        if k in last:
            assert r["i"] - last[k] > S.GAP, ("same question too close", r["qid"])
        last[k] = r["i"]
    return end[0], ans


def modes(tmp):
    for part, sno in CASES:
        for mode in MODES:
            path = run_case(part, sno, os.path.join(tmp, mode), mode)
            end, ans = check(path)
            _, _, o = RP.replay(path)
            same = end["method"] == json.loads(json.dumps(o)) if end["method"] is not None else o["questions"] == 0
            m = end["method"] or {}
            print(f"{part} s{sno} {K.relation_of(part, sno):14s} {mode:5s} shown {len(ans):3d} fillers "
                  f"{end['fillers']:2d} reason {end['stop_reason']:22s} q {m.get('questions')} cert "
                  f"{m.get('certified')} exact {m.get('cert_exact')} dk {m.get('dk')} replay "
                  f"{'ok' if same else 'DIFFERENT'}")
            assert same


def resume(tmp):
    for part, sno in CASES:
        for mode in ("exact", "err", "dk"):
            whole = norm(os.path.join(tmp, mode, f"{part}_s{sno}_{K.relation_of(part, sno)}.jsonl"))
            for cut in (5, 18, 25, 41):
                out = os.path.join(tmp, f"resume_{mode}_{cut}")
                sess = open_session(part, sno, out, mode)
                if drive(sess, mode, cut):                      # ended before the cut
                    sess.questionnaire({"familiarity": 3, "fatigue": 2, "confidence": 4, "stop_reason": "test"})
                else:
                    sess.fh.close()                             # the server dies; the method thread is left behind
                    sess = open_session(part, sno, out, mode)   # and the session continues from its file
                    drive(sess, mode)
                    sess.questionnaire({"familiarity": 3, "fatigue": 2, "confidence": 4, "stop_reason": "test"})
                assert norm(sess.path) == whole, ("resume differs", part, sno, mode, cut)
            print(f"resume {part} s{sno} {mode}: cut after 5, 18, 25, 41 answers, same session")


def parallel(tmp):
    cases = [("E01", 1, "err"), ("P01", 1, "dk"), ("E02", 1, "err"), ("U02", 2, "exact"), ("P03", 1, "err"),
             ("TE03", 2, "dk")]
    alone = {c: norm(run_case(c[0], c[1], os.path.join(tmp, "alone"), c[2])) for c in cases}
    paths, errors = {}, []

    def one(c):
        try:
            paths[c] = run_case(c[0], c[1], os.path.join(tmp, "together"), c[2])
        except Exception as e:                                  # noqa: BLE001
            errors.append((c, repr(e)))

    ts = [threading.Thread(target=one, args=(c,)) for c in cases]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errors, errors
    for c in cases:
        assert norm(paths[c]) == alone[c], ("parallel differs", c)
    print("parallel: six sessions at once equal the same sessions alone")


def dump(out):
    for part, sno in CASES:
        for mode in MODES:
            run_case(part, sno, os.path.join(out, mode), mode)


def compare():
    tmp = tempfile.mkdtemp(prefix="hs_cmp_")
    runs = {"kit seed 1": ({"PYTHONHASHSEED": "1"}, ), "kit seed 2": ({"PYTHONHASHSEED": "2"}, ),
            "build seed 3": ({"PYTHONHASHSEED": "3", "STUDY_BUILD": "1"}, )}
    for name, (env, ) in runs.items():
        e = {**os.environ, **env}
        if "STUDY_BUILD" not in env:
            e.pop("STUDY_BUILD", None)
        subprocess.run([sys.executable, os.path.abspath(__file__), "--dump", os.path.join(tmp, name)], env=e,
                       check=True)
    ref = "kit seed 1"
    n = 0
    for root, _, files in os.walk(os.path.join(tmp, ref)):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), os.path.join(tmp, ref))
            a = norm(os.path.join(tmp, ref, rel))
            for name in runs:
                b = norm(os.path.join(tmp, name, rel))
                if name.startswith("build"):                    # the code md5 names STUDY_SOURCE's files there
                    a0 = [{k: v for k, v in r.items() if k != "code"} for r in a]
                    b = [{k: v for k, v in r.items() if k != "code"} for r in b]
                    assert a0 == b, ("build differs", rel)
                else:
                    assert a == b, (name, "differs", rel)
            n += 1
    print(f"compare: {n} session files agree across {', '.join(runs)}")


def main():
    if "--dump" in sys.argv:
        return dump(sys.argv[sys.argv.index("--dump") + 1])
    if "--compare" in sys.argv:
        return compare()
    tmp = tempfile.mkdtemp(prefix="hs_test_")
    print("session files in", tmp)
    modes(tmp)
    resume(tmp)
    parallel(tmp)


if __name__ == "__main__":
    main()
