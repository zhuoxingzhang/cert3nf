"""
LaTeX rows and numbers for the paper on v6f (design note item 70), from files kept in confirm/, recounted from the raw rows:
  v6f_fresh3/        batch 3, the 23 confirmatory relations: main, b100, err, v5, rbhyb, ec2, L3, price_gold.json
  v6f_fresh3_extra/  theta_{rep,raw}_<T>, ec2hyb_<T>, designer69/ (item 69)
  v6f_runs/          the 35 development relations: main_*, err_*, th01_*, price_dev.json, scale66/
  paper_src/         the posterior certificate on the development relations (rbhyb, rbhyb0)
A missing input is named and its part skipped.  Budget 1000 runs stand for budget 100 runs: a run certified within 100 answers is the same
run (checked here on the rows at budget 100), and a run that needs more shows its answers in parentheses.
Usage (in confirm/): python scripts/paper_tables_v6f.py > scripts/paper_tables_v6f.out
"""
import json, os, statistics as st, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(HERE)
C = "e2a6af907596"
MAIN, LLM = "v6s|lc+hone+kf+rl", "v6|lc+hone+kf+rl"
TRUTHS = ("full", "sure")
CROSS, DAGGER = r"\ding{55}", r"$\dagger$"
B3 = ["fresh3_" + x for x in ("tpcc_order_line", "tpcc_stock", "tpcc_customer", "twitter_tweets", "synthea_encounters", "synthea_claims", "synthea_claims_transactions",
                              "companieshouse", "fec_candidate", "fec_committee", "fec_linkage", "gleif", "hgnc", "nppes_npidata", "onspd", "openpayments_general", "openpayments_profile",
                              "ourairports_airports", "ourairports_frequencies", "ourairports_navaids", "stackexchange_postlinks", "stackexchange_posts", "stackexchange_users")]
CLASS_A = set(B3[:7])
DEV = ["food", "hospital", "pricepaid", "ssb_customer", "ssb_date", "ssb_lineorder", "ssb_part", "ssb_supplier", "tpcds_core", "tpch_lineitem_orders", "tpch_orders_customer",
       "tpch_partsupp_part_supplier", "fresh_ldbc_comment", "fresh_ldbc_study", "fresh_gtfs_at", "fresh_faa", "fresh_abs_mb", "fresh_sec_fsds", "fresh_scorecard_fos", "fresh_epa_aqs",
       "fresh_pums_ca", "fresh_chicago_crimes", "fresh_usda_sr"]
B2 = ["fresh_auctionmark", "fresh_seats", "fresh_tatp", "fresh_simplewiki", "fresh_chembl", "fresh_musicbrainz", "fresh_pluto", "fresh_fhrs", "fresh_geonames", "fresh_eia860",
      "fresh_stats19", "fresh_ghcn"]
NAME = {"tpch_lineitem_orders": "tpch-lineitem", "tpch_orders_customer": "tpch-orders", "tpch_partsupp_part_supplier": "tpch-partsupp", "tpcds_core": "tpcds-core",
        "fresh_ldbc_comment": "ldbc-comment", "fresh_ldbc_study": "ldbc-study", "fresh_gtfs_at": "gtfs", "fresh_abs_mb": "abs", "fresh_sec_fsds": "sec", "fresh_scorecard_fos": "scorecard",
        "fresh_epa_aqs": "epa", "fresh_pums_ca": "pums", "fresh_chicago_crimes": "chicago", "fresh_usda_sr": "usda", "fresh_eia860": "eia-860", "fresh_ghcn": "ghcn-daily",
        "fresh3_tpcc_order_line": "tpcc-orderline", "fresh3_tpcc_stock": "tpcc-stock", "fresh3_tpcc_customer": "tpcc-customer", "fresh3_twitter_tweets": "tweets",
        "fresh3_synthea_encounters": "syn-encounters", "fresh3_synthea_claims": "syn-claims", "fresh3_synthea_claims_transactions": "syn-trans",
        "fresh3_companieshouse": "companies", "fresh3_fec_candidate": "fec-cand", "fresh3_fec_committee": "fec-comm", "fresh3_fec_linkage": "fec-link", "fresh3_nppes_npidata": "nppes",
        "fresh3_openpayments_general": "pay-general", "fresh3_openpayments_profile": "pay-profile", "fresh3_ourairports_airports": "air-airports",
        "fresh3_ourairports_frequencies": "air-freq", "fresh3_ourairports_navaids": "air-navaids", "fresh3_stackexchange_postlinks": "se-postlinks",
        "fresh3_stackexchange_posts": "se-posts", "fresh3_stackexchange_users": "se-users"}
