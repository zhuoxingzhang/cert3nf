"""
Design note item 57: the careful mode of v5tol.py without a budget against the rules C1, C2, T1-T3.
Inputs (in confirm): v5tol_unb/v5tol_<T>.jsonl (v5t, v5st: careful, eps_m 0.02, mechanism c; v5, v5s: the
trusting controls of the same code; budget 1000, a designer who never errs), v5_unb/v5_<T>.jsonl (item 39: the
trusting family without a budget), v5tol_dev_c/ and v5tol_fresh2/ (item 34: the careful runs with the budget of 100)
and v5_dev/<PRICE_FILE> (default price_min.json, item 45).
  C1  the v5 and v5s rows of v5tol_unb equal those of v5_unb (certified, questions, gold_good)
  C2  a careful run certified within 100 answers in item 34 is the same run here (certified, same questions); one not
      certified there needs more than 100 answers here
  T1  every v5t run is certified within 1000 answers
  T2  questions(v5t) / questions(v5 of v5_unb) over the 35 relations: median <= 2 and upper quartile <= 3, per truth
      (quantiles inclusive, as v5_unb_report.py; a run not certified counts with its 1000 answers)
  T3  every v5t certificate is exact (cert_exact: H+ = Sigma*+ on the FDs of the data), and its design is good for
      gold wherever the trusting v5 certificate of v5_unb is (the relations whose data satisfy the documented FDs)
  report only: the same numbers for v5st; the share of relations certified within B answers for B in 10, 30, 100,
      300, 1000 (price, v5, v5t, v5st; all, development, confirmatory); the extra answers of v5t over v5 and its
      re-asked answers; the ratio of v5t to the price; the step coordinates of Fig. budget (--coords)
Usage (in confirm):  python scripts/v5tol_unb_report.py [--dir v5tol_unb] [--coords]
"""
import argparse, json, os, statistics

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEV = ["food", "hospital", "pricepaid", "ssb_customer", "ssb_date", "ssb_lineorder", "ssb_part", "ssb_supplier",
       "tpcds_core", "tpch_lineitem_orders", "tpch_orders_customer", "tpch_partsupp_part_supplier", "fresh_abs_mb",
       "fresh_chicago_crimes", "fresh_epa_aqs", "fresh_faa", "fresh_gtfs_at", "fresh_ldbc_comment", "fresh_ldbc_study",
       "fresh_pums_ca", "fresh_scorecard_fos", "fresh_sec_fsds", "fresh_usda_sr"]
CONF = ["fresh_auctionmark", "fresh_seats", "fresh_tatp", "fresh_simplewiki", "fresh_chembl", "fresh_musicbrainz",
        "fresh_pluto", "fresh_fhrs", "fresh_geonames", "fresh_eia860", "fresh_stats19", "fresh_ghcn"]
GRID = [10, 30, 100, 300, 1000]
CAREFUL = ("v5t", "v5st")
REF = {"v5t": "v5", "v5st": "v5s"}          # the trusting counterpart of a careful variant


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


def med(xs):
    return statistics.median(xs) if xs else None


