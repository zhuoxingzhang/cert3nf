"""Report of design note item 43 (no pass lines): Cert3NF with the refutation by the data relaxed to g3 > theta
(v5tau.py).  Per instance set (the 12 repaired confirmatory relations, the 4 unrepaired ones), truth, budget, theta and
variant: runs, certified, certified but not good for the documented FDs (gold), median questions of the certified runs,
and the questions that only the tolerance leaves to the designer.  theta = 0 is v5 (v5_fresh2, v5_unb for the
repaired instances; the theta = 0 rows of v5tau for the unrepaired ones).
Usage (in confirm, with the outputs of v5tau.py in tau43/):  python scripts/tau43_report.py"""
import json, os, statistics
from collections import defaultdict


def load(f):
    if not os.path.exists(f):
        return []
    with open(f, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


rows = defaultdict(list)
for T in ("full", "sure"):
    for B, ref in ((100, f"v5_fresh2/v5_{T}.jsonl"), (1000, f"v5_unb/v5_{T}.jsonl")):
        fresh = {json.loads(x)["dataset"] for x in open(f"v5_fresh2/v5_{T}.jsonl", encoding="utf-8")}
        for r in load(ref):
            if r["variant"] in ("v5", "v5s") and r["dataset"] in fresh:
                rows["repaired", T, B, 0.0, r["variant"]].append(r)
        for r in load(f"tau43/rep_{T}_b{B}.jsonl"):
            rows["repaired", T, B, r["theta"], r["variant"]].append(r)
        for r in load(f"tau43/raw_{T}_b{B}.jsonl"):
            rows["unrepaired", T, B, r["theta"], r["variant"]].append(r)
print(f"{'instances':10s} {'truth':5s} {'B':>4s} {'theta':>6s} {'var':4s} {'runs':>4s} {'cert':>4s} {'bad':>4s} {'med q':>6s} {'theta q':>7s}")
for k in sorted(rows):
    rs = rows[k]
    c = [r for r in rs if r["certified"]]
    bad = [r["dataset"] for r in c if not r["gold_good"]]
    mq = statistics.median(r["questions"] for r in c) if c else None
    tq = sum(r.get("theta_questions", 0) for r in rs)
    print(f"{k[0]:10s} {k[1]:5s} {k[2]:4d} {k[3]:6.3f} {k[4]:4s} {len(rs):4d} {len(c):4d} {len(bad):4d} {mq!s:>6s} {tq:7d}  {','.join(d.replace('fresh_', '') for d in bad)}")