# the data violate a documented FD of the full truth, listed before any run (witness.py; items 32, 33, 61)
VIOL = {"full": {"food", "pricepaid", "fresh_pums_ca", "fresh_seats", "fresh_simplewiki", "fresh_chembl", "fresh_musicbrainz", "fresh_pluto",
                 "fresh3_tpcc_order_line", "fresh3_hgnc", "fresh3_onspd", "fresh3_ourairports_airports", "fresh3_ourairports_frequencies"}, "sure": set()}


def name(d):
    return NAME.get(d, d.replace("fresh3_", "").replace("fresh_", "")).replace("_", "-")


def rows(path):
    if not os.path.exists(path):
        print(f"% MISSING {path}")
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def by_variant(rs, keep=None):
    out = defaultdict(dict)
    for r in rs:
        if keep is None or keep(r):
            out[r["variant"]][r["dataset"]] = r
    return out


def seeded(rs, var):
    out = defaultdict(list)
    for r in rs:
        if r["variant"] == var:
            out[r["dataset"]].append(r)
    return out


def within(r, b):
    return bool(r) and bool(r.get("certified")) and r["questions"] <= b


def within3(rs, b):
    return sum(within(r, b) for r in rs) >= 2


def cell(r, T):
    """the answers until the certificate, in parentheses above 100; -- no certificate within the budget of the run"""
    if not r or not r.get("certified"):
        return "--"
    s = f"{r['questions']}"
    if not r.get("gold_good"):
        s += DAGGER if r["dataset"] in VIOL[T] else CROSS
    return s if r["questions"] <= 100 else f"({s})"


def cell3(rs, T):
    """three seeds: the median answers, where a seed without a certificate counts as more than any budget, so -- if
    fewer than two seeds certify; a relation counts within B (within3) exactly when this median is at most B"""
    assert len(rs) == 3, (len(rs), rs and rs[0]["dataset"])
    c = [r for r in rs if r.get("certified")]
    if len(c) < 2:
        return "--"
    q = sorted(r["questions"] for r in c)[1]
    s = f"{q:g}"
    bad = sum(not r.get("gold_good") for r in c)
    if bad * 2 >= len(c):
        s += DAGGER if rs[0]["dataset"] in VIOL[T] else CROSS
    return s if q <= 100 else f"({s})"


def rank_marks(cells, cols, best=max):
    """the last rows of Tab. cert and Tab. cert-dev: underline the most relations among the cells at cols and wave-underline
    the second most (ulem), ties sharing a mark; empty cells, -- and wrong certificates are not ranked"""
    def val(c):
        if c in ("", "--") or CROSS in c:
            return None
        return int(c.replace(DAGGER, "").strip("()").split("/")[0])
    ranked = sorted({val(cells[i]) for i in cols} - {None}, reverse=best is max)
    out = list(cells)
    for i in cols:
        x = val(cells[i])
        if x is not None and x == ranked[0]:
            out[i] = rf"\uline{{{cells[i]}}}"
        elif x is not None and len(ranked) > 1 and x == ranked[1]:
            out[i] = rf"\uwave{{{cells[i]}}}"
    return out


# ---- load ----
D = {}
for T in TRUTHS:
    m3 = rows(f"v6f_fresh3/main_{T}.jsonl")
    v3 = rows(f"v6f_fresh3/v5_{T}.jsonl")
    m1 = rows(f"v6f_runs/main_{C}_dev_{T}.jsonl") + rows(f"v6f_runs/main_{C}_b2_{T}.jsonl")
    theta = rows(f"v6f_fresh3_extra/theta_rep_{T}.jsonl")
    raw = rows(f"v6f_fresh3_extra/theta_raw_{T}.jsonl")
    D[T] = dict(main3=by_variant(m3), v53=by_variant(v3), main1=by_variant(m1), b100=by_variant(rows(f"v6f_fresh3/b100_{T}.jsonl")),
                ec2=rows(f"v6f_fresh3/ec2_{T}.jsonl"), rb=rows(f"v6f_fresh3/rbhyb_{T}.jsonl"), L3=rows(f"v6f_fresh3/L3_{T}.jsonl"),
                err3=rows(f"v6f_fresh3/err_{T}.jsonl"), err1=rows(f"v6f_runs/err_{C}_dev_{T}.jsonl") + rows(f"v6f_runs/err_{C}_b2_{T}.jsonl"),
                ec2hyb=rows(f"v6f_fresh3_extra/ec2hyb_{T}.jsonl"), theta=theta, raw=raw,
                th01=rows(f"v6f_runs/th01_{C}_{T}.jsonl"))
PRICE = {}
for f in ("v6f_runs/price_dev.json", "v6f_runs/price_b2.json", "v6f_fresh3/price_gold.json"):
    for k, v in json.load(open(f, encoding="utf-8")).items():
        PRICE[k] = v["price"]


def price(T, d):
    return PRICE[f"{T}/{d}"]


