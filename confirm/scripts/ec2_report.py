"""
Design note item 52: rules E1 and E2 (C6 of the paper) and the reported numbers for the interactive baseline (ec2hyb,
ec2hyb0) on the twelve confirmatory relations, from files kept in confirm/:
  ec2_results/results_ec2_<T>.jsonl   the runs of ec2hyb.py (variants ec2hyb and ec2hyb0, seeds 0-2)
  v5_fresh2/v5_<T>.jsonl              Cert3NF (v5), as in Table 3
  paper_src/conf_<T>_rbhyb.jsonl      the posterior certificate with the marginal choice (rbhyb, rbhyb0), as in Table 3
Good designs are counted as in Table 4 (paper_tables_v5.py): a relation counts if the median of its seeds is good.
Usage (in confirm/): python scripts/ec2_report.py > ec2_results/report.txt
"""
import json, os, statistics

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF = ["fresh_auctionmark", "fresh_seats", "fresh_tatp", "fresh_simplewiki", "fresh_chembl", "fresh_musicbrainz",
        "fresh_pluto", "fresh_fhrs", "fresh_geonames", "fresh_eia860", "fresh_stats19", "fresh_ghcn"]
CLASS_A = {"fresh_auctionmark", "fresh_seats", "fresh_tatp", "fresh_simplewiki"}
VIOL = {"full": {"fresh_seats", "fresh_simplewiki", "fresh_chembl", "fresh_musicbrainz", "fresh_pluto"}, "sure": set()}
PARTS = (("all", CONF), ("A", [d for d in CONF if d in CLASS_A]), ("B", [d for d in CONF if d not in CLASS_A]))


def rows(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def med(xs):
    return statistics.median(xs) if xs else None


def per_rel(rs):
    out = {}
    for r in rs:
        out.setdefault(r["dataset"], []).append(r)
    return out


def good_rel(runs):
    return med([bool(r.get("gold_good")) for r in runs]) >= 0.5


def main():
    for T in ("full", "sure"):
        v5 = {r["dataset"]: r for r in rows(os.path.join(HERE, "v5_fresh2", f"v5_{T}.jsonl")) if r["variant"] == "v5"}
        ref = rows(os.path.join(HERE, "paper_src", f"conf_{T}_rbhyb.jsonl"))
        ec2 = rows(os.path.join(HERE, "ec2_results", f"results_ec2_{T}.jsonl"))
        print(f"==== {T} truth")
        R = {v: per_rel([r for r in ref + ec2 if r["variant"] == v]) for v in ("rbhyb", "rbhyb0", "ec2hyb", "ec2hyb0")}
        for v, P in R.items():
            assert sorted(P) == sorted(CONF) and all(len(P[d]) == 3 for d in CONF), (v, {d: len(P.get(d, [])) for d in CONF})
        c5 = [d for d in CONF if v5[d].get("certified")]
        for v in ("ec2hyb", "ec2hyb0"):
            P = R[v]
            print(f"-- rules for {v}")
            for name, part in PARTS:
                g5 = sum(bool(v5[d].get("gold_good")) for d in part)
                ge = sum(good_rel(P[d]) for d in part)
                print(f"E1 {name}: good designs at the end of the budget, Cert3NF {g5}/{len(part)} vs {v} {ge}/{len(part)} "
                      f"-> {'holds' if g5 >= ge else 'FAILS'}")
            ce = [d for d in CONF if sum(bool(r.get("certified")) for r in P[d]) >= 2]
            print(f"E2: relations certified within 100, Cert3NF {len(c5)} vs {v} (at least two seeds) {len(ce)} "
                  f"-> {'holds' if len(c5) >= len(ce) else 'FAILS'}")
            print(f"   Cert3NF: {sorted(c5)}; {v}: {sorted(ce)}")
        print("-- reported")
        for v, P in R.items():
            rs = [r for d in CONF for r in P[d]]
            c = [r for r in rs if r.get("certified")]
            wrong = [r for r in c if not r.get("gold_good")]
            f1 = statistics.mean(statistics.mean(r.get("f1") or 0.0 for r in P[d]) for d in CONF)
            both = [r for r in c if r["dataset"] in c5]
            print(f"{v}: certified runs {len(c)}/{len(rs)}, median answers {med([r['questions'] for r in c])}, "
                  f"wrong {len(wrong)} ({sorted({r['dataset'] for r in wrong})}; pre-listed "
                  f"{sum(r['dataset'] in VIOL[T] for r in wrong)}), certified relations (two seeds) "
                  f"{sum(sum(bool(r.get('certified')) for r in P[d]) >= 2 for d in CONF)}, "
                  f"good relations (median seed) {sum(good_rel(P[d]) for d in CONF)}/12, macro F1 {f1:.2f}; "
                  f"where Cert3NF certifies too: Cert3NF - {v} answers median "
                  f"{med([v5[r['dataset']]['questions'] - r['questions'] for r in both])} over {len(both)} runs; "
                  f"secs median {med([r['secs'] for r in rs])}, max {max(r['secs'] for r in rs)}")
            for d in CONF:
                cells = [f"{r['questions']}{'' if not r.get('certified') else ('c' if r.get('gold_good') else 'c!')}"
                         for r in sorted(P[d], key=lambda r: r["seed"])]
                print(f"   {d:20s} {' '.join(cells)}")
        print(f"Cert3NF: certified {len(c5)} {sorted(c5)}, good {sum(bool(r.get('gold_good')) for r in v5.values())}/12")
        for a, b in (("rbhyb", "ec2hyb"), ("rbhyb0", "ec2hyb0")):
            pairs = [(x, y) for d in CONF for x in R[a][d] for y in R[b][d] if x["seed"] == y["seed"]]
            bc = [(x, y) for x, y in pairs if x.get("certified") and y.get("certified")]
            print(f"{b} vs {a} by seed: certified {sum(bool(y.get('certified')) for _, y in pairs)} vs "
                  f"{sum(bool(x.get('certified')) for x, _ in pairs)}; both certified {len(bc)}, "
                  f"{b} - {a} answers median {med([y['questions'] - x['questions'] for x, y in bc])}")


if __name__ == "__main__":
    main()
