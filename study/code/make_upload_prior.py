"""
The learned prior of an uploaded table (upload.py): the logistic regression of bench.estimate (kind "learned", the
seven data features of a candidate) fitted on every relation of the training pool, which each relation of the paper
uses with itself left out; an upload is none of them, so it uses all of them.  Checks on one pool relation that the
weights fitted without it give the method's own prior (auto_confirm.prior), then writes prebuilt/upload_prior.json.
Usage:  python study/code/make_upload_prior.py
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as K

K.setenv("full")
import auto_common as AC          # noqa: E402
import auto_confirm as C          # noqa: E402
import bench                      # noqa: E402

COLS = list(range(7))


def weights(train):
    ys = [p in set(b["truth"]) for b in train for p in b["P"]]
    return bench.fit_logistic([[b["X"][p][c] for c in COLS] for b in train for p in b["P"]], ys)


def prior(w, b):
    return bench.clip({p: float(1 / (1 + np.exp(-np.dot(w, [b["X"][p][c] for c in COLS])))) for p in b["P"]},
                      lo=C.RHO_MIN)


def main():
    bs = C.benches()
    pool = AC.pool()
    probe = pool[0]
    want = C.prior(bs[probe], "learned")
    got = prior(weights([bs[d] for d in pool if d != probe]), bs[probe])
    assert max(abs(want[p] - got[p]) for p in want) < 1e-12, "the refit differs from auto_confirm.prior"
    w = weights([bs[d] for d in pool])
    out = {"pool": pool, "columns": COLS, "weights": [float(x) for x in w], "rho_min": C.RHO_MIN,
           "check": f"leaving out {probe} reproduces auto_confirm.prior(kind learned)"}
    with open(os.path.join(K.PREBUILT, "upload_prior.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print("pool", len(pool), "relations; weights", np.round(w, 3).tolist())


if __name__ == "__main__":
    main()
