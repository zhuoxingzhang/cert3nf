"""
Recompute the method's run of a session from its log: v5study is run again with a person who gives the logged live
answers in order (each must be asked for the same question as in the session); when the answers run out, a session
that was stopped stops again.  The method is deterministic on one platform, so the output must equal the logged one
(across platforms the certificate may pick another of several equivalent FDs, with the same questions).
Usage:  python replay.py SESSION.jsonl
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as K
import session as S
import v5                         # noqa: E402


class Logged:
    def __init__(self, live):
        self.it = iter(live)

    def ask(self, z, a, k, kind):
        r = next(self.it, None)
        if r is None:
            raise v5.Budget                                    # the session stopped here
        assert tuple(r["key"]) == (z, a), ("replay asks another question than the session", r["qid"])
        return {"yes": True, "no": False, "dk": None}[r["answer"]]


def replay(path):
    recs = S.read(path)
    start = recs[0]
    end = next((r for r in recs if r["event"] == "end"), None)
    live = [r for r in recs if r["event"] == "answer" and r["phase"] == "live"]
    ds = start["relation"]
    _, b, adv = K.prebuilt(ds)
    who = Logged(live)
    out = S.run_method(who, ds, b, adv)
    assert next(who.it, None) is None, "answers left over after the method ended"
    return start, end, out


def main():
    path = sys.argv[1]
    start, end, out = replay(path)
    same = end is not None and end["method"] == json.loads(json.dumps(out))
    print(path, "relation", start["relation"], "questions", out["questions"], "certified", out["certified"],
          "dk", out["dk"], "| the logged output is reproduced" if same else "| DIFFERENT from the logged output")


if __name__ == "__main__":
    main()
