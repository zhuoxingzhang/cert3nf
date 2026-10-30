"""
LaTeX rows for the tables of the paper (Sec. 6 and Appendix B) after the second confirmatory evaluation (design note,
items 32-34), from files kept in confirm:
  v5_dev/v5_<T>.jsonl            24 development relations, v5 family (item 32, gold oracle; v5s on tpcds_customer from
                                 v5tol_dev_c, where the eps = 0 rows reproduce item 32 field by field)
  v5_dev/price.json              their prices (item 32, T-e)
  v5_fresh2/v5_<T>.jsonl         12 confirmatory relations, v5 family (item 33); v5_fresh2/price.json their prices
  paper_src/<set>_<T>_rbhyb.jsonl, paper_src/<set>_<T>_auto.jsonl
                                 the posterior certificate (rbhyb, rbhyb0) and the fully automatic methods: dev12 =
                                 the first twelve development relations (item 19/23), dev24b = the twelve of the first
                                 confirmatory evaluation (item 28, now development), conf = the twelve of item 33
  v5tol_dev_c/, v5tol_fresh2/    the tolerant mode, mechanism c (item 34)
  ../e3/data/<ds>.json           attributes and rows per relation
Usage (in confirm): python scripts/paper_tables_v5.py > scripts/paper_tables_v5.out
"""
import json, os, statistics, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
E3 = os.path.join(HERE, "..", "e3", "data")
DEV = ["food", "hospital", "pricepaid", "ssb_customer", "ssb_date", "ssb_lineorder", "ssb_part", "ssb_supplier",
       "tpcds_core", "tpch_lineitem_orders", "tpch_orders_customer", "tpch_partsupp_part_supplier",
       "fresh_tpcds_customer", "fresh_ldbc_comment", "fresh_ldbc_study", "fresh_gtfs_at", "fresh_faa", "fresh_abs_mb",
       "fresh_sec_fsds", "fresh_scorecard_fos", "fresh_epa_aqs", "fresh_pums_ca", "fresh_chicago_crimes", "fresh_usda_sr"]
CONF = ["fresh_auctionmark", "fresh_seats", "fresh_tatp", "fresh_simplewiki",
        "fresh_chembl", "fresh_musicbrainz", "fresh_pluto", "fresh_fhrs", "fresh_geonames", "fresh_eia860",
        "fresh_stats19", "fresh_ghcn"]
CLASS_A = {"fresh_auctionmark", "fresh_seats", "fresh_tatp", "fresh_simplewiki"}
NAME = {"tpch_lineitem_orders": "tpch-lineitem", "tpch_orders_customer": "tpch-orders",
        "tpch_partsupp_part_supplier": "tpch-partsupp", "tpcds_core": "tpcds-core", "fresh_tpcds_customer": "tpcds-customer",
        "fresh_ldbc_comment": "ldbc-comment", "fresh_ldbc_study": "ldbc-study", "fresh_gtfs_at": "gtfs", "fresh_abs_mb": "abs",
        "fresh_sec_fsds": "sec", "fresh_scorecard_fos": "scorecard", "fresh_epa_aqs": "epa", "fresh_pums_ca": "pums",
        "fresh_chicago_crimes": "chicago", "fresh_usda_sr": "usda", "fresh_eia860": "eia-860", "fresh_ghcn": "ghcn-daily",
        "fresh_stats19": "stats19"}
# Relations on which the data violate a documented FD under the full truth, listed before any run (witness.py, item 32
# 10-28 16:25 for the development relations; item 33 pre-listing 10-28 23:35 for the confirmatory ones).  A certificate
# there covers Sigma*+ restricted to the FDs holding on r, so its design can miss the violated FD (the paper's assumption
# r |= Sigma* fails); the tables mark such designs with a dagger instead of a cross.  None under the sure truth.
VIOL = {"full": {"food", "pricepaid", "fresh_pums_ca", "fresh_seats", "fresh_simplewiki", "fresh_chembl",
                 "fresh_musicbrainz", "fresh_pluto"}, "sure": set()}