# budget 100 is budget 1000 cut off, on the rows of batch 3
for T in TRUTHS:
    for d in B3:
        a, b = D[T]["main3"][MAIN][d], D[T]["b100"][MAIN][d]
        assert within(a, 100) == bool(b.get("certified")) and (not within(a, 100) or a["questions"] == b["questions"]), (T, d)
        assert a["code"] == C and a["budget"] == 1000 and a["oracle"] == "gold", (T, d)

# ---- certified within B, per set and truth ----
print("%% ---- relations certified within B answers ----")
BS = (25, 50, 75, 100, 150, 200, 300, 500, 1000)
for T in TRUTHS:
    print(f"% truth {T}, batch 3 (23 relations); seeded methods: at least two of three seeds")
    print("%   B            " + " ".join(f"{b:5d}" for b in BS))
    m, v = D[T]["main3"], D[T]["v53"]
    lines = [("price", lambda b: sum(price(T, d) <= b for d in B3)), ("Cert3NF", lambda b: sum(within(m[MAIN][d], b) for d in B3)), ("with LLM", lambda b: sum(within(m[LLM][d], b) for d in B3)),
             ("v5", lambda b: sum(within(v["v5"][d], b) for d in B3)), ("v5s", lambda b: sum(within(v["v5s"][d], b) for d in B3)), ("w/o advisor", lambda b: sum(within(v["v5n"][d], b) for d in B3))]
    for var in sorted({r["variant"] for r in D[T]["ec2"]}):
        sd = seeded(D[T]["ec2"], var)
        if len(sd) == 23:
            lines.append((var, lambda b, sd=sd: sum(within3(sd[d], b) for d in B3)))
    for var in sorted({r["variant"] for r in D[T]["ec2hyb"]} | {"rbhyb"}):
        src = D[T]["rb"] if var == "rbhyb" else D[T]["ec2hyb"]
        sd = seeded(src, var)
        if len(sd) == 23:
            lines.append((var + " (b100)", lambda b, sd=sd: sum(within3(sd[d], b) for d in B3)))
    for lab, fn in lines:
        print(f"%   {lab:14s} " + " ".join(f"{fn(b):5d}" for b in BS))
    print(f"% truth {T}, all 58 relations")
    m1 = D[T]["main1"]
    al = lambda var, b: sum(within(m1[var].get(d), b) for d in DEV + B2)
    v3 = {"v5s": v["v5s"], "v5n": v["v5n"]}
    print("%   price          " + " ".join(f"{sum(price(T, d) <= b for d in DEV + B2 + B3):5d}" for b in BS))
    print("%   Cert3NF        " + " ".join(f"{al(MAIN, b) + sum(within(m[MAIN][d], b) for d in B3):5d}" for b in BS))
    print("%   with LLM       " + " ".join(f"{al(LLM, b) + sum(within(m[LLM][d], b) for d in B3):5d}" for b in BS))
    print("%   v5s            " + " ".join(f"{al('v5s', b) + sum(within(v['v5s'][d], b) for d in B3):5d}" for b in BS))
    print("%   w/o advisor    " + " ".join(f"{al('v5n', b) + sum(within(v['v5n'][d], b) for d in B3):5d}" for b in BS))

# ---- answers against the price ----
print("%% ---- answers against the price, without a budget, certified runs ----")
for T in TRUTHS:
    m, v = D[T]["main3"], D[T]["v53"]
    for lab, get in (("Cert3NF", lambda d: m[MAIN][d]), ("with LLM", lambda d: m[LLM][d]), ("v5s", lambda d: v["v5s"][d]), ("w/o advisor", lambda d: v["v5n"][d])):
        rs = [get(d) for d in B3 if get(d).get("certified")]
        ratio = sorted(r["questions"] / price(T, r["dataset"]) for r in rs)
        tot = sum(get(d)["questions"] for d in B3)
        print(f"% {T} batch 3 {lab:12s}: certified {len(rs)}/23, total answers {tot}, above the price {tot - sum(price(T, d) for d in B3)}, ratio median {st.median(ratio):.3f}, Q3 {st.quantiles(ratio, n=4)[2]:.3f}, max {ratio[-1]:.2f}")
    for var in sorted({r["variant"] for r in D[T]["ec2"]}):
        sd = seeded(D[T]["ec2"], var)
        if len(sd) != 23:
            continue
        q = {d: st.median(r["questions"] for r in sd[d]) for d in B3}
        ratio = sorted(q[d] / price(T, d) for d in B3)
        pair = sorted(m[MAIN][d]["questions"] / q[d] for d in B3)
        print(f"% {T} batch 3 {var:12s}: certified runs {sum(bool(r.get('certified')) for x in sd.values() for r in x)}/69, total answers {sum(q.values()):g}, above the price {sum(q.values()) - sum(price(T, d) for d in B3):g}, ratio median {st.median(ratio):.3f}, Q3 {st.quantiles(ratio, n=4)[2]:.3f}; Cert3NF over it: median {st.median(pair):.3f}, wins {sum(x < 1 for x in pair)}, ties {sum(x == 1 for x in pair)}, losses {sum(x > 1 for x in pair)}")
    m1 = D[T]["main1"]
    for lab, part in (("dev", DEV), ("b2", B2), ("dev+b2", DEV + B2)):
        rs = [m1[MAIN][d] for d in part if m1[MAIN][d].get("certified")]
        ratio = sorted(r["questions"] / price(T, r["dataset"]) for r in rs)
        print(f"% {T} {lab:6s} Cert3NF: certified {len(rs)}/{len(part)}, within 100 {sum(r['questions'] <= 100 for r in rs)}, ratio median {st.median(ratio):.3f}, Q3 {st.quantiles(ratio, n=4)[2]:.3f}, max {ratio[-1]:.2f}, total {sum(m1[MAIN][d]['questions'] for d in part)}, price {sum(price(T, d) for d in part)}")

