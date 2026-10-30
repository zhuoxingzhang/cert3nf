"""The dashed price curve of Fig. budget: the share of the relations of v5_unb whose price is at most B, as pgfplots
coordinates (a step at every price), per truth.  Usage (in confirm):  python scripts/fig_budget_price.py PRICE_FILE"""
import json, os, sys

pf = sys.argv[1]
P = json.load(open(os.path.join("v5_dev", pf), encoding="utf-8"))
for T in ("full", "sure"):
    dss = sorted({json.loads(x)["dataset"] for x in open(f"v5_unb/v5_{T}.jsonl", encoding="utf-8") if x.strip()})
    pr = sorted(P[f"{T}/{ds}"]["price"] for ds in dss)
    n = len(pr)
    pts = [(10, sum(p <= 10 for p in pr) / n)]
    for p in sorted(set(pr)):
        if p > 10:
            pts.append((p, sum(q <= p for q in pr) / n))
    pts.append((1000, 1.0))
    print(T, n, " ".join(f"({x},{y:.3f})" for x, y in pts))