AUTO = [("hyfd", "HyFD"), ("trust", "trust"), ("clf", "classifier"), ("ours", "posterior alone"), ("A5", "rules"),
        ("L1", "LLM design"), ("L3", "normalizer"), ("upper", "every candidate")]
CROSS, DAGGER = r"\ding{55}", r"$\dagger$"


def rows(path):
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.endswith("\n") and line.strip():
                out.append(json.loads(line))
    return out


def med(xs):
    return statistics.median(xs) if xs else None


def fmt(x):
    if x is None:
        return "--"
    return f"{x:g}" if isinstance(x, float) and x != int(x) else f"{int(x)}"


def load_v5(T):
    V = {}
    for r in rows(os.path.join(HERE, "v5_dev", f"v5_{T}.jsonl")):
        V[(r["variant"], r["dataset"])] = r
    for r in rows(os.path.join(HERE, "v5tol_dev_c", f"v5tol_{T}.jsonl")):   # v5s on tpcds_customer (no LLM answers)
        if r["variant"] == "v5s" and r["designer_err"] == 0 and (r["variant"], r["dataset"]) not in V:
            V[(r["variant"], r["dataset"])] = r
    for r in rows(os.path.join(HERE, "v5_fresh2", f"v5_{T}.jsonl")):
        V[(r["variant"], r["dataset"])] = r
    return V


def load_price(T):
    P = {}
    for d in ("v5_dev", "v5_fresh2"):
        for k, v in json.load(open(os.path.join(HERE, d, os.environ.get("PRICE_FILE", "price.json")), encoding="utf-8")).items():
            t, ds = k.split("/", 1)
            if t == T:
                P[ds] = v
    return P


def load_ref(T, kind):
    R = {}
    for s in ("dev12", "dev24b", "conf"):
        names = [f"{s}_{T}_{kind}.jsonl"]
        if kind == "auto":                 # the normalizer L3 (item 37), run after the other automatic methods
            names += [f"{s}_{T}_L3.jsonl"]
        for name in names:
            path = os.path.join(HERE, "paper_src", name)
            if name.endswith("_L3.jsonl") and not os.path.exists(path):
                continue
            for r in rows(path):
                if r.get("error"):
                    r = dict(r, certified=False, gold_good=False, f1=0.0)
                R[(r["variant"], r["dataset"], r.get("seed", 0))] = r
    return R


def v5cell(r, T):
    if r is None:
        return "--"
    if not r.get("certified"):
        return "--"
    s = str(r["questions"])
    if not r.get("gold_good"):
        s += DAGGER if r["dataset"] in VIOL[T] else CROSS
    return s


def refcell(rs, T):
    c = [r for r in rs if r.get("certified")]
    if not rs:
        return "--"
    if not c:
        return "0"
    w = sum(1 for r in c if not r.get("gold_good") and r["dataset"] not in VIOL[T])
    d = sum(1 for r in c if not r.get("gold_good") and r["dataset"] in VIOL[T])
    return f"{len(c)}{CROSS * w}{DAGGER * d} ({fmt(med([r['questions'] for r in c]))})"


def cert_rows(dss, V, P, RB, label):
    print(f"%% ---- certificates ({label}) ----")
    for ds in dss:
        full, sure = V["full"], V["sure"]
        base = full.get(("v5n", ds)) or sure.get(("v5n", ds))
        cells = []
        for T in ("full", "sure"):
            cells += [v5cell(V[T].get((v, ds)), T) for v in ("v5", "v5s", "v5n")]
            cells.append(refcell([RB[T][k] for k in RB[T] if k[0] == "rbhyb" and k[1] == ds], T))
        name = NAME.get(ds, ds.replace("fresh_", "")) + (" (A)" if ds in CLASS_A else "")
        print(f"{name} & {base['candidates']:,} & {full[('v5n', ds)]['true']}/{sure[('v5n', ds)]['true']} & "
              f"{P['full'][ds]['price']}/{P['sure'][ds]['price']} & " + " & ".join(cells) + r"\\")


