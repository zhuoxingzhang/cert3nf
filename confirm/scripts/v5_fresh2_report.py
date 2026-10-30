"""The confirmatory evaluation of v5 (design notes, item 33) against its pre-registered rules K1-K6, per
truth, on the twelve relations of the second batch; every rule for all relations, class A and class B apart.

Inputs (in confirm): v5_fresh2/v5_<truth>.jsonl (v5, v5s, v5n, v5u; run_v5_fresh2.sh), v5_fresh2/price.json
(price.py), llm_fresh2_<truth>_q35/results_rbhyb.jsonl (rbhyb, rbhyb0, seeds 0-2) and results.jsonl (the fully
automated methods of item 19's main table).  A missing input leaves its rules undetermined; a verdict on fewer than
the twelve relations is interim.
  K1 exact: check_cert.check agrees with every run of the v5 family that carries a certificate; every premise of a
     certified run is right for gold; every certified design is good for gold, except on the relations listed before
     the run whose documented FDs the data violate (outside the certificate by its premise r |= Sigma*).
  K2 LLM helps: v5 certifies more relations than v5s, or as many with a median of q(v5) - q(v5s) <= -3 over the
     relations both certify; both truths must hold.
  K3 bounded damage: v5 certifies at least as many as v5n, and q(v5) <= q(v5n) + b + (maximal sets answered yes) on
     at least 90% of the relations.
  K4 price: median questions / price (b) over the certified v5 runs <= 2; every certified run of the v5 family has
     at least m*_r no answers, the number of distinct maximal sets of Sigma* that hold on r (design note item 35,
     Thm. N (i): part (c) of the price theorem over-counts and is replaced; the certificate's no answers are the
     designer's: a question the data refute is answered without the designer and is not in the certificate).
  K5 certify over discover: designs good for gold at the stop, v5 >= rbhyb (per relation, rbhyb by the median of its
     three seeds); rbhyb's wrong posterior certificates and the fully automated methods are reported.
  K6 report only.
Usage (in confirm):  python scripts/v5_fresh2_report.py [--v5dir v5_fresh2] [--answers llm_fresh2] [--model q35]
(the gpt-oss-20b robustness run of item 37: --v5dir v5_fresh2_gptoss --model gptoss)
"""
import argparse, json, os, statistics, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.environ.setdefault("CONFIRM_ORACLE", "gold")
import auto_common as AC          # noqa: E402
from check_cert import check      # noqa: E402
from price import closure, maxsets  # noqa: E402

CLASS_A = {"fresh_auctionmark", "fresh_seats", "fresh_tatp", "fresh_simplewiki"}
# pre-listed (design note item 33, 2026-10-28 23:35): relations whose documented FDs the data violate, per truth
VIOLATED = {"full": {"fresh_seats", "fresh_simplewiki", "fresh_chembl", "fresh_musicbrainz", "fresh_pluto"},
            "sure": set()}
FAMILY = ("v5", "v5s", "v5n", "v5u")
AUTO = ("ours", "clf", "trust", "hyfd", "L1", "A5", "A9", "upper")


def rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def med(xs):
    xs = list(xs)
    return statistics.median(xs) if xs else None


def verdict(ok):
    return "undetermined" if ok is None else "holds" if ok else "FAILS"


def m_star(b):
    """the distinct maximal sets of Sigma* (sigma0 and the documented FDs) that hold on r for some attribute"""
    n = len(b["R"])
    full = (1 << n) - 1
    mask = lambda s: sum(1 << i for i in s)
    F = [(mask(l), mask(r)) for l, r in b["sigma0"]] + [(mask(l), mask(r)) for l, r in b["gold"]]
    minfd = {}
    for p in b["P"] + b["implied0"]:
        minfd.setdefault(mask(p[1]), []).append(mask(p[0]))
    held = set()
    for a in range(n):
        for M in maxsets(F, 1 << a, full):
            if any(x & ~M == 0 for x in minfd.get(1 << a, [])):
                held.add(M)
    return len(held)


