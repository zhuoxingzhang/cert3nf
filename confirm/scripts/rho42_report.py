"""Report of design note item 42 (b): the tolerant v5 (mechanism c) under a designer whose errors are correlated per
question (v5tol.py --rho), against the independent designer (rho = 0) of v5tol_dev_c and v5tol_fresh2.  Per set
(development, confirmatory), truth, rho, variant and eps: runs, certified, wrong certificates, their share, and the
bound of Prop. err, N (3 E[eps_q^2] - 2 E[eps_q^3]), at the median number N of different questions of the certified
runs (from the run's question log when present, otherwise its questions minus its repetitions).
Usage (in confirm):  python scripts/rho42_report.py"""
import json, os, statistics
from collections import defaultdict


def load(f):
    with open(f, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def premise(eps, rho):
    """3 E[q^2] - 2 E[q^3] for q ~ Beta with mean eps and correlation rho (rho = 0: q = eps)"""
    if rho == 0:
        return 3 * eps ** 2 - 2 * eps ** 3
    s = (1 - rho) / rho
    a, b = eps * s, (1 - eps) * s
    m2 = a * (a + 1) / ((a + b) * (a + b + 1))
    m3 = m2 * (a + 2) / (a + b + 2)
    return 3 * m2 - 2 * m3


def distinct(r):
    return r["questions"] - r.get("reask_questions", 0)


rows = defaultdict(list)
for setname, ref in (("dev", "v5tol_dev_c"), ("conf", "v5tol_fresh2")):
    for T in ("full", "sure"):
        for r in load(os.path.join(ref, f"v5tol_{T}.jsonl")):
            if r["variant"] in ("v5t", "v5st") and r["designer_err"] in (0.02, 0.05) and not r["persistent"] and r.get("mech", "c") == "c":
                rows[setname, T, 0.0, r["variant"], r["designer_err"]].append(r)
        for rho in (0.25, 0.5):
            f = f"v5tol_rho/{setname}_{T}_rho{rho}.jsonl"
            for r in load(f):
                rows[setname, T, rho, r["variant"], r["designer_err"]].append(r)
print(f"{'set':4s} {'truth':5s} {'rho':>4s} {'var':4s} {'eps':>4s} {'runs':>4s} {'cert':>4s} {'wrong':>5s} {'share':>6s} {'N':>5s} {'bound':>6s}")
for k in sorted(rows):
    rs = rows[k]
    c = [r for r in rs if r["certified"]]
    w = sum(r["wrong_cert"] for r in c)
    n = statistics.median(distinct(r) for r in c) if c else None
    bd = min(1.0, n * premise(k[4], k[2])) if n else None
    print(f"{k[0]:4s} {k[1]:5s} {k[2]:4.2f} {k[3]:4s} {k[4]:4.2f} {len(rs):4d} {len(c):4d} {w:5d} {(w / len(c) if c else 0):6.3f} "
          f"{n if n is not None else '-':>5} {bd if bd is None else round(bd, 3)!s:>6}")
# pooled over the two sets and truths
print("\npooled over sets and truths")
pool = defaultdict(list)
for k, rs in rows.items():
    pool[k[2], k[3], k[4]].extend(rs)
for k in sorted(pool):
    c = [r for r in pool[k] if r["certified"]]
    w = sum(r["wrong_cert"] for r in c)
    print(f"  rho {k[0]:4.2f} {k[1]:4s} eps {k[2]:4.2f}: runs {len(pool[k]):4d} cert {len(c):4d} wrong {w:3d} share {w / len(c) if c else 0:.3f}")
