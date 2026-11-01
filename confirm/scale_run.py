"""
The scale experiment (design note item 53) on the synthetic relations of ../e3/scale.py.  auto_common.py stays as it
is: at import, the relations of e3/truth/scale.json become the relations under evaluation (FRESH), with their declared
keys, so that no pool trains on them, and the prior is learned on the development relations, as for the confirmatory
ones (CONFIRM_BATCH=2).
Usage (in confirm, with CONFIRM_TRUTH=full CONFIRM_ORACLE=gold CONFIRM_BATCH=2):
  python scale_run.py v5 --answers llm_fresh2_full_q35 --variants v5s,v5n --budget 1000 --workers 8 --out scale/v5.jsonl
  python scale_run.py price --results scale/v5.jsonl --out scale/price.json
  python scale_run.py check --results scale/v5.jsonl --out scale/check.jsonl
  python scale_run.py report --results scale/v5.jsonl --price scale/price.json --check scale/check.jsonl
"""
import json, os, statistics, sys, time

import auto_common as AC

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "e3", "truth", "scale.json"),
          encoding="utf-8") as _fh:
    SCALE = json.load(_fh)["datasets"]
AC.DECLARED.update({ds: spec["key"] for ds, spec in SCALE.items()})
AC.FRESH = [ds for ds in SCALE if os.path.exists(os.path.join(AC.bench.E3, ds + ".json"))]


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def rows(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def run_v5():
    import v5
    sys.argv = ["v5.py"] + sys.argv[2:] + ([] if "--datasets" in sys.argv else ["--datasets", ",".join(AC.FRESH)])
    # every worker loads the relations of auto_confirm.benches(), of which the prior trains on the pool only; the
    # synthetic relations, with up to millions of candidates, are therefore loaded only by the run that evaluates them
    AC.FRESH = []
    v5.main()


def price():
    """the price of Thm. price as in price_min.py: the upper bound of a smallest cover (cover_bounds.py, with the yes
    answers of the certified runs) plus the held sets m_r (price_sets.py)"""
    import cover_bounds as CB
    import price_sets as PS
    runs, seen = {}, set()
    for r in rows(arg("--results")):
        seen.add(r["dataset"])
        if r.get("certified"):
            runs.setdefault(r["dataset"], []).append(r["certificate"]["yes"])
    out = {}
    # a relation without any run (the runs did not fit into memory) is reported by report(), not priced
    for ds in (d for d in AC.FRESH if d in seen):
        t0 = time.time()
        b = AC.load(ds)
        idx = {x: i for i, x in enumerate(b["names"])}
        ys = [[(sum(1 << idx[c] for c in l), 1 << idx[a]) for l, a in y] for y in runs.get(ds, [])]
        cover4, pairs, mstar = PS.price_sets(b)
        bb = CB.bounds(b, ys)
        out[ds] = {"attributes": len(b["R"]), "candidates": len(b["P"]), "true": len(b["truth"]),
                   "truth_single_rhs": sum(len(t["rhs"]) for t in SCALE[ds]["truth"][1:]),
                   "cover": bb["cover_ub"], "cover_lb": bb["cover_lb"], "cover_exact": bb["cover_lb"] == bb["cover_ub"],
                   "m_r": mstar, "m_r_pairs": pairs, "price": bb["cover_ub"] + mstar, "secs": round(time.time() - t0, 1)}
        print(ds, out[ds], flush=True)
    with open(arg("--out"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)


def check():
    import check_cert as CC
    with open(arg("--out"), "w", encoding="utf-8") as fo:
        for r in rows(arg("--results")):
            c = CC.check(AC.load(r["dataset"]), r["certificate"], truth=True)
            c = {k: v for k, v in c.items() if not k.endswith("_examples")}
            fo.write(json.dumps({"variant": r["variant"], "dataset": r["dataset"], "run_certified": r["certified"],
                                 "gold_good": r.get("gold_good"), **c}) + "\n")
            print(r["variant"], r["dataset"], r["certified"], c, flush=True)


def spearman(x, y):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        rk = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for t in range(i, j + 1):
                rk[order[t]] = (i + j) / 2
            i = j + 1
        return rk
    rx, ry = ranks(x), ranks(y)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    return sxy / (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5


def report():
    """rules S1-S3 of item 53 and the reported numbers, per configuration (median over the three seeds)"""
    R = rows(arg("--results"))
    P = json.load(open(arg("--price"), encoding="utf-8"))
    C = {(c["variant"], c["dataset"]): c for c in rows(arg("--check"))}
    cfg = lambda ds: (int(ds.split("_")[1][1:]), int(ds.split("_")[2][1:]))
    # not mined within two hours, or mined with more candidates than the memory holds (the logs of run_scale*.sh tell which)
    print("no run:", [ds for ds in SCALE if not any(r["dataset"] == ds for r in R)])
    s1 = []
    for r in R:
        c = C[(r["variant"], r["dataset"])]
        s1.append(r["certified"] and c["certified"] and c["sound"] and r["gold_good"])
        if not s1[-1]:
            print("S1 fails on", r["variant"], r["dataset"], r["questions"], c)
    print(f"S1: {sum(s1)}/{len(s1)} runs certified within the budget, checked and good -> "
          f"{'holds' if all(s1) else 'FAILS'}")
    v5s = {r["dataset"]: r for r in R if r["variant"] == "v5s"}
    v5n = {r["dataset"]: r for r in R if r["variant"] == "v5n"}
    ok2 = True
    print("n  share  rel  candidates  true  cover  m_r  price  v5s  ratio  v5n  secs/answer  (medians)")
    for key in sorted({cfg(ds) for ds in v5s}):
        dss = [ds for ds in v5s if cfg(ds) == key]
        m = lambda f: statistics.median(f(ds) for ds in dss)
        ratio = m(lambda ds: v5s[ds]["questions"] / P[ds]["price"])
        ok2 &= ratio <= 2
        print(f"{key[0]:2d}  {key[1] / 100:.1f}  {len(dss)}  {m(lambda ds: P[ds]['candidates']):9.0f}  "
              f"{m(lambda ds: P[ds]['true']):4.0f}  {m(lambda ds: P[ds]['cover']):4.0f}  {m(lambda ds: P[ds]['m_r']):4.0f}  "
              f"{m(lambda ds: P[ds]['price']):5.0f}  {m(lambda ds: v5s[ds]['questions']):4.0f}  {ratio:.2f}  "
              f"{m(lambda ds: v5n[ds]['questions']) if all(ds in v5n for ds in dss) else float('nan'):4.0f}  "
              f"{m(lambda ds: v5s[ds]['secs'] / max(v5s[ds]['questions'], 1)):.3f}")
    print(f"S2: median ratio of answers to price at most 2 in every configuration -> {'holds' if ok2 else 'FAILS'}")
    dss = sorted(v5s)
    q = [v5s[ds]["questions"] for ds in dss]
    rp, rc = spearman(q, [P[ds]["price"] for ds in dss]), spearman(q, [P[ds]["candidates"] for ds in dss])
    print(f"S3: Spearman(answers, price) {rp:.2f} vs Spearman(answers, candidates) {rc:.2f} -> "
          f"{'holds' if rp > rc else 'FAILS'}")
    print("not exact covers:", [ds for ds in dss if not P[ds]["cover_exact"]])
    print("max secs per run:", max(r["secs"] for r in R), "max secs per answer:",
          round(max(r["secs"] / max(r["questions"], 1) for r in R), 3))


if __name__ == "__main__":
    {"v5": run_v5, "price": price, "check": check, "report": report}[sys.argv[1]]()
