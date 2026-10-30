"""Report of design note item 44: attribute exploration (aexp.c) against the price of Thm. price (smallest F, held sets
counted once, v5_fresh2/price_min.json) and the answers of v5, v5s and v5n without a budget (v5_unb, budget 1000).
Per truth and counterexample variant (min: the closure under Sigma*, pre-registered; max: the largest, exploratory):
per relation the implication questions (yes, no), the unit yes/no answers they amount to, the closed sets visited and
the time; a run stopped at the time limit gives lower bounds (marked >=).  Medians of unit / price and unit / v5 over
all relations, with stopped runs at their lower bounds.
Usage (in confirm, with the outputs of aexp.py in ae44/):  python scripts/aexp_report.py"""
import json, os, statistics


def load(f):
    if not os.path.exists(f):
        return []
    with open(f, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


price = json.load(open("v5_fresh2/price_min.json", encoding="utf-8"))
for T in ("full", "sure"):
    unb = {}
    for r in load(f"v5_unb/v5_{T}.jsonl"):
        if r["variant"] in ("v5", "v5s", "v5n") and r["certified"]:
            unb[r["dataset"], r["variant"]] = r["questions"]
    for var, f in (("min", f"ae44/aexp_{T}.jsonl"), ("max", f"ae44/aexp_max_{T}.jsonl")):
        rows = load(f)
        if not rows:
            continue
        print(f"== truth {T}, counterexamples {var}")
        print(f"{'relation':20s} {'done':>4s} {'yes':>5s} {'no':>9s} {'unit':>10s} {'visited':>9s} {'secs':>7s} {'equiv':>5s} "
              f"{'price':>5s} {'v5':>5s} {'v5s':>5s} {'v5n':>5s} {'unit/price':>11s} {'unit/v5':>9s}")
        rp, rv = [], []
        for r in rows:
            ds = r["dataset"]
            p = price[f"{T}/{ds}"]["price"]
            q = [unb.get((ds, v)) for v in ("v5", "v5s", "v5n")]
            ge = "" if r["finished"] else ">="
            rp.append(r["unit"] / p)
            if q[0]:
                rv.append(r["unit"] / q[0])
            print(f"{ds.replace('fresh_', ''):20s} {r['finished']!s:>4s} {r['yes']:5d} {ge + str(r['no']):>9s} {ge + str(r['unit']):>10s} "
                  f"{r['visited']:9d} {r['secs']:7.1f} {r['equivalent']!s:>5s} {p:5d} {q[0]!s:>5s} {q[1]!s:>5s} {q[2]!s:>5s} "
                  f"{ge + format(r['unit'] / p, '.0f'):>11s} {ge + format(r['unit'] / q[0], '.0f') if q[0] else '-':>9s}")
        print(f"  median unit/price {statistics.median(rp):.0f}, unit/v5 {statistics.median(rv) if rv else float('nan'):.0f}; "
              f"finished {sum(bool(r['finished']) for r in rows)}/{len(rows)}, equivalent {sum(bool(r['equivalent']) for r in rows)}")
