"""The confirmatory evaluation of v6f.py against the final rules V1-V5 of design note item 67, per truth, on all relations, class A
and class B apart.  Written before any method ran on batch 3, tested on the rows of the development relations and batch 2.

Inputs, each a comma-separated list of paths with {T} for the truth (defaults: batch 3, folder v6f_fresh3):
  --main   v6f.py at budget 1000 (the main form, its ablations, the LLM form)
  --b100   v6f.py at budget 100 (the main form)
  --v5     frozen v5.py at budget 1000 (v5, v5s, v5n)
  --ec2    ec2full.py at budget 1000 (ec2full, ec2full0, seeds 0-2)
  --rbhyb  auto_confirm.py at budget 100 (rbhyb, seeds 0-2)
  --price  price files (scripts/price_exact.py)
A missing input leaves its rule undetermined; a verdict on fewer relations than --expect is marked interim.
Usage (in confirm/):  CONFIRM_BATCH=3 python scripts/v6f_fresh3_report.py"""
import argparse, json, os, statistics as st, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.environ.setdefault("CONFIRM_ORACLE", "gold")
import auto_common as AC          # noqa: E402
from check_cert import check      # noqa: E402

MAIN = "v6s|lc+hone+kf+rl"
BUDGET = 1000
CLASS_A = {f"fresh3_{x}" for x in ("tpcc_order_line", "tpcc_stock", "tpcc_customer", "twitter_tweets", "synthea_encounters", "synthea_claims", "synthea_claims_transactions")}
# pre-listed (design note item 61, witness_fresh3.log, before any method ran): relations whose documented FDs the data violate, per truth
EXCUSED = {"full": {"fresh3_tpcc_order_line", "fresh3_hgnc", "fresh3_onspd", "fresh3_ourairports_airports", "fresh3_ourairports_frequencies"}, "sure": set()}


def rows(paths, T):
    out = []
    for p in filter(None, paths.split(",")):
        p = p.replace("{T}", T)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                out += [json.loads(x) for x in fh if x.strip()]
    return [r for r in out if "dataset" in r]


def q(r):
    return r["questions"] if r["certified"] else BUDGET


def verdict(ok):
    return "undetermined" if ok is None else "holds" if ok else "FAILS"


def spread(xs):
    return f"median {st.median(xs):.3f}, Q3 {st.quantiles(xs, n=4)[2]:.3f}, max {max(xs):.2f}" if len(xs) > 1 else str(xs)