def data_rows(dss, V):
    print("%% ---- data table ----")
    for ds in dss:
        d = json.load(open(os.path.join(E3, f"{ds}.json"), encoding="utf-8"))
        name = NAME.get(ds, ds.replace("fresh_", "")) + (" (A)" if ds in CLASS_A else "")
        print(f"{name} & {len(d['attributes'])} & {d['instance']['rows']:,} & {V['full'][('v5n', ds)]['candidates']:,} & "
              f"{V['full'][('v5n', ds)]['true']} & {V['sure'][('v5n', ds)]['true']}\\\\")


def auto_rows(V, RB, AU):
    print("%% ---- automatic methods: good designs for gold / runs and macro F1; dev (23 relations with answers), conf ----")

    def cell(rs):
        if not rs:
            return "--", "--"
        per = {}
        for r in rs:
            per.setdefault(r["dataset"], []).append(r)
        good = sum(bool(r.get("gold_good")) for r in rs)
        f1 = statistics.mean(statistics.mean(r.get("f1") or 0.0 for r in v_) for v_ in per.values())
        return f"{good}/{len(rs)}", f"{f1:.2f}"

    def line(label, get):
        g, f = [], []
        for part in (DEV, CONF):
            for T in ("full", "sure"):
                a, b = cell(get(T, part))
                g.append(a); f.append(b)
        print(f"{label} & " + " & ".join(g) + " & " + " & ".join(f) + r"\\")

    for v, label in AUTO:
        line(label, lambda T, part, v=v: [AU[T][k] for k in AU[T] if k[0] == v and k[1] in part])
    print(r"\midrule")

    def relcell(rs, part):
        """relations whose median seed is good for gold / relations with runs, and the macro F1"""
        per = {}
        for r in rs:
            per.setdefault(r["dataset"], []).append(r)
        good = sum(1 for ds in per if med([bool(r.get("gold_good")) for r in per[ds]]) >= 0.5)
        f1 = statistics.mean(statistics.mean(r.get("f1") or 0.0 for r in v_) for v_ in per.values())
        return f"{good}/{len(per)}", f"{f1:.2f}"

    for label, v, src in (("posterior certificate", "rbhyb", RB), (r"posterior cert.\ w/o model", "rbhyb0", RB), (r"\ours", "v5", V)):
        g, f = [], []
        for part in (DEV, CONF):
            for T in ("full", "sure"):
                a, b = relcell([src[T][k] for k in src[T] if k[0] == v and k[1] in part], part)
                g.append(a); f.append(b)
        print(f"{label} & " + " & ".join(g) + " & " + " & ".join(f) + r"\   % per relation (median of seeds for the posterior certificate)")