# ---- EC^2 (original), Cert3NF with the EC^2 order (same pool), Cert3NF ----
print("%% ---- what the framework and the order give EC^2, batch 3: runs or relations ----")
for T in TRUTHS:
    m = D[T]["main3"][MAIN]
    print(f"% truth {T}: method: within 50, within 100 (relations, at least two of three seeds), good on gold (median seed), wrong certificates, lossless among the runs not certified within 100")
    print(f"%   Cert3NF: {sum(within(m[d], 50) for d in B3)}, {sum(within(m[d], 100) for d in B3)}, {sum(bool(D[T]['b100'][MAIN][d]['gold_good']) for d in B3)}, wrong {sum(bool(m[d].get('wrong_cert')) for d in B3)}, lossless {sum(bool(D[T]['b100'][MAIN][d]['gold_lossless']) for d in B3 if not within(m[d], 100))}/{sum(not within(m[d], 100) for d in B3)}")
    for src, var in ((D[T]["ec2"], "ec2full"), (D[T]["ec2"], "ec2full0"), (D[T]["ec2hyb"], "ec2hyb"), (D[T]["ec2hyb"], "ec2hyb0"), (D[T]["rb"], "rbhyb"), (D[T]["rb"], "rbhyb0")):
        sd = seeded(src, var)
        if len(sd) != 23:
            print(f"%   {var}: not complete ({len(sd)} relations)")
            continue
        good = sum(st.median(bool(r.get("gold_good")) for r in sd[d]) >= 0.5 for d in B3)
        runs = [r for x in sd.values() for r in x]
        wrong = sum(bool(r.get("certified")) and not r.get("gold_good") and r["dataset"] not in VIOL[T] for r in runs)
        unc = [r for r in runs if not within(r, 100)]
        urel = [d for d in B3 if not within3(sd[d], 100)]          # relations, by the median of three seeds
        lrel = sum(st.median(bool(r.get("gold_lossless")) for r in sd[d]) >= 0.5 for d in urel)
        print(f"%   {var}: {sum(within3(sd[d], 50) for d in B3)}, {sum(within3(sd[d], 100) for d in B3)}, good {good}, certified runs {sum(bool(r.get('certified')) for r in runs)}/69, wrong {wrong}, lossless {sum(bool(r.get('gold_lossless')) for r in unc)}/{len(unc)} runs, {lrel}/{len(urel)} relations (median seed)")

# ---- Tab. cert, batch 3 ----
print("%% ---- Tab. cert: confirmatory relations ----")
for d in B3:
    cells = []
    for T in TRUTHS:
        m, v = D[T]["main3"], D[T]["v53"]
        th = {r["dataset"]: r for r in D[T]["theta"] if r.get("theta") == 0.1 and r["variant"] == MAIN}
        th.update({r["dataset"]: r for r in D[T]["raw"] if r.get("theta") == 0.1 and r["variant"] == MAIN})
        cells += [str(m[MAIN][d]["true"]), str(price(T, d)), cell(m[MAIN][d], T), cell(m[LLM][d], T), cell(v["v5n"][d], T),
                  cell3(seeded(D[T]["ec2"], "ec2full0").get(d, []), T), cell3(seeded(D[T]["rb"], "rbhyb").get(d, []), T),
                  cell3(seeded(D[T]["ec2hyb"], "ec2hyb").get(d, []), T), cell(th.get(d), T)]
    print(f"{name(d)}{' (A)' if d in CLASS_A else ''} & {D['full']['main3'][MAIN][d]['candidates']:,} & " + " & ".join(cells) + r"\\")

# ---- Tab. cert-dev: development relations, as in the v5 paper, posterior from paper_src ----
print("%% ---- Tab. cert-dev: development relations ----")
RB1 = {}
for T in TRUTHS:
    RB1[T] = defaultdict(list)
    for s in ("dev12", "dev24b", "conf"):
        for r in rows(f"paper_src/{s}_{T}_rbhyb.jsonl"):
            if r["variant"] == "rbhyb":
                RB1[T][r["dataset"]].append(r)
