"""
A designer whose errors repeat or correlate, on the frozen v6f.py (design note item 69, the rows "repeated" and phi of Tab. tol).
v6f.py has the independent designer only, and any change to it is a new version.  So this file leaves it untouched and replaces
auto_confirm.designer_flip, through which v6f.run's designer flips an answer, before v6f.main starts its workers:
  --repeated  the k-th answer to a question errs iff the first does (v5tol.py's persistent designer)
  --rho R     item 42 (b): the question has its own error rate eps_q ~ Beta(eps (1-R)/R, (1-eps)(1-R)/R), mean eps, and the k-th
              answer errs when the uniform number of designer_flip is below eps_q
Without either, the rows equal those of v6f.py field by field except secs and the three fields added here.  flip_uniform and
flip_rate are v5tol.py's, verbatim, and scripts/test_v6f_designer.py compares them with the frozen file.  One output file holds one
designer, since v6f.main resumes by a key without rho and repeated.  The workers must fork, since they inherit the replacement.
Usage (in confirm/):
  CONFIRM_ORACLE=gold CONFIRM_TRUTH=full python v6f_designer.py --rho 0.25 --answers A --datasets D --variants V --eps 0.02 --seeds 3 --careful --budget 1000 --workers 4 --out F
"""
import argparse, hashlib, json, multiprocessing, os, sys
import numpy as np
import auto_confirm as C
import v6f

with open(os.path.abspath(__file__), "rb") as _fh:
    CODE = hashlib.md5(_fh.read()).hexdigest()[:12]
FLIP, ONE = C.designer_flip, v6f.one
RHO, REPEATED = 0.0, False


def flip_uniform(ds, seed, p, eps, k=0):
    """the uniform number that auto_confirm.designer_flip compares with eps"""
    h = hashlib.sha256(repr((ds, seed, sorted(p[0]), sorted(p[1]), eps) + ((k,) if k else ())).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2 ** 64


def flip_rate(ds, seed, p, eps, rho):
    """eps_q of the correlated designer (item 42 (b)): Beta with mean eps and correlation rho, seeded by the question"""
    h = hashlib.sha256(repr((ds, seed, sorted(p[0]), sorted(p[1]), eps, "rate")).encode()).digest()
    s = (1 - rho) / rho
    return float(np.random.default_rng(int.from_bytes(h[:8], "big")).beta(eps * s, (1 - eps) * s))


def flip(ds, seed, p, eps, k=0):
    """whether the k-th answer to candidate p is wrong, for this designer"""
    k = 0 if REPEATED else k
    if RHO > 0:
        return flip_uniform(ds, seed, p, eps, k) < flip_rate(ds, seed, p, eps, RHO)
    return FLIP(ds, seed, p, eps, k)


def one(args):
    return {**ONE(args), "rho": RHO, "repeated": REPEATED, "designer_code": CODE}


def main():
    global RHO, REPEATED
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--rho", type=float, default=0.0)
    ap.add_argument("--repeated", action="store_true")
    ap.add_argument("--out", required=True)
    a, rest = ap.parse_known_args()
    assert 0 <= a.rho < 1
    assert multiprocessing.get_start_method() == "fork", "the workers inherit the replacement by forking"
    if os.path.exists(a.out):
        for x in open(a.out, encoding="utf-8"):
            if x.strip():
                r = json.loads(x)
                if (r.get("rho"), r.get("repeated")) != (a.rho, a.repeated):
                    raise SystemExit(f"{a.out} holds rows of another designer: {r.get('rho')}, {r.get('repeated')}")
    RHO, REPEATED = a.rho, a.repeated
    C.designer_flip, v6f.one = flip, one
    sys.argv = [sys.argv[0], "--out", a.out] + rest
    v6f.main()


if __name__ == "__main__":
    main()