def k_rules(T, V, price, RB, AU, dss, label, mst):
    """K1-K5 on the relations dss; returns {rule: True/False/None}"""
    out = {}
    print(f"  -- {label}: {len(dss)} relations")
    # K1
    bad = []
    for v in FAMILY:
        for ds in dss:
            r = V.get((v, ds))
            if r is None:
                continue
            c = r["_check"]
            if c["certified"] != r["certified"]:
                bad.append(f"{v}/{ds} checker disagrees")
            if r["certified"] and not c["sound"]:
                bad.append(f"{v}/{ds} premises wrong yes {c['yes_wrong']} no {c['no_wrong']}")
            if r["certified"] and not r["gold_good"] and ds not in VIOLATED[T]:
                bad.append(f"{v}/{ds} certified design not good for gold")
    n = sum((v, ds) in V for v in FAMILY for ds in dss)
    out["K1"] = None if not n else not bad
    excused = [f"{v}/{ds}" for v in FAMILY for ds in dss if (v, ds) in V and V[(v, ds)]["certified"]
               and not V[(v, ds)]["gold_good"] and ds in VIOLATED[T]]
    print(f"    K1 runs checked {n}; problems {bad or 'none'}; certified designs not good on pre-listed relations "
          f"{excused or 'none'} -> {verdict(out['K1'])}")
    # K2
    have = [ds for ds in dss if ("v5", ds) in V and ("v5s", ds) in V]
    c5 = sum(V[("v5", ds)]["certified"] for ds in have)
    cs = sum(V[("v5s", ds)]["certified"] for ds in have)
    diff = [V[("v5", ds)]["questions"] - V[("v5s", ds)]["questions"] for ds in have
            if V[("v5", ds)]["certified"] and V[("v5s", ds)]["certified"]]
    out["K2"] = None if not have else c5 > cs or (c5 == cs and med(diff) is not None and med(diff) <= -3)
    print(f"    K2 certified v5 {c5}, v5s {cs} of {len(have)}; q(v5) - q(v5s) where both certify: median {med(diff)} "
          f"(n {len(diff)}) -> {verdict(out['K2'])}")
    # K3
    have = [ds for ds in dss if ("v5", ds) in V and ("v5n", ds) in V]
    c5 = sum(V[("v5", ds)]["certified"] for ds in have)
    cn = sum(V[("v5n", ds)]["certified"] for ds in have)
    ok = [ds for ds in have if V[("v5", ds)]["questions"] <= V[("v5n", ds)]["questions"] + V[("v5", ds)]["cap"]
          + V[("v5", ds)]["max_questions"] - V[("v5", ds)]["max_no"]]
    out["K3"] = None if not have else c5 >= cn and len(ok) >= 0.9 * len(have)
    print(f"    K3 certified v5 {c5} >= v5n {cn}; bound holds on {len(ok)}/{len(have)} "
          f"(fails on {sorted(set(have) - set(ok)) or 'none'}) -> {verdict(out['K3'])}")
    # K4
    rat, low = [], []
    for v in FAMILY:
        for ds in dss:
            r, pr = V.get((v, ds)), price.get(f"{T}/{ds}")
            if r is None or not r["certified"] or pr is None:
                continue
            if v == "v5":
                rat.append(r["questions"] / pr["price"])
            if r["refuted_answers"] < mst[ds]:
                low.append(f"{v}/{ds} no {r['refuted_answers']} < m*_r {mst[ds]}")
    out["K4"] = None if not price or not rat else med(rat) <= 2 and not low
    print(f"    K4 questions/price over certified v5 runs: median {med(rat) and round(med(rat), 2)}, n {len(rat)}"
          f"{', range %.2f-%.2f' % (min(rat), max(rat)) if rat else ''}; below the no bound {low or 'none'} "
          f"-> {verdict(out['K4'])}")
    # K5
    have = [ds for ds in dss if ("v5", ds) in V and len(RB.get("rbhyb", {}).get(ds, {})) == 3]
    g5 = sum(bool(V[("v5", ds)]["gold_good"]) for ds in have)
    gr = sum(med(int(bool(r["gold_good"])) for r in RB["rbhyb"][ds].values()) >= 0.5 for ds in have)
    out["K5"] = None if not have else g5 >= gr
    print(f"    K5 good for gold at the stop: v5 {g5}, rbhyb (median of three seeds) {gr} of {len(have)} -> "
          f"{verdict(out['K5'])}")
    for v in ("rbhyb", "rbhyb0"):
        runs = [r for ds in dss for r in RB.get(v, {}).get(ds, {}).values()]
        cert = [r for r in runs if r["certified"]]
        print(f"       {v}: posterior certificates {len(cert)}/{len(runs)}, wrong for gold "
              f"{sum(not r['gold_good'] for r in cert)} (for reach {sum(not r['reach_good'] for r in cert)}); good "
              f"designs for gold {sum(bool(r['gold_good']) for r in runs)}/{len(runs)}")
    auto = {v: (sum(bool(r.get("gold_good")) for ds in dss for r in AU.get(v, {}).get(ds, {}).values()),
                sum(len(AU.get(v, {}).get(ds, {})) for ds in dss)) for v in AUTO}
    print("       fully automated, good for gold (runs): " + ", ".join(f"{v} {g}/{k}" for v, (g, k) in auto.items() if k)
          + ("" if all(k for _, k in auto.values()) else "  (not every method run)"))
    return out


