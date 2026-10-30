"""
Design note item 39: the v5 family without a budget against the rules U1-U3.
Inputs (in confirm): v5_unb/v5_<T>.jsonl (v5, v5s, v5n with --budget 1000), v5_dev/price.json (the price of
every relation under both truths), and the budgeted runs v5_dev/v5_<T>.jsonl and v5_fresh2/v5_<T>.jsonl.
  U1 over all relations, the median of questions / price of v5 is at most 2 and the upper quartile at most 3,
     per truth; development and confirmatory relations are also reported apart.
  U2 consistency: a relation certified within 100 answers in the budgeted run is certified with the same number of
     answers in the unbounded run (the runs are deterministic and the budget only stops them).
  U3 report only: the share of relations certified within B answers for B from 25 to 1000 (v5, v5s, v5n) and the
     share whose price is at most B (the ceiling of every method); every run should certify within 1000.
Usage (in confirm):  python scripts/v5_unb_report.py [--dir v5_unb]
"""
import argparse, json, os, statistics

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEV = ["food", "hospital", "pricepaid", "ssb_customer", "ssb_date", "ssb_lineorder", "ssb_part", "ssb_supplier",
       "tpcds_core", "tpch_lineitem_orders", "tpch_orders_customer", "tpch_partsupp_part_supplier", "fresh_abs_mb",
       "fresh_chicago_crimes", "fresh_epa_aqs", "fresh_faa", "fresh_gtfs_at", "fresh_ldbc_comment", "fresh_ldbc_study",
       "fresh_pums_ca", "fresh_scorecard_fos", "fresh_sec_fsds", "fresh_usda_sr"]
CONF = ["fresh_auctionmark", "fresh_seats", "fresh_tatp", "fresh_simplewiki", "fresh_chembl", "fresh_musicbrainz",
        "fresh_pluto", "fresh_fhrs", "fresh_geonames", "fresh_eia860", "fresh_stats19", "fresh_ghcn"]
GRID = [25, 50, 75, 100, 125, 150, 200, 250, 300, 400, 500, 750, 1000]


def rows(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def quart(xs):
    xs = sorted(xs)
    if not xs:
        return None, None
    q = statistics.quantiles(xs, n=4, method="inclusive") if len(xs) >= 2 else [xs[0]] * 3
    return statistics.median(xs), q[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="v5_unb")
    a = ap.parse_args()
    with open(os.path.join(HERE, "v5_dev", os.environ.get("PRICE_FILE", "price.json")), encoding="utf-8") as fh:
        P = json.load(fh)
    for T in ("full", "sure"):
        U = {}
        for r in rows(os.path.join(HERE, a.dir, f"v5_{T}.jsonl")):
            assert r["truth"] == T and r["oracle"] == "gold" and r.get("budget") == 1000, (r["variant"], r["dataset"])
            U[(r["variant"], r["dataset"])] = r
        B = {}
        for f in ("v5_dev", "v5_fresh2"):
            for r in rows(os.path.join(HERE, f, f"v5_{T}.jsonl")):
                B[(r["variant"], r["dataset"])] = r
        dss = sorted({ds for _, ds in U})
        print(f"== truth {T}: {len(U)} runs over {len(dss)} relations")
        if not dss:
            continue
        # U1
        print("  relation                   cand  true price | v5 q  ratio cert | v5s q  cert | v5n q  cert")
        ratios = {"all": [], "dev": [], "conf": []}
        for ds in dss:
            p = P[f"{T}/{ds}"]["price"]
            v = U.get(("v5", ds))
            if not v:
                continue
            ratio = v["questions"] / p
            for k in ("all", "dev" if ds in DEV else "conf"):
                ratios[k].append(ratio)
            s = U.get(("v5s", ds), {}); n = U.get(("v5n", ds), {})
            print(f"  {ds:26s} {v['candidates']:5d} {v['true']:5d} {p:5d} | {v['questions']:4d} {ratio:6.2f} "
                  f"{'yes' if v['certified'] else 'NO ':4s} | {s.get('questions', 0):4d} {'yes' if s.get('certified') else 'NO ':4s}"
                  f" | {n.get('questions', 0):4d} {'yes' if n.get('certified') else 'NO ':4s}")
        for k in ("all", "dev", "conf"):
            m, q3 = quart(ratios[k])
            if m is None:
                continue
            over3 = sum(x > 3 for x in ratios[k])
            print(f"  U1 {k}: n {len(ratios[k])}, median ratio {m:.2f}, upper quartile {q3:.2f}, above 3x {over3}"
                  + (f" -> {'holds' if m <= 2 and q3 <= 3 else 'FAILS'}" if k == "all" else ""))
        # U2
        bad = []
        for (v, ds), r in B.items():
            u = U.get((v, ds))
            if r["certified"] and u is not None and (not u["certified"] or u["questions"] != r["questions"]):
                bad.append((v, ds, r["questions"], u["questions"], u["certified"]))
        checked = sum(1 for (v, ds), r in B.items() if r["certified"] and (v, ds) in U)
        print(f"  U2 consistency: {checked} certified budgeted runs compared, {len(bad)} differ"
              + (f": {bad}" if bad else " -> holds"))
        # U3
        unc = [(v, ds) for (v, ds), r in U.items() if not r["certified"]]
        print(f"  U3 not certified within 1000: {unc if unc else 'none'}")
        print("  B\tprice<=B\t" + "\t".join(f"{v}<=B" for v in ("v5", "v5s", "v5n")) + "   (share of relations)")
        for Bq in GRID:
            cols = [sum(1 for ds in dss if P[f"{T}/{ds}"]["price"] <= Bq) / len(dss)]
            for v in ("v5", "v5s", "v5n"):
                rs = [U[(v, ds)] for ds in dss if (v, ds) in U]
                cols.append(sum(1 for r in rs if r["certified"] and r["questions"] <= Bq) / len(rs) if rs else 0)
            print(f"  {Bq}\t" + "\t".join(f"{c:.2f}" for c in cols))


if __name__ == "__main__":
    main()