def tol_rows():
    print("%% ---- tolerant mode (mechanism c): certificates and wrong certificates, relations x three seeds ----")
    TOL = {}
    for s, d in (("dev", "v5tol_dev_c"), ("conf", "v5tol_fresh2")):
        for T in ("full", "sure"):
            TOL[(s, T)] = [r for r in rows(os.path.join(HERE, d, f"v5tol_{T}.jsonl")) if r["dataset"] != "fresh_tpcds_customer"]

    def cnt(s, T, v, eps, stub=False):
        rs = [r for r in TOL[(s, T)] if r["variant"] == v and r["designer_err"] == eps and bool(r.get("persistent")) == stub]
        c = [r for r in rs if r.get("certified")]
        w = sum(1 for r in c if r.get("wrong_cert"))
        return len(c), w, len(rs)

    for eps in (0.02, 0.05):
        for v, label in (("v5", "trusting"), ("v5t", "tolerant"), ("v5st", "tolerant w/o model")):
            cells = []
            for s in ("dev", "conf"):
                for T in ("full", "sure"):
                    c, w, n = cnt(s, T, v, eps)
                    cells.append(f"{c} & {w}")
            print(f"{eps:g} & {label} & " + " & ".join(cells) + r"\\")
    cells = []
    for s in ("dev", "conf"):
        for T in ("full", "sure"):
            c, w, n = cnt(s, T, "v5t", 0.05, True)
            cells.append(f"{c} & {w}")
    print("0.05, stubborn & tolerant & " + " & ".join(cells) + r"\\")
    print("% runs per cell:", {k: cnt(k[0], k[1], "v5t", 0.02)[2] for k in TOL})
    print("% cost at eps 0 (certified relations, tolerant vs trusting; extra questions where both certify):")
    for s in ("dev", "conf"):
        for T in ("full", "sure"):
            t = {r["dataset"]: r for r in TOL[(s, T)] if r["variant"] == "v5t" and r["designer_err"] == 0}
            v = {r["dataset"]: r for r in TOL[(s, T)] if r["variant"] == "v5" and r["designer_err"] == 0}
            both = [ds for ds in t if t[ds].get("certified") and ds in v and v[ds].get("certified")]
            print(f"%   {s} {T}: v5t {sum(bool(r.get('certified')) for r in t.values())}/{len(t)}, "
                  f"v5 {sum(bool(r.get('certified')) for r in v.values())}/{len(v)}, "
                  f"extra median {fmt(med([t[ds]['questions'] - v[ds]['questions'] for ds in both]))} over {len(both)}")