def report(T, v5dir, answers, model="q35"):
    os.environ["CONFIRM_TRUTH"] = T
    V = {}
    for r in rows(os.path.join(HERE, v5dir, f"v5_{T}.jsonl")):
        assert r["truth"] == T and r["oracle"] == "gold", (r["variant"], r["dataset"], r["truth"], r["oracle"])
        V[(r["variant"], r["dataset"])] = r
    pp = os.path.join(HERE, v5dir, "price.json")
    price = json.load(open(pp, encoding="utf-8")) if os.path.exists(pp) else {}
    RB, AU = {}, {}
    for f, by in (("results_rbhyb", RB), ("results", AU)):
        for r in rows(os.path.join(HERE, f"{answers}_{T}_{model}", f + ".jsonl")):
            by.setdefault(r["variant"], {}).setdefault(r["dataset"], {})[r.get("seed", 0)] = r
    dss = sorted({ds for _, ds in V} | {ds for v in RB.values() for ds in v})
    print(f"== truth {T}: {len(dss)} relations ({sum(ds in CLASS_A for ds in dss)} class A); "
          f"{len(V)} v5-family runs, price {'yes' if price else 'missing'}, rbhyb {'yes' if RB else 'missing'}, "
          f"automated {'yes' if AU else 'missing'}")
    loaded, mst = {}, {}
    for (v, ds), r in V.items():
        if ds not in loaded:
            loaded[ds] = AC.load(ds)
            mst[ds] = m_star(loaded[ds])
        r["_check"] = check(loaded[ds], r["certificate"], truth=True)
    res = {}
    for label, sel in (("all", dss), ("class A", [d for d in dss if d in CLASS_A]),
                       ("class B", [d for d in dss if d not in CLASS_A])):
        res[label] = k_rules(T, V, price, RB, AU, sel, label, mst)
    # K6, report only
    print(f"  K6 per relation (C certified; q questions; free: data-answered no; llm: LLM queries / candidates; attrs: "
          f"median attributes per question; partial: certified schemata of the design; fb: fallback design good for gold)")
    for ds in dss:
        cells = []
        for v in FAMILY:
            r = V.get((v, ds))
            if r is None:
                cells.append(f"{v} -")
                continue
            c = (f"{v} {'C' if r['certified'] else '-'} q{r['questions']} g{int(bool(r['gold_good']))} "
                 f"free{r['data_no']} partial {r['schemata_certified']}/{r['schemata']}")
            if v in ("v5", "v5u"):
                c += f" llm {r['llm_queries']}/{r['candidates']}"
            if "fb_gold_good" in r:
                c += f" fb{int(bool(r['fb_gold_good']))}"
            cells.append(c)
        r5 = V.get(("v5", ds))
        pr = price.get(f"{T}/{ds}")
        print(f"   {ds:18s} {'A' if ds in CLASS_A else 'B'} price {pr['price'] if pr else '-'} m*_r "
              f"{mst.get(ds, '-')} attrs {r5['attrs_median'] if r5 else '-'} | " + " | ".join(cells))
    unc = [r for (v, _), r in V.items() if v == "v5" and not r["certified"]]
    if unc:
        print(f"  K6 uncertified v5 runs: partial coverage {sum(r['schemata_certified'] for r in unc)}/"
              f"{sum(r['schemata'] for r in unc)} schemata; fallback good for gold "
              f"{sum(bool(r.get('fb_gold_good')) for r in unc)}/{len(unc)}")
    du = [V[("v5u", ds)]["questions"] - V[("v5", ds)]["questions"] for ds in dss
          if ("v5u", ds) in V and ("v5", ds) in V]
    print(f"  K6 v5u - v5: certified {sum(V[('v5u', d)]['certified'] for d in dss if ('v5u', d) in V)} vs "
          f"{sum(V[('v5', d)]['certified'] for d in dss if ('v5', d) in V)}; questions difference median {med(du)}")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v5dir", default="v5_fresh2")
    ap.add_argument("--answers", default="llm_fresh2")
    ap.add_argument("--model", default="q35", help="short model name of the answers directory, e.g. gptoss")
    a = ap.parse_args()
    res = {T: report(T, a.v5dir, a.answers, a.model) for T in ("full", "sure")}
    print("== verdicts (all relations; K2 must hold under both truths)")
    for k in ("K1", "K2", "K3", "K4", "K5"):
        print(f"  {k}: full {verdict(res['full']['all'][k])}, sure {verdict(res['sure']['all'][k])}; class A "
              f"{verdict(res['full']['class A'][k])}/{verdict(res['sure']['class A'][k])}, class B "
              f"{verdict(res['full']['class B'][k])}/{verdict(res['sure']['class B'][k])}")


if __name__ == "__main__":
    main()