def rules(T, M, V, EC, B100, RB, price, checked, dss, label, excused):
    res = {}
    A = {d: M[d] for d in dss if d in M}
    print(f"  -- {label}: {len(dss)} relations, main form on {len(A)}")
    # V1
    com = [d for d in A if d in V.get("v5", {})]
    x = [q(A[d]) / q(V["v5"][d]) for d in com]
    if com:
        ta, tb = sum(q(A[d]) for d in com), sum(q(V["v5"][d]) for d in com)
        res["V1"] = st.median(x) <= 0.9 and ta < tb
        print(f"    V1 over v5, n {len(com)}: {spread(x)}, wins {sum(y < 1 for y in x)}, losses {sum(y > 1 for y in x)}; total {ta} vs {tb} -> {verdict(res['V1'])}")
        print(f"       losses: {[(d, q(A[d]), q(V['v5'][d])) for d in com if q(A[d]) > q(V['v5'][d])]}")
    else:
        res["V1"] = None
        print("    V1 no v5 rows -> undetermined")
    # V2
    bad, ex = [], []
    for d, r in A.items():
        c = checked[d]
        if c["certified"] != bool(r["certified"]):
            bad.append(f"{d} checker disagrees")
        if r["certified"] and not c["sound"]:
            bad.append(f"{d} premises wrong yes {c['yes_wrong']} no {c['no_wrong']}")
        if r["certified"] and not r["gold_good"]:
            (ex if d in excused else bad).append(d)
    res["V2"] = None if not A else not bad
    print(f"    V2 runs {len(A)}, certified {sum(bool(r['certified']) for r in A.values())}; problems {bad or 'none'}; not good on pre-listed relations {ex or 'none'} -> {verdict(res['V2'])}")
    # V3
    v3 = []
    for v in ("ec2full", "ec2full0"):
        com = [d for d in A if len(EC.get(v, {}).get(d, {})) == 3]
        left = [d for d in A if d not in com]
        if not com:
            print(f"    V3 no {v} rows")
            v3.append(None)
            continue
        x = [q(A[d]) / st.median(q(s) for s in EC[v][d].values()) for d in com]
        v3.append(st.median(x) <= 1)
        print(f"    V3 over {v} (median of three seeds), n {len(com)}: {spread(x)}, wins {sum(y < 1 for y in x)}, losses {sum(y > 1 for y in x)}; without three seeds {left or 'none'}")
    res["V3"] = None if None in v3 else all(v3)
    print(f"    V3 -> {verdict(res['V3'])}")
    # V4
    o = [q(r) / price[f"{T}/{d}"]["price"] for d, r in A.items() if f"{T}/{d}" in price]
    low = [(d, r["refuted_answers"], price[f"{T}/{d}"]["m_star"]) for d, r in A.items() if r["certified"] and f"{T}/{d}" in price and r["refuted_answers"] < price[f"{T}/{d}"]["m_star"]]
    res["V4"] = None if not o else st.median(o) <= 1.6 and st.quantiles(o, n=4)[2] <= 2 and not low
    print(f"    V4 questions/price, n {len(o)}: {spread(o) if o else '-'}; total {sum(q(A[d]) for d in A)} over price {sum(price[f'{T}/{d}']['price'] for d in A if f'{T}/{d}' in price)}; below m* {low or 'none'} -> {verdict(res['V4'])}")
    # V5
    N = V.get("v5n", {})
    com = [d for d in A if d in N]
    if com:
        ca, cn = sum(bool(A[d]["certified"]) for d in com), sum(bool(N[d]["certified"]) for d in com)
        lim = {d: q(N[d]) + A[d]["cap"] + A[d]["max_questions"] - A[d]["max_no"] + A[d]["hone_no"] for d in com}
        ok = [d for d in com if q(A[d]) <= lim[d]]
        bound = ca >= cn and len(ok) >= 0.9 * len(com)
        print(f"    V5 certified {ca} >= v5n {cn}; bound holds on {len(ok)}/{len(com)}, fails on {sorted(set(com) - set(ok)) or 'none'}")
    else:
        bound = None
        print("    V5 no v5n rows")
    com = [d for d in dss if d in B100 and len(RB.get("rbhyb", {}).get(d, {})) == 3]
    if com:
        ga = sum(bool(B100[d]["gold_good"]) for d in com)
        gr = sum(st.median(int(bool(s["gold_good"])) for s in RB["rbhyb"][d].values()) >= 0.5 for d in com)
        k5 = ga >= gr
        runs = [s for d in com for s in RB["rbhyb"][d].values()]
        cert = [s for s in runs if s["certified"]]
        print(f"    V5 good on gold at the end of budget 100, n {len(com)}: main {ga}, rbhyb {gr}; rbhyb wrong posterior certificates {sum(not s['gold_good'] for s in cert)}/{len(cert)}")
    else:
        k5 = None
        print("    V5 no rbhyb rows or no rows at budget 100")
    res["V5"] = None if bound is None or k5 is None else bound and k5
    print(f"    V5 -> {verdict(res['V5'])}")
    return res