def summary(V, P, RB, AU):
    print("%% ---- summary numbers for the text ----")
    for part, label in ((DEV, "dev"), (CONF, "conf")):
        for T in ("full", "sure"):
            get = lambda v: {ds: V[T][(v, ds)] for ds in part if (v, ds) in V[T]}
            v5, v5s, v5n, v5u = get("v5"), get("v5s"), get("v5n"), get("v5u")
            cert = lambda D: sorted(ds for ds in D if D[ds].get("certified"))
            c5, cs, cn, cu = cert(v5), cert(v5s), cert(v5n), cert(v5u)
            cs23 = [ds for ds in cs if ds in v5]
            both = [ds for ds in c5 if ds in cs]
            bothn = [ds for ds in c5 if ds in cn]
            bothu = [ds for ds in c5 if ds in cu]
            ratio = [v5[ds]["questions"] / P[T][ds]["price"] for ds in c5]
            print(f"% {label} {T}: v5 {len(c5)}/{len(v5)} v5s {len(cs)}/{len(v5s)} (on v5's relations {len(cs23)}/{len(v5)}) v5n {len(cn)}/{len(v5n)} v5u {len(cu)}/{len(v5u)}; "
                  f"q(v5)-q(v5s) median {fmt(med([v5[ds]['questions'] - v5s[ds]['questions'] for ds in both]))} (n {len(both)}); "
                  f"q(v5)-q(v5n) median {fmt(med([v5[ds]['questions'] - v5n[ds]['questions'] for ds in bothn]))} (n {len(bothn)}); "
                  f"q(v5)-q(v5u) median {fmt(med([v5[ds]['questions'] - v5u[ds]['questions'] for ds in bothu]))} (n {len(bothu)}); "
                  f"price ratio median {fmt(round(med(ratio), 2) if ratio else None)} range {fmt(round(min(ratio), 2) if ratio else None)}-{fmt(round(max(ratio), 2) if ratio else None)}")
            print(f"%   certified v5: {[NAME.get(d, d.replace('fresh_', '')) + ' ' + str(v5[d]['questions']) for d in c5]}")
            print(f"%   certified v5n only: {[NAME.get(d, d) for d in cn if d not in c5]}; v5 only: {[NAME.get(d, d) for d in c5 if d not in cn]}")
            print(f"%   v5s only: {[NAME.get(d, d) for d in cs if d not in c5]}; v5 only vs v5s: {[NAME.get(d, d) for d in c5 if d not in cs]}")
            wrong = [ds for ds in c5 if not v5[ds].get("gold_good")]
            print(f"%   v5 certified designs not good for gold: {wrong} (pre-listed: {[d for d in wrong if d in VIOL[T]]})")
            good = sum(bool(r.get("gold_good")) for r in v5.values())
            unc = [ds for ds in v5 if not v5[ds].get("certified")]
            part_cov = (sum(v5[ds]["schemata_certified"] for ds in unc), sum(v5[ds]["schemata"] for ds in unc))
            fb = sum(bool(v5[ds].get("gold_good")) for ds in unc)
            print(f"%   v5 good at stop {good}/{len(v5)}; uncertified {len(unc)}: partial coverage {part_cov[0]}/{part_cov[1]}, fallback good {fb}")
            q = [r.get("llm_queries", 0) / r["candidates"] for r in v5.values()]
            print(f"%   LLM query share: median {fmt(round(med(q), 2))}, min {fmt(round(min(q), 3))}, max {fmt(round(max(q), 2))}; "
                  f"free no (v5): {sorted(r.get('free', 0) for r in v5.values())}; v5n free: {sorted(r.get('free', 0) for r in v5n.values())}")
            print(f"%   discovery capped (b reached): {[NAME.get(d, d) for d in v5 if v5[d].get('capped')]}; "
                  f"disc questions median {fmt(med([r.get('disc_questions', 0) for r in v5.values()]))}")
            rb = [RB[T][k] for k in RB[T] if k[0] == "rbhyb" and k[1] in part]
            rb0 = [RB[T][k] for k in RB[T] if k[0] == "rbhyb0" and k[1] in part]
            for nm, rs in (("rbhyb", rb), ("rbhyb0", rb0)):
                c = [r for r in rs if r.get("certified")]
                w = [r for r in c if not r.get("gold_good")]
                print(f"%   {nm}: certificates {len(c)}/{len(rs)}, wrong for gold {len(w)} on {sorted({r['dataset'] for r in w})}, "
                      f"good at stop {sum(bool(r.get('gold_good')) for r in rs)}/{len(rs)}; "
                      f"relations with median-of-seeds good: {sum(1 for ds in part if med([bool(r.get('gold_good')) for r in rs if r['dataset'] == ds] or [0]) >= 0.5)}")
                both = [r for r in c if (("v5", r["dataset"]) in V[T]) and V[T][("v5", r["dataset"])].get("certified")]
                print(f"%     where both certify: v5 - {nm} questions median {fmt(med([V[T][('v5', r['dataset'])]['questions'] - r['questions'] for r in both]))} (n {len(both)})")
            up = [AU[T][k] for k in AU[T] if k[0] == "upper" and k[1] in part]
            print(f"%   upper good {sum(bool(r.get('gold_good')) for r in up)}/{len(up)}; not good on {sorted({r['dataset'] for r in up if not r.get('gold_good')})}; "
                  f"upper questions median {fmt(med([r['questions'] for r in up]))}")


def main():
    V = {T: load_v5(T) for T in ("full", "sure")}
    P = {T: load_price(T) for T in ("full", "sure")}
    RB = {T: load_ref(T, "rbhyb") for T in ("full", "sure")}
    AU = {T: load_ref(T, "auto") for T in ("full", "sure")}
    # sanity: every v5 row that the K1 check passed; the dagger is used only on pre-listed relations
    for T in ("full", "sure"):
        for ds in DEV + CONF:
            d = json.load(open(os.path.join(E3, f"{ds}.json"), encoding="utf-8"))
            viol = d.get("truth_fds_violated_by_data") or []
            if T == "full" and bool(viol) != (ds in VIOL["full"]):
                print(f"% WARNING: violation list mismatch on {ds}: json {len(viol)} vs VIOL {ds in VIOL['full']}", file=sys.stderr)
    cert_rows(CONF, V, P, RB, "confirmatory, Table 3")
    cert_rows(DEV, V, P, RB, "development, appendix")
    data_rows(DEV + CONF, V)
    auto_rows(V, RB, AU)
    tol_rows()
    summary(V, P, RB, AU)


if __name__ == "__main__":
    main()