for d in DEV + B2:
    cells = []
    for T in TRUTHS:
        m1 = D[T]["main1"]
        cells += [str(m1[MAIN][d]["true"]), str(price(T, d)), cell(m1[MAIN][d], T), cell(m1[LLM][d], T), cell(m1["v5n"][d], T), cell3(RB1[T][d], T)]
    print(f"{name(d)} & {D['full']['main1'][MAIN][d]['candidates']:,} & " + " & ".join(cells) + r"\\")

# ---- Tab. tol ----
print("%% ---- Tab. tol: certificates and wrong certificates; budget 1000, and within 100 answers in brackets ----")
PATH = {"dev": "v6f_fresh3_extra/designer69/dev/designer_{}_" + C + "_dev_{}.jsonl", "b2": "v6f_fresh3_extra/designer69/b2/designer_{}_" + C + "_b2_{}.jsonl", "b3": "v6f_fresh3_extra/designer69/b3/designer_{}_{}.jsonl"}
for label, care, eps, file_ in (("0.02 trusting", False, 0.02, None), ("0.02 careful", True, 0.02, None), ("0.05 trusting", False, 0.05, None), ("0.05 careful", True, 0.05, None),
                                ("0.05 repeated", True, 0.05, "rep"), ("0.02 phi .25", True, 0.02, "rho0.25"), ("0.02 phi .5", True, 0.02, "rho0.5"), ("0.05 phi .25", True, 0.05, "rho0.25"), ("0.05 phi .5", True, 0.05, "rho0.5")):
    cells = []
    pooled = [0, 0, 0, 0]
    for part in ("dev", "b2", "b3"):
        for T in TRUTHS:
            if file_:
                rs = rows(PATH[part].format(file_, T))
            elif part == "b3":
                rs = D[T]["err3"]
            else:
                rs = [r for r in D[T]["err1"] if r["dataset"] in (DEV if part == "dev" else B2)]
            rs = [r for r in rs if r["variant"] == MAIN and bool(r.get("careful")) == care and r["designer_err"] == eps]
            c = [r for r in rs if r.get("certified")]
            w = sum(bool(r.get("wrong_cert")) for r in c)
            c1 = [r for r in c if r["questions"] <= 100]
            w1 = sum(bool(r.get("wrong_cert")) for r in c1)
            for i, x in enumerate((len(c), w, len(c1), w1)):
                pooled[i] += x
            cells.append(f"{len(c1)} & {w1}")
    print(f"{label} & " + " & ".join(cells) + rf"\\  % budget 1000 pooled: {pooled[0]} cert, {pooled[1]} wrong ({pooled[1] / max(pooled[0], 1):.3f}); within 100 pooled: {pooled[2]} cert, {pooled[3]} wrong ({pooled[3] / max(pooled[2], 1):.3f})")

# ---- careful with an exact designer ----
print("%% ---- careful mode with a designer who never errs ----")
for T in TRUTHS:
    e = {r["dataset"]: r for r in D[T]["err3"] + D[T]["err1"] if r["variant"] == MAIN and r.get("careful") and r["designer_err"] == 0}
    b = {**D[T]["main1"][MAIN], **D[T]["main3"][MAIN]}
    ratio = sorted(e[d]["questions"] / b[d]["questions"] for d in e)
    cr = sorted(e[d]["questions"] / price(T, d) for d in e)
    print(f"% {T}: {len(e)} relations, certified {sum(bool(r.get('certified')) for r in e.values())}, within 100 {sum(within(r, 100) for r in e.values())} (batch 3: {sum(within(e[d], 100) for d in B3)}), careful/trusting median {st.median(ratio):.2f}, min {ratio[0]:.2f}, max {ratio[-1]:.2f}; careful/price median {st.median(cr):.2f}")