def fmt(x):
    if x is None:
        return "--"
    return f"{x:.2f}" if isinstance(x, float) else str(x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="v5tol_unb")
    ap.add_argument("--coords", action="store_true", help="also the pgfplots coordinates of the careful curves")
    a = ap.parse_args()
    pf = os.environ.get("PRICE_FILE", "price_min.json")
    with open(os.path.join(HERE, "v5_dev", pf), encoding="utf-8") as fh:
        P = json.load(fh)
    print(f"== prices from v5_dev/{pf}")
    for T in ("full", "sure"):
        U = {}
        for r in rows(os.path.join(HERE, a.dir, f"v5tol_{T}.jsonl")):
            assert r["truth"] == T and r["oracle"] == "gold" and r.get("budget") == 1000, (r["variant"], r["dataset"])
            assert r["designer_err"] == 0 and not r["persistent"] and r["seed"] == 0, (r["variant"], r["dataset"])
            if r["variant"] in CAREFUL:
                assert r["eps_m"] > 0 and r["mech"] == "c", (r["variant"], r["dataset"])
            else:
                assert r["eps_m"] == 0, (r["variant"], r["dataset"])
            U[(r["variant"], r["dataset"])] = r
        R = {(r["variant"], r["dataset"]): r for r in rows(os.path.join(HERE, "v5_unb", f"v5_{T}.jsonl"))}
        B = {}
        for d in ("v5tol_dev_c", "v5tol_fresh2"):
            for r in rows(os.path.join(HERE, d, f"v5tol_{T}.jsonl")):
                if r["designer_err"] == 0 and not r["persistent"]:
                    B[(r["variant"], r["dataset"])] = r
        dss = sorted({ds for _, ds in U})
        print(f"== truth {T}: {len(U)} runs over {len(dss)} relations")
        if not dss:
            continue
        price = lambda ds: P[f"{T}/{ds}"]["price"]
        part = lambda ds: "dev" if ds in DEV else "conf"
        cert = lambda r: ("yes" if r.get("certified") else "NO ") if r else "-- "
        yn = lambda r, k: ("yes" if r.get(k) else "no ") if r else "-- "
        # the table
        print("  relation                   cand  true price | v5 q | v5t q  cert   /v5 /price reask exact good | v5st q cert | v5s q cert")
        for ds in dss:
            v = R.get(("v5", ds), {})
            t = U.get(("v5t", ds), {})
            s = U.get(("v5st", ds), {})
            o = U.get(("v5s", ds), {})
            tq, vq = t.get("questions"), v.get("questions")
            any_ = t or s
            print(f"  {ds:26s} {any_.get('candidates', 0):5d} {any_.get('true', 0):5d} {price(ds):5d} | {vq or 0:4d} | "
                  f"{tq or 0:4d} {cert(t)} {fmt(tq / vq if tq and vq else None):>5s} "
                  f"{fmt(tq / price(ds) if tq else None):>5s} {t.get('reask_questions', 0):5d} "
                  f"{yn(t, 'cert_exact')} {yn(t, 'gold_good')} | {s.get('questions', 0):4d} {cert(s)} | "
                  f"{o.get('questions', 0):4d} {cert(o)}")
        # C1
        bad, checked = [], 0
        for v in ("v5", "v5s"):
            for ds in dss:
                u, r = U.get((v, ds)), R.get((v, ds))
                if u is None or r is None:
                    continue
                checked += 1
                if (u["certified"], u["questions"], u["gold_good"]) != (r["certified"], r["questions"], r["gold_good"]):
                    bad.append((v, ds, u["questions"], r["questions"]))
        print(f"  C1 implementation check: {checked} v5/v5s runs compared with v5_unb, {len(bad)} differ"
              + (f": {bad} -> FAILS" if bad else " -> holds"))
        early = [(v, ds, r["questions"]) for (v, ds), r in U.items() if not r["certified"] and r["questions"] != 1000]
        print(f"  budget guard: {sum(not r['certified'] for r in U.values())} uncertified runs, "
              f"{len(early)} stopped before 1000 answers" + (f": {early} -> FAILS" if early else ""))
        # C2
        bad, checked = [], 0
        for (v, ds), b in B.items():
            u = U.get((v, ds))
            if v not in CAREFUL or u is None:
                continue
            checked += 1
            if b["certified"] and not (u["certified"] and u["questions"] == b["questions"] and u["gold_good"] == b["gold_good"]):
                bad.append((v, ds, b["questions"], u["questions"], u["certified"]))
            if not b["certified"] and u["certified"] and u["questions"] <= 100:
                bad.append((v, ds, "uncertified at 100", u["questions"]))
        print(f"  C2 consistency with the budget of 100: {checked} careful runs compared, {len(bad)} differ"
              + (f": {bad} -> FAILS" if bad else " -> holds"))
        # T1
        for v in CAREFUL:
            n = sum((v, ds) in U for ds in dss)
            unc = [ds for ds in dss if (v, ds) in U and not U[(v, ds)]["certified"]]
            tag = "T1" if v == "v5t" else "  "
            print(f"  {tag} {v}: {n - len(unc)}/{n} certified within 1000" + (f", not: {unc}" if unc else "")
                  + (f" -> {'holds' if not unc else 'FAILS'}" if tag == "T1" else ""))
        # T2
        for v in CAREFUL:
            ratios = {"all": [], "dev": [], "conf": []}
            over = {"all": 0, "dev": 0, "conf": 0}
            for ds in dss:
                u, r = U.get((v, ds)), R.get((REF[v], ds))
                if u is None or r is None:
                    continue
                x = u["questions"] / r["questions"]
                for k in ("all", part(ds)):
                    ratios[k].append(x)
                    over[k] += x > 3
            for k in ("all", "dev", "conf"):
                m, q3 = quart(ratios[k])
                if m is None:
                    continue
                tag = "T2" if v == "v5t" and k == "all" else "  "
                print(f"  {tag} {v} / {REF[v]} {k}: n {len(ratios[k])}, median ratio {m:.2f}, upper quartile {q3:.2f}, "
                      f"above 3x {over[k]}" + (f" -> {'holds' if m <= 2 and q3 <= 3 else 'FAILS'}" if tag == "T2" else ""))
        # T3
        for v in CAREFUL:
            cs = [ds for ds in dss if (v, ds) in U and U[(v, ds)]["certified"]]
            inexact = [ds for ds in cs if not U[(v, ds)]["cert_exact"]]
            clean = [ds for ds in cs if R.get(("v5", ds), {}).get("gold_good")]
            notgood = [ds for ds in clean if not U[(v, ds)]["gold_good"]]
            viol = [ds for ds in cs if ds not in clean]
            tag = "T3" if v == "v5t" else "  "
            print(f"  {tag} {v}: {len(cs)} certificates, {len(inexact)} not exact{': ' + str(inexact) if inexact else ''}; "
                  f"on the {len(clean)} relations whose data satisfy the documented FDs {len(notgood)} designs not good"
                  f"{': ' + str(notgood) if notgood else ''}; data violate a documented FD on {viol}"
                  + (f" -> {'holds' if not inexact and not notgood else 'FAILS'}" if tag == "T3" else ""))
        # the cost of the second answers
        for v in CAREFUL:
            ref = REF[v]
            pairs = [(U[(v, ds)], R[(ref, ds)]) for ds in dss if (v, ds) in U and (ref, ds) in R]
            extra = [u["questions"] - r["questions"] for u, r in pairs]
            both = [u["questions"] - r["questions"] for u, r in pairs if u["certified"] and r["certified"]]
            within = [u["questions"] - r["questions"] for u, r in pairs if r["certified"] and r["questions"] <= 100]
            reask = [u["reask_questions"] for u, _ in pairs]
            conf = [u["confirm_questions"] for u, _ in pairs]
            m, q3 = quart([u["questions"] / price(u["dataset"]) for u, _ in pairs])
            print(f"  cost {v} over {ref}: extra answers median {fmt(med(extra))} over {len(extra)} "
                  f"(both certified {fmt(med(both))} over {len(both)}; {ref} certified within 100 {fmt(med(within))} "
                  f"over {len(within)}); re-asked median {fmt(med(reask))}, confirm questions median {fmt(med(conf))}; "
                  f"{v} / price median {fmt(m)} upper quartile {fmt(q3)}")
        # the budget grid
        for k, sub in (("all", dss), ("dev", [d for d in dss if d in DEV]), ("conf", [d for d in dss if d in CONF])):
            print(f"  {k} ({len(sub)}): B\tprice<=B\tv5<=B\tv5t<=B\tv5st<=B   (share of relations)")
            for Bq in GRID:
                cols = [sum(price(ds) <= Bq for ds in sub) / len(sub)]
                for src, v in ((R, "v5"), (U, "v5t"), (U, "v5st")):
                    rs = [src[(v, ds)] for ds in sub if (v, ds) in src]
                    cols.append(sum(r["certified"] and r["questions"] <= Bq for r in rs) / len(rs) if rs else 0)
                print(f"    {Bq}\t" + "\t".join(f"{c:.2f}" for c in cols))
        if a.coords:
            for v in CAREFUL:
                qs = sorted(U[(v, ds)]["questions"] for ds in dss if (v, ds) in U and U[(v, ds)]["certified"])
                n = sum((v, ds) in U for ds in dss)
                pts = [(10, sum(q <= 10 for q in qs) / n)]
                pts += [(q, sum(x <= q for x in qs) / n) for q in sorted(set(qs)) if q > 10]
                pts.append((1000, len(qs) / n))
                print(f"  coords {T} {v} n {n}: " + " ".join(f"({x},{y:.3f})" for x, y in pts))


if __name__ == "__main__":
    main()
