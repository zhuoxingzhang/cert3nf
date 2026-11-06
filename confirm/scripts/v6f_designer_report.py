"""Report of design note item 69 (c): v6f careful under a designer whose errors repeat or correlate per question, against
the independent designer (rho = 0, the err rows), with the cells of rho42_report.py.  Per set, truth, designer and eps:
runs, certified, wrong certificates, their share among certified and among all runs, the mean number Q of different
questions, the bound of Prop. err, the median of the questions, the runs with a good design on gold, and the same count
of certificates within 100 questions.
Usage:  python v6f_designer_report.py DEV_DIR B2_DIR B3_ERR_DIR B3_DESIGNER_DIR
(the result directories of the development relations, of batch 2 and of batch 3; the output is v6f_fresh3_extra/designer69/report.txt)"""
import json, os, statistics, sys
from collections import defaultdict

C = "e2a6af907596"
MAIN = "v6s|lc+hone+kf+rl"
DEV, B2, B3E, B3D = sys.argv[1:5]
RUNS = {"dev": 23 * 3, "b2": 12 * 3, "b3": 23 * 3}


def load(f):
    with open(f, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def premise(eps, rho):
    """3 E[q^2] - 2 E[q^3] for q ~ Beta with mean eps and correlation rho (rho = 0: q = eps, rho = 1: q is 0 or 1, the repeating designer)"""
    if rho == 0:
        return 3 * eps ** 2 - 2 * eps ** 3
    if rho == 1:
        return eps
    s = (1 - rho) / rho
    a, b = eps * s, (1 - eps) * s
    m2 = a * (a + 1) / ((a + b) * (a + b + 1))
    m3 = m2 * (a + 2) / (a + b + 2)
    return 3 * m2 - 2 * m3


def distinct(r):
    return r["questions"] - r.get("reask_questions", 0)


def paths(s, T, lab):
    """the file of one set, truth and designer label ('err' is the independent designer)"""
    if s == "dev":
        return os.path.join(DEV, f"err_{C}_dev_{T}.jsonl" if lab == "err" else f"designer_{lab}_{C}_dev_{T}.jsonl")
    if s == "b2":
        return os.path.join(B2, f"err_{C}_b2_{T}.jsonl" if lab == "err" else f"designer_{lab}_{C}_b2_{T}.jsonl")
    return os.path.join(B3E, f"err_{T}.jsonl") if lab == "err" else os.path.join(B3D, f"designer_{lab}_{T}.jsonl")


rows = defaultdict(list)
for s in ("dev", "b2", "b3"):
    for T in ("full", "sure"):
        for lab, rho in (("err", 0.0), ("rho0.25", 0.25), ("rho0.5", 0.5), ("rep", 1.0)):
            for r in load(paths(s, T, lab)):
                # the err files also hold v6s, the trusting mode and the exact designer
                if r["variant"] != MAIN or not r["careful"] or r["designer_err"] not in (0.02, 0.05):
                    continue
                assert r["code"] == C and r["truth"] == T and r["budget"] == 1000, (s, T, lab)
                rows[s, T, rho, r["designer_err"]].append(r)
for k, rs in rows.items():
    assert len(rs) == RUNS[k[0]], (k, len(rs))
    assert len({(r["dataset"], r["seed"]) for r in rs}) == len(rs), k


def line(rs, eps, rho):
    """Q is the mean number of different questions over all runs, as in Prop. err, whose bound is on the wrong certificates among all runs; "within 100" is a run that certified after at most 100 questions, which a budget of 100 does not change"""
    c = [r for r in rs if r["certified"]]
    w = sum(r["wrong_cert"] for r in c)
    q = sum(distinct(r) for r in rs) / len(rs)
    c1 = [r for r in c if r["questions"] <= 100]
    w1 = sum(r["wrong_cert"] for r in c1)
    return (f"{len(rs):4d} {len(c):4d} {w:5d} {w / len(c) if c else 0:6.3f} {w / len(rs):6.3f} {q:6.1f} {min(1.0, q * premise(eps, rho)):6.3f} "
            f"{statistics.median(r['questions'] for r in rs):>6} {sum(bool(r['gold_good']) for r in rs):4d} {len(c1):5d} {w1:5d} {w1 / len(c1) if c1 else 0:6.3f}")


HEAD = f"{'runs':>4s} {'cert':>4s} {'wrong':>5s} {'share':>6s} {'of all':>6s} {'Q':>6s} {'bound':>6s} {'q med':>6s} {'good':>4s} {'c100':>5s} {'w100':>5s} {'share':>6s}"
print(f"{'set':4s} {'truth':5s} {'rho':>4s} {'eps':>4s} {HEAD}")
for k in sorted(rows):
    print(f"{k[0]:4s} {k[1]:5s} {k[2]:4.2f} {k[3]:4.2f} {line(rows[k], k[3], k[2])}")
print("\npooled over sets and truths")
print(f"{'rho':>4s} {'eps':>4s} {HEAD}")
pool = defaultdict(list)
for k, rs in rows.items():
    pool[k[2], k[3]].extend(rs)
for k in sorted(pool):
    print(f"{k[0]:4.2f} {k[1]:4.2f} {line(pool[k], k[1], k[0])}")
print("\nbatch 3 alone, pooled over truths")
print(f"{'rho':>4s} {'eps':>4s} {HEAD}")
pool = defaultdict(list)
for k, rs in rows.items():
    if k[0] == "b3":
        pool[k[2], k[3]].extend(rs)
for k in sorted(pool):
    print(f"{k[0]:4.2f} {k[1]:4.2f} {line(pool[k], k[1], k[0])}")