# ---- Tab. scale ----
print("%% ---- Tab. scale: medians over the seeds of each size ----")
S = rows("v6f_runs/scale66/rows.jsonl")
sp = json.load(open("scale/price.json", encoding="utf-8")) if os.path.exists("scale/price.json") else {}
if S:
    v6 = {r["dataset"]: r for r in S if r["variant"] == MAIN}
    v5s = {r["dataset"]: r for r in S if r["variant"] == "v5s"}
    print(f"% certified {sum(bool(r.get('certified')) for r in v6.values())}/{len(v6)}; total {sum(r['questions'] for r in v6.values())} vs v5s {sum(r['questions'] for r in v5s.values())}")
    v5n = {r["dataset"]: r for r in rows("scale/v5.jsonl") if r["variant"] == "v5n"}
    groups = defaultdict(list)
    for d in v6:
        n, share = d.split("_")[1:3]
        groups[(int(n[1:]), int(share[1:]))].append(d)
    for (n, share), ds in sorted(groups.items()):
        med = lambda f: st.median(f(d) for d in ds)
        print(f"{n} & {share / 100:.1f} & {med(lambda d: v6[d]['candidates']):,.0f} & {med(lambda d: v6[d]['true']):.0f} & {med(lambda d: sp[d]['price']):.0f} & {med(lambda d: v6[d]['questions']):.0f} & {med(lambda d: v6[d]['questions'] / sp[d]['price']):.2f} & {med(lambda d: v5n[d]['questions']):.0f}\\\\")

    def ranks(xs):
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        out = [0.0] * len(xs)
        i = 0
        while i < len(xs):
            j = i
            while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
                j += 1
            for k in range(i, j + 1):
                out[order[k]] = (i + j) / 2
            i = j + 1
        return out

    def spearman(a, b):
        ra, rb = ranks(a), ranks(b)
        ma, mb = st.mean(ra), st.mean(rb)
        return sum((x - ma) * (y - mb) for x, y in zip(ra, rb)) / (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5

    ds = sorted(v6)
    q = [v6[d]["questions"] for d in ds]
    ratio = sorted(v6[d]["questions"] / sp[d]["price"] for d in ds)
    r5 = sorted(v5s[d]["questions"] / sp[d]["price"] for d in ds)
    print(f"% ratio to price over the 18: median {st.median(ratio):.2f}, Q3 {st.quantiles(ratio, n=4)[2]:.2f}, max {ratio[-1]:.2f}; v5s median {st.median(r5):.2f}, max {r5[-1]:.2f}; max price {max(sp[d]['price'] for d in ds)}, within 100 {sum(x <= 100 for x in q)}")
    print(f"% Spearman of the answers: price {spearman(q, [sp[d]['price'] for d in ds]):.2f}, true {spearman(q, [v6[d]['true'] for d in ds]):.2f}, candidates {spearman(q, [v6[d]['candidates'] for d in ds]):.2f}; largest candidates {max(v6[d]['candidates'] for d in ds):,}")

# ---- without a budget, within the budget ----
print("%% ---- how far the answers go ----")
for T in TRUTHS:
    b3, b1 = D[T]["main3"][MAIN], D[T]["main1"][MAIN]
    for lab, part, src in (("batch 3", B3, b3), ("dev+b2", DEV + B2, b1), ("all 58", DEV + B2 + B3, {**b1, **b3})):
        q = sorted(src[d]["questions"] for d in part)
        ratio = sorted(src[d]["questions"] / price(T, d) for d in part)
        r100 = sorted(src[d]["questions"] / price(T, d) for d in part if within(src[d], 100))
        print(f"% {T} {lab}: certified {sum(bool(src[d].get('certified')) for d in part)}/{len(part)}, answers median {st.median(q):g}, max {q[-1]}, at most 200: {sum(x <= 200 for x in q)}, at most 250: {sum(x <= 250 for x in q)}; ratio median {st.median(ratio):.2f}, above 2x: {sum(x > 2 for x in ratio)}, above 3x: {sum(x > 3 for x in ratio)}; within 100 only: median {st.median(r100):.2f} over {len(r100)}")

# ---- designs that run out of the budget ----
print("%% ---- designs at the end of the budget 100 ----")
for T in TRUTHS:
    for lab, rs in (("batch 3", D[T]["b100"][MAIN].values()), ("dev+b2", [r for r in rows(f"v6f_runs/b100_{C}_dev_{T}.jsonl") + rows(f"v6f_runs/b100_{C}_b2_{T}.jsonl") if r["variant"] == MAIN])):
        u = [r for r in rs if not r.get("certified")]
        print(f"% {T} {lab}: uncertified {len(u)}, lossless {sum(bool(r['gold_lossless']) for r in u)}, schemata certified {sum(r['schemata_certified'] for r in u)} of {sum(r['schemata'] for r in u)}; good at the end {sum(bool(r['gold_good']) for r in rs)} of {len(list(rs))}")

# ---- where the answers go, batch 3 ----
print("%% ---- kinds of answers, batch 3, without a budget ----")
for T in TRUTHS:
    m = D[T]["main3"][MAIN]
    find = sum(m[d]["qx_questions"] + m[d]["hone_questions"] + m[d]["guess_questions"] + m[d]["reuse_questions"] for d in B3)
    mx = sum(m[d]["max_questions"] for d in B3)
    tot = sum(m[d]["questions"] for d in B3)
    print(f"% {T} Cert3NF: total {tot}, finding {find}, maximal sets {mx}, other candidates {tot - find - mx}, secs {sum(m[d]['secs'] for d in B3):.0f}")
    for var in sorted({r["variant"] for r in D[T]["ec2"]}):
        sd = seeded(D[T]["ec2"], var)
        if len(sd) != 23:
            continue
        pick = {d: sorted(sd[d], key=lambda r: r["questions"])[1] for d in B3}
        print(f"% {T} {var}: total {sum(r['questions'] for r in pick.values())}, finding {sum(r['qx_questions'] for r in pick.values())}, maximal sets {sum(r['max_questions'] for r in pick.values())}, other candidates {sum(r['cand_questions'] for r in pick.values())}, secs {sum(r['secs'] for r in pick.values()):.0f}, ESS median of medians {st.median(r['ess_median'] for r in pick.values() if r.get('ess_median') is not None):g}")

# ---- Fig. budget, batch 3 ----
print("%% ---- Fig. budget: confirmatory relations ----")


def curve(vals, n):
    vals = sorted(v for v in vals if v is not None)
    pts = [(10, sum(v <= 10 for v in vals) / n)]
    for x in sorted(set(v for v in vals if 10 < v < 1000)):
        pts.append((x, sum(v <= x for v in vals) / n))
    pts.append((1000, sum(v <= 1000 for v in vals) / n))
    return " ".join(f"({int(x)},{y:.3f})" for x, y in pts)


for T in TRUTHS:
    m, v = D[T]["main3"], D[T]["v53"]
    care = {r["dataset"]: r for r in D[T]["err3"] if r["variant"] == MAIN and r.get("careful") and r["designer_err"] == 0}
    q = lambda r: r["questions"] if r and r.get("certified") else None
    print(f"% truth {T}")
    print("% price:      " + curve([price(T, d) for d in B3], 23))
    print("% Cert3NF:    " + curve([q(m[MAIN][d]) for d in B3], 23))
    print("% with LLM:   " + curve([q(m[LLM][d]) for d in B3], 23))
    print("% careful:    " + curve([q(care[d]) for d in B3], 23))
    print("% w/o advisor:" + curve([q(v["v5n"][d]) for d in B3], 23))
    for var in sorted({r["variant"] for r in D[T]["ec2"]}):
        sd = seeded(D[T]["ec2"], var)
        if len(sd) == 23:
            print(f"% {var}: " + curve([sorted((q(r) if q(r) is not None else 10 ** 9) for r in sd[d])[1] for d in B3], 23))

# ---- normalizer ----
print("%% ---- normalizer on batch 3 ----")
for T in TRUTHS:
    sd = seeded(D[T]["L3"], "L3")
    print(f"% {T}: runs {sum(map(len, sd.values()))}, good relations (median seed) {sum(st.median(bool(r.get('gold_good')) for r in x) >= 0.5 for x in sd.values())}, good runs {sum(bool(r.get('gold_good')) for x in sd.values() for r in x)}, lossless relations {sum(st.median(bool(r.get('gold_lossless')) for r in x) >= 0.5 for x in sd.values())}, F1 {st.mean(st.mean(r.get('f1') or 0.0 for r in x) for x in sd.values()):.2f}")

# ---- last rows of Tab. cert and Tab. cert-dev ----
print("%% ---- within 100 and within 50, last rows ----")
cells3, cells1 = {100: [], 50: []}, []
for T in TRUTHS:
    m, v = D[T]["main3"], D[T]["v53"]
    th = {r["dataset"]: r for r in D[T]["theta"] if r.get("theta") == 0.1 and r["variant"] == MAIN}
    th.update({r["dataset"]: r for r in D[T]["raw"] if r.get("theta") == 0.1 and r["variant"] == MAIN})
    ec = seeded(D[T]["ec2"], "ec2full0")
    rb, eh = seeded(D[T]["rb"], "rbhyb"), seeded(D[T]["ec2hyb"], "ec2hyb")
    for b in (100, 50):
        cells3[b] += rank_marks(["", "", f"{sum(within(m[MAIN][d], b) for d in B3)}/23", f"{sum(within(m[LLM][d], b) for d in B3)}/23", f"{sum(within(v['v5n'][d], b) for d in B3)}/23",
                                 f"{sum(within3(ec[d], b) for d in B3)}/23", f"{sum(within3(rb[d], b) for d in B3)}/23", f"{sum(within3(eh[d], b) for d in B3)}/23",
                                 f"{sum(within(th[d], b) for d in B3)}/23"], range(2, 8), max)
    m1 = D[T]["main1"]
    cells1 += rank_marks(["", "", f"{sum(within(m1[MAIN][d], 100) for d in DEV + B2)}/35", f"{sum(within(m1[LLM][d], 100) for d in DEV + B2)}/35", f"{sum(within(m1['v5n'][d], 100) for d in DEV + B2)}/35", f"{sum(within3(RB1[T][d], 100) for d in DEV + B2)}/35"], range(2, 6), max)
    for lab, sd, part in (("development", RB1[T], DEV + B2), ("confirmatory", rb, B3), ("EC2 certificate, confirmatory", eh, B3)):
        ok = [d for d in part if within3(sd[d], 100)]
        marked = [d for d in ok if cell3(sd[d], T).endswith((CROSS, DAGGER))]
        wrong = [d for d in marked if d not in VIOL[T]]
        print(f"% {T} {lab}: posterior-style median of three: certified relations {len(ok)}/{len(part)}, of them wrong (cross) {len(wrong)}, dagger {len(marked) - len(wrong)}; runs: certified {sum(bool(r.get('certified')) for d in part for r in sd[d])}/{3 * len(part)}")
print("within 100 &  & " + " & ".join(cells3[100]) + r"\\")
print("within 50 &  & " + " & ".join(cells3[50]) + r"\\")
print("within 100 &  & " + " & ".join(cells1) + r"\\")

# ---- Tab. auto ----
print("%% ---- Tab. auto: good relations by the median seed, macro F1 ----")
AU = {}
for T in TRUTHS:
    AU[T] = defaultdict(lambda: defaultdict(list))
    for s in ("dev12", "dev24b", "conf"):
        for suf in ("auto", "L3"):
            for r in rows(f"paper_src/{s}_{T}_{suf}.jsonl"):
                if r.get("error"):
                    r = dict(r, certified=False, gold_good=False, gold_lossless=False, f1=0.0)
                AU[T][r["variant"]][r["dataset"]].append(r)
    for r in rows(f"v6f_fresh3/auto_{T}.jsonl") + D[T]["L3"]:
        if r.get("error"):
            r = dict(r, certified=False, gold_good=False, gold_lossless=False, f1=0.0)
        AU[T][r["variant"]][r["dataset"]].append(r)


def relcell(per, part):
    per = {d: per[d] for d in part if d in per}
    if not per:
        return "--", "--"
    good = sum(st.median(bool(r.get("gold_good")) for r in x) >= 0.5 for x in per.values())
    return f"{good}/{len(per)}", f"{st.mean(st.mean(r.get('f1') or 0.0 for r in x) for x in per.values()):.2f}".replace("0.", ".", 1)


def autorow(label, get):
    g, f = [], []
    for part in (DEV + B2, B3):
        for T in TRUTHS:
            a, b = relcell(get(T), part)
            g.append(a)
            f.append(b)
    print(f"{label} & " + " & ".join(g) + " & " + " & ".join(f) + r"\\")


for var, label in (("hyfd", "mined FDs"), ("trust", "trust"), ("clf", "classifier"), ("ours", "posterior alone"), ("A5", "rules"), ("L1", "LLM design"), ("L3", "normalizer"), ("upper", "every candidate")):
    autorow(label, lambda T, var=var: AU[T][var])
print(r"\midrule")
b100one = {T: {d: [r] for d, r in {**by_variant(rows(f"v6f_runs/b100_{C}_dev_{T}.jsonl") + rows(f"v6f_runs/b100_{C}_b2_{T}.jsonl"))[MAIN], **D[T]["b100"][MAIN]}.items()} for T in TRUTHS}
autorow("posterior certificate", lambda T: {**{d: RB1[T][d] for d in DEV + B2}, **seeded(D[T]["rb"], "rbhyb")})
autorow("EC$^2$", lambda T: seeded(D[T]["ec2hyb"], "ec2hyb"))
autorow("EC$^2$ order", lambda T: {d: [dict(r, gold_good=(r.get("at100") or {}).get("gold_good", r.get("gold_good")), f1=(r.get("at100") or {}).get("f1", r.get("f1"))) for r in x] for d, x in seeded(D[T]["ec2"], "ec2full0").items()})
autorow(r"\ours", lambda T: b100one[T])
print("% lossless by the median seed, batch 3:")
for var, label in (("hyfd", "mined FDs"), ("trust", "trust"), ("clf", "classifier"), ("ours", "posterior alone"), ("A5", "rules"), ("L1", "LLM design"), ("L3", "normalizer")):
    print(f"%   {label}: " + ", ".join(f"{T} {sum(st.median(bool(r.get('gold_lossless')) for r in AU[T][var][d]) >= 0.5 for d in B3 if d in AU[T][var])}/{sum(d in AU[T][var] for d in B3)}" for T in TRUTHS))

# ---- Tab. data, batch 3 ----
print("%% ---- Tab. data ----")
for d in DEV + B2 + B3:
    j = json.load(open(f"../e3/data/{d}.json", encoding="utf-8"))
    src = D["full"]["main3"][MAIN] if d in B3 else D["full"]["main1"][MAIN]
    src2 = D["sure"]["main3"][MAIN] if d in B3 else D["sure"]["main1"][MAIN]
    print(f"{name(d)}{' (A)' if d in CLASS_A else ''} & {len(j['attributes'])} & {j['instance']['rows']:,} & {src[d]['candidates']:,} & {src[d]['true']}/{src2[d]['true']}")
