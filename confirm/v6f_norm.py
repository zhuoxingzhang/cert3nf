"""
Design note item 74 (b): Normalize order, Cert3NF with the prior of its advisor replaced by Normalize's score.

The variant v6n|<rules> is v6f.py's v6s|<rules> (statistics only) in every respect but the prior probabilities that its
advisor starts from: Normalize's score (normalize.prior, Papenbrock and Naumann, EDBT 2017, Sec. 7.2) of the extended
FD X -> cl(X) \\ X \\ primary key of every candidate's left-hand side X, clipped as the learned prior is.  The online
calibration, the four rules, the order of the questions, the stopping rule and the certificate stay those of v6f.py,
which this module patches at run time and does not change.  Every other variant runs as in v6f.py, so that a control
run of v6s|<rules> through this module can be compared with the rows of the paper field by field.

Usage (in confirm/), as v6f.py:
  CONFIRM_TRUTH=full CONFIRM_ORACLE=gold CONFIRM_BATCH=3 python v6f_norm.py --answers llm_fresh3_full_q35 \
      --variants 'v6n|lc+hone+kf+rl' --budget 1000 --workers 8 --out v6f_fresh3_extra/normalize/order_full.jsonl
"""
import auto_confirm as C
import bench
import normalize as N
import v6f

v6f.VARIANTS["v6n"] = v6f.VARIANTS["v6s"]
_advisor_for, _one = v6f.advisor_for, v6f.one
_STATE = {"norm": False}


def advisor_for(b, adir, model, llm, lazy):
    if not _STATE["norm"]:
        return _advisor_for(b, adir, model, llm, lazy)
    assert not llm
    pi = bench.clip(N.read_prior(b), lo=C.RHO_MIN)          # written by normalize.py prior from the instance
    return v6f.Advisor(b["P"], pi, None, lazy), "normalize", "none"


def one(args):
    _STATE["norm"] = args[0].partition("|")[0] == "v6n"
    return _one(args)


v6f.advisor_for, v6f.one = advisor_for, one      # v6f.main submits v6f.one; forked workers inherit the patches

if __name__ == "__main__":
    v6f.main()