def report(T, a):
    os.environ["CONFIRM_TRUTH"] = T
    AC_T = lambda r: r.get("truth", T) == T and r.get("oracle", "gold") == "gold"
    R = {}
    for r in rows(a.main, T):
        assert AC_T(r), (r["variant"], r["dataset"])
        R.setdefault(r["variant"], {})[r["dataset"]] = r
    M = R.get(MAIN, {})
    V = {}
    for r in rows(a.v5, T):
        V.setdefault(r["variant"], {})[r["dataset"]] = r
    EC, RB = {}, {}
    for r in rows(a.ec2, T):
        if r["budget"] == BUDGET:
            EC.setdefault(r["variant"], {}).setdefault(r["dataset"], {})[r["seed"]] = r
    for r in rows(a.rbhyb, T):
        RB.setdefault(r["variant"], {}).setdefault(r["dataset"], {})[r.get("seed", 0)] = r
    B100 = {r["dataset"]: r for r in rows(a.b100, T) if r["variant"] == MAIN}
    price = {}
    for p in filter(None, a.price.split(",")):
        if os.path.exists(p):
            price.update(json.load(open(p, encoding="utf-8")))
    checked = {d: check(AC.load(d), r["certificate"], truth=True) for d, r in M.items()}
    dss = sorted(set(M) | set(a.datasets.split(",") if a.datasets else AC.FRESH))
    classa = CLASS_A if not a.class_a else set(a.class_a.split(","))
    excused = EXCUSED[T] if a.excused is None else set(a.excused.split(","))
    print(f"== truth {T}: {len(dss)} relations ({sum(d in classa for d in dss)} class A); main {len(M)}{'' if len(M) == a.expect else ' (interim)'}, price {len(price)}")
    res = {"all": rules(T, M, V, EC, B100, RB, price, checked, dss, "all", excused)}
    for label, sel in (("class A", [d for d in dss if d in classa]), ("class B", [d for d in dss if d not in classa])):
        res[label] = rules(T, M, V, EC, B100, RB, price, checked, sel, label, excused) if sel else {}
    print("  report only")
    w100 = [d for d, r in B100.items() if r["certified"]]
    print(f"    budget 100, main: certified {len(w100)}, good on gold {sum(bool(r['gold_good']) for r in B100.values())} of {len(B100)}; frozen v5 at 1000 within 100: {sum(bool(r['certified']) and r['questions'] <= 100 for r in V.get('v5', {}).values())}")
    for v in sorted(R, key=lambda v: (v.count("+"), v)):
        print(f"    {v:24s} n {len(R[v]):2d} total {sum(q(r) for r in R[v].values()):5d} certified {sum(bool(r['certified']) for r in R[v].values()):2d} good {sum(bool(r.get('gold_good')) for r in R[v].values()):2d}")
    for v in sorted(V):
        print(f"    {v:24s} n {len(V[v]):2d} total {sum(q(r) for r in V[v].values()):5d} certified {sum(bool(r['certified']) for r in V[v].values()):2d} good {sum(bool(r.get('gold_good')) for r in V[v].values()):2d}")
    print("    per relation: class, candidates, price, m*, main, v5, v5s, v5n, ec2full, ec2full0, attributes per question (median), good")
    for d in dss:
        p, r = price.get(f"{T}/{d}", {}), M.get(d)
        cell = lambda v: q(V[v][d]) if d in V.get(v, {}) else "-"
        ece = lambda v: st.median(q(s) for s in EC[v][d].values()) if len(EC.get(v, {}).get(d, {})) == 3 else "-"
        print(f"     {d:40s} {'A' if d in classa else 'B'} {p.get('candidates', '-'):>6} {p.get('price', '-'):>4} {p.get('m_star', '-'):>4} {q(r) if r else '-':>5} {cell('v5'):>5} {cell('v5s'):>5} {cell('v5n'):>5} {ece('ec2full'):>6} {ece('ec2full0'):>6} {r['attrs_median'] if r else '-':>4} {int(bool(r['gold_good'])) if r else '-'}")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--main", default="v6f_fresh3/main_{T}.jsonl")
    ap.add_argument("--b100", default="v6f_fresh3/b100_{T}.jsonl")
    ap.add_argument("--v5", default="v6f_fresh3/v5_{T}.jsonl")
    ap.add_argument("--ec2", default="v6f_fresh3/ec2_{T}.jsonl")
    ap.add_argument("--rbhyb", default="v6f_fresh3/rbhyb_{T}.jsonl")
    ap.add_argument("--price", default="v6f_fresh3/price_gold.json")
    ap.add_argument("--datasets", default="")
    ap.add_argument("--class-a", default="")
    ap.add_argument("--excused", default=None)
    ap.add_argument("--expect", type=int, default=23)
    a = ap.parse_args()
    res = {T: report(T, a) for T in ("full", "sure")}
    print("== verdicts: all (class A / class B)")
    for k in ("V1", "V2", "V3", "V4", "V5"):
        print(f"  {k}: " + "; ".join(f"{T} {verdict(res[T]['all'].get(k))} ({verdict(res[T]['class A'].get(k))} / {verdict(res[T]['class B'].get(k))})" for T in ("full", "sure")))


if __name__ == "__main__":
    main()
