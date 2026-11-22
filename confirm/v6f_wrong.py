"""
Design note item 82 (a): Cert3NF with a wrong advisor.

The variants below are v6f.py's v6s (statistics only) in every respect but the prior probabilities that the advisor
starts from.  The learned prior pi of the relation (auto_confirm.prior_for, kind "learned") is replaced by
  v6i        inverted: 1 - pi, so the advisor believes what the statistics doubt and doubts what they believe;
  v6p0..2    permuted: the values of pi shuffled among the candidates of the relation (seeded by the relation and the
             number), so the advisor keeps the share of likely candidates and knows nothing about which they are;
  v6a        all: 0.98 for every candidate, an advisor that insists on every candidate;
each clipped as the learned prior is.  The online calibration, the latent classes with their starting rate, the four
rules, the order of the questions, the stopping rule and the certificate stay those of v6f.py, which this module patches
at run time and does not change.  The calibration grid of v6f.py has positive slopes only (drd.GRID), so it can flatten a
wrong prior but cannot turn it around.  Every other variant runs as in v6f.py, so that a control run of v6s|<rules>
through this module can be compared with the rows of the paper field by field.

Usage (in confirm/), as v6f.py:
  CONFIRM_TRUTH=full CONFIRM_ORACLE=gold CONFIRM_BATCH=3 python v6f_wrong.py --answers llm_fresh3_full_q35 \
      --variants 'v6i|lc+hone+kf+rl,v6p0|lc+hone+kf+rl' --budget 1000 --workers 8 --out item82/wrong_b3_full.jsonl
  python v6f_wrong.py test        the unit test of the replacement (no relation is read)
"""
import hashlib
import sys

import numpy as np

import auto_confirm as C
import bench
import v6f

KINDS = {"v6i": "inverted", "v6a": "all", "v6p0": "permuted0", "v6p1": "permuted1", "v6p2": "permuted2"}
for _k in KINDS:
    v6f.VARIANTS[_k] = v6f.VARIANTS["v6s"]
_advisor_for, _one = v6f.advisor_for, v6f.one
_STATE = {"kind": None}


def wrong_prior(name, P, pi, kind):
    """the prior of kind for the candidates P of the relation name, from its learned prior pi"""
    if kind == "inverted":
        out = {p: 1.0 - pi[p] for p in P}
    elif kind == "all":
        out = {p: 0.98 for p in P}
    else:
        k = int(kind[len("permuted"):])
        seed = int.from_bytes(hashlib.sha256(repr((name, "permuted", k)).encode()).digest()[:8], "big")
        order = np.random.default_rng(seed).permutation(len(P)).tolist()
        out = {p: pi[P[j]] for p, j in zip(P, order)}
    return bench.clip(out, lo=C.RHO_MIN)


def advisor_for(b, adir, model, llm, lazy):
    kind = _STATE["kind"]
    if kind is None:
        return _advisor_for(b, adir, model, llm, lazy)
    assert not llm
    pi = wrong_prior(b["name"], b["P"], C.prior_for(b, "learned", adir, model), kind)
    return v6f.Advisor(b["P"], pi, None, lazy), kind, "none"


def one(args):
    _STATE["kind"] = KINDS.get(args[0].partition("|")[0])
    return _one(args)


def test():
    rng = np.random.default_rng(0)
    P = [((i,), (99,)) for i in range(200)]
    pi = bench.clip({p: float(v) for p, v in zip(P, rng.beta(0.3, 3.0, len(P)))}, lo=C.RHO_MIN)
    inv = wrong_prior("r", P, pi, "inverted")
    assert all(abs(inv[p] - min(0.98, max(C.RHO_MIN, 1 - pi[p]))) < 1e-15 for p in P)
    seq = [inv[p] for p in sorted(P, key=lambda p: pi[p])]
    assert all(x >= y for x, y in zip(seq, seq[1:])) and seq[0] > seq[-1], "the inverted prior ranks the candidates in the opposite order"
    assert set(wrong_prior("r", P, pi, "all").values()) == {0.98}
    perms = [wrong_prior("r", P, pi, f"permuted{k}") for k in range(3)]
    for q in perms:
        assert sorted(q.values()) == sorted(pi.values()), "a permutation keeps the values"
        assert sum(q[p] != pi[p] for p in P) > len(P) // 2, "a permutation moves most values"
    assert perms[0] != perms[1] != perms[2] != perms[0], "the three permutations differ"
    assert wrong_prior("r", P, pi, "permuted0") == perms[0], "a permutation is a function of the relation and its number"
    assert wrong_prior("s", P, pi, "permuted0") != perms[0], "another relation gets another permutation"
    assert all(v6f.VARIANTS[k] == v6f.VARIANTS["v6s"] for k in KINDS)
    print("v6f_wrong: unit test passed")


v6f.advisor_for, v6f.one = advisor_for, one      # v6f.main submits v6f.one; forked workers inherit the patches

if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        test()
    else:
        v6f.main()
