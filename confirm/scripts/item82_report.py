"""
Design note item 82: three supplementary experiments, counted as the paper counts
(paper_tables_v6f.py, paired_tests_v6f.py, err75_report.py), from the local copies in v6f_fresh3_extra/item82/.
  (a) wrong/wrong_<set>_<T>.jsonl          Cert3NF with a wrong advisor (v6f_wrong.py), sets dev, b2, b3
  (b) ec2find/ec2find_<T>.jsonl            the EC^2 order with the Find step of Cert3NF (ec2find.py), batch 3
  (c) designer/designer_rho<phi>_<set>_<T>.jsonl   the careful mode at (eps, phi) = (0.10, 0.12) and (0.15, 0.18)
A missing part is named and skipped.  All three ran after the verdicts V1-V5 and are reported only.
Usage (in confirm/): python scripts/item82_report.py > scripts/item82_report.out
"""
import contextlib, io, json, math, os, statistics as st, sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
with contextlib.redirect_stdout(io.StringIO()):
    import paper_tables_v6f as P          # the paper's loaders, names and counts; its printout is discarded
    import paired_tests_v6f as PT         # the exact Wilcoxon test of item 73

C, MAIN, TRUTHS, B3, DEV, B2, D, VIOL = P.C, P.MAIN, P.TRUTHS, P.B3, P.DEV, P.B2, P.D, P.VIOL
BASE = "v6f_fresh3_extra/item82"
SETS = {"dev": DEV, "b2": B2, "b3": B3}
ALL = DEV + B2 + B3
INFO = {}
for f in ("v6f_runs/price_dev.json", "v6f_runs/price_b2.json", "v6f_fresh3/price_gold.json"):
    INFO.update(json.load(open(f, encoding="utf-8")))


def load(path):
    if not os.path.exists(path):
        print(f"% MISSING {path}")
        return None
    with open(path, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def q3(xs):
    return st.quantiles(xs, n=4)[2]


def paired(a, b, ds):
    """a over b per relation: the median ratio, wins, ties, losses of a, and the exact Wilcoxon p on the log ratios"""
    logs = [math.log(a[d] / b[d]) for d in ds]
    nz = [x for x in logs if x != 0]
    return st.median(a[d] / b[d] for d in ds), sum(x < 0 for x in logs), sum(x == 0 for x in logs), sum(x > 0 for x in logs), PT.wilcoxon_p(nz) if nz else 1.0


# =============================== (a) a wrong advisor ===============================
print("%% ==== (a) Cert3NF with a wrong advisor: exact designer, budget 1000 ====")
KINDS = (("inverted", ["v6i"]), ("permuted", ["v6p0", "v6p1", "v6p2"]), ("all", ["v6a"]))
RULES = "|lc+hone+kf+rl"
for T in TRUTHS:
    W, ok = defaultdict(dict), True
    for S, ds in SETS.items():
        rs = load(f"{BASE}/wrong/wrong_{S}_{T}.jsonl")
        if rs is None:
            ok = False
            continue
        keys = Counter((r["variant"], r["dataset"]) for r in rs)
        want = {(v + RULES, d) for _, vs in KINDS for v in vs for d in ds}
        print(f"% {T} {S}: {len(rs)} rows, duplicate keys {sum(n > 1 for n in keys.values())}, missing {len(want - set(keys))}, extra {len(set(keys) - want)}; "
              f"code {sorted({r['code'] for r in rs})}, budget {sorted({r['budget'] for r in rs})}, oracle {sorted({r['oracle'] for r in rs})}, prior kinds {sorted({r['prior_kind'] for r in rs})}")
        for r in rs:
            W[r["variant"].partition("|")[0]][r["dataset"]] = r
    if not ok:
        continue
    main = dict(D[T]["main3"][MAIN])
    main.update({d: D[T]["main1"][MAIN][d] for d in DEV + B2})
    none = dict(D[T]["v53"]["v5n"])
    none.update({d: D[T]["main1"]["v5n"][d] for d in DEV + B2})
    price = lambda d: INFO[f"{T}/{d}"]["price"]
    for lab, part in (("confirmatory 23", B3), ("all 58", ALL)):
        print(f"% truth {T}, {lab}: price {sum(price(d) for d in part)}, smallest covers {sum(INFO[f'{T}/{d}']['cover'] for d in part)}, held sets {sum(INFO[f'{T}/{d}']['m_r'] for d in part)}")
        refs = (("Cert3NF", {d: [main[d]] for d in part}), ("w/o advisor", {d: [none[d]] for d in part}))
        wrongs = tuple((k, {d: [W[v][d] for v in vs] for d in part}) for k, vs in KINDS)
        qs = {}
        for name, runs in refs + wrongs:
            flat = [r for d in part for r in runs[d]]
            med = lambda d, f: st.median(f(r) for r in runs[d])
            q = {d: med(d, lambda r: r["questions"]) for d in part}
            qs[name] = q
            cert = {d: sum(bool(r["certified"]) for r in runs[d]) * 2 > len(runs[d]) for d in part}
            ratio = sorted(q[d] / price(d) for d in part if cert[d])
            notgood = [r for r in flat if r["certified"] and not r.get("gold_good")]
            line = (f"%   {name:12s}: runs {len(flat)}, certified runs {sum(bool(r['certified']) for r in flat)}, relations certified {sum(cert.values())}/{len(part)}, "
                    f"within 50 {sum(cert[d] and q[d] <= 50 for d in part)}, within 100 {sum(cert[d] and q[d] <= 100 for d in part)}; answers {sum(q.values()):g}, above the price {sum(q.values()) - sum(price(d) for d in part):g}, "
                    f"ratio median {st.median(ratio):.3f}, Q3 {q3(ratio):.3f}, max {ratio[-1]:.2f}; certified and not good on gold: dagger {sum(r['dataset'] in VIOL[T] for r in notgood)}, other {sum(r['dataset'] not in VIOL[T] for r in notgood)}")
            has = lambda *ks: all(k in r for r in flat for k in ks)
            if has("confirmed"):
                line += f"; d {sum(med(d, lambda r: r['confirmed']) for d in part):g}"
            if has("wrong_cert"):
                line += f", wrong_cert {sum(bool(r['wrong_cert']) for r in flat)}"
            if has("disc_no", "max_no", "guess_questions", "guess_hits", "qx_questions"):
                over = [r for r in flat if r["max_no"] > INFO[f"{T}/{r['dataset']}"]["m_r"]]
                line += (f", no to believed FDs: max {max(r['disc_no'] for r in flat)}, sum {sum(med(d, lambda r: r['disc_no']) for d in part):g}; no to maximal sets above m_r: runs {len(over)} "
                         f"(dagger {sum(r['dataset'] in VIOL[T] for r in over)}); guesses {sum(med(d, lambda r: r['guess_questions']) for d in part):g}, hits {sum(med(d, lambda r: r['guess_hits']) for d in part):g}, "
                         f"QuickXplain {sum(med(d, lambda r: r['qx_questions']) for d in part):g}")
            print(line)
        for name, _ in wrongs:
            for ref in ("Cert3NF", "w/o advisor"):
                m, w, t, l, p = paired(qs[name], qs[ref], part)
                print(f"%   {name:9s} over {ref:11s}: sums {sum(qs[name].values()):g} / {sum(qs[ref].values()):g} = {sum(qs[name].values()) / sum(qs[ref].values()):.3f}, median ratio {m:.3f}, fewer {w}, equal {t}, more {l}, Wilcoxon p {p:.2g}")
    for S in SETS:
        f = f"{BASE}/wrong/wrong_{S}_{T}.check.txt"
        if os.path.exists(f):
            lines = open(f, encoding="utf-8").read().strip().split("\n")
            print(f"% check_cert {S} {T}: {len(lines) - 1} rows, {sum('DISAGREES' in x for x in lines)} disagreements, last line: {lines[-1]}")

# =============================== (b) the EC^2 order with the Find step ===============================
print("%% ==== (b) EC^2 order with the Find step of Cert3NF (ec2find0), batch 3, three seeds, budget 1000 ====")
share = {}
for T in TRUTHS:
    rs = load(f"{BASE}/ec2find/ec2find_{T}.jsonl")
    if rs is None:
        continue
    keys = Counter((r["variant"], r["dataset"], r["seed"]) for r in rs)
    want = {("ec2find0", d, s) for d in B3 for s in range(3)}
    print(f"% {T}: {len(rs)} rows, duplicate keys {sum(n > 1 for n in keys.values())}, missing {len(want - set(keys))}, extra {len(set(keys) - want)}; "
          f"codes {sorted({(r['code_find'], r['code_ec2full'], r['code_v6f']) for r in rs})}, budget {sorted({r['budget'] for r in rs})}, truth {sorted({r['truth'] for r in rs})}")
    if set(keys) != want:
        continue
    price = lambda d: P.price(T, d)
    psum = sum(price(d) for d in B3)
    m = D[T]["main3"][MAIN]
    meth = {"Cert3NF": {d: [m[d]] for d in B3}, "EC2 order": P.seeded(D[T]["ec2"], "ec2full0"), "EC2 order + Find": P.seeded(rs, "ec2find0")}
    G, Q = {}, {}
    for name, sd in meth.items():
        runs = [r for d in B3 for r in sd[d]]
        one = len(sd[B3[0]]) == 1
        w50 = sum((P.within(sd[d][0], 50) if one else P.within3(sd[d], 50)) for d in B3)
        w100 = sum((P.within(sd[d][0], 100) if one else P.within3(sd[d], 100)) for d in B3)
        q = {d: st.median(r["questions"] for r in sd[d]) for d in B3}
        Q[name], G[name] = q, sum(q.values()) - psum
        ratio = sorted(q[d] / price(d) for d in B3)
        wrong = sum(bool(r["certified"]) and not r.get("gold_good") and r["dataset"] not in VIOL[T] for r in runs)
        pick = {d: sorted(sd[d], key=lambda r: r["questions"])[len(sd[d]) // 2] for d in B3}
        if name == "Cert3NF":
            find = sum(r["qx_questions"] + r["hone_questions"] + r["guess_questions"] + r["reuse_questions"] for r in pick.values())
            other = sum(r["questions"] for r in pick.values()) - find - sum(r["max_questions"] for r in pick.values())
            parts = f"finding {find} (QuickXplain {sum(r['qx_questions'] for r in pick.values())})"
        else:
            find = sum(r["qx_questions"] + r.get("guess_questions", 0) + r.get("reuse_questions", 0) for r in pick.values())
            other = sum(r["cand_questions"] for r in pick.values())
            parts = (f"finding {find} (QuickXplain {sum(r['qx_questions'] for r in pick.values())}, guesses {sum(r.get('guess_questions', 0) for r in pick.values())} with {sum(r.get('guess_hits', 0) for r in pick.values())} hits, "
                     f"reuse {sum(r.get('reuse_questions', 0) for r in pick.values())} with {sum(r.get('reuse_hits', 0) for r in pick.values())} hits)")
        print(f"%   {name:17s}: within 50 {w50}, within 100 {w100}, certified runs {sum(bool(r['certified']) for r in runs)}/{len(runs)}, wrong {wrong}; answers {sum(q.values()):g}, above the price {G[name]:g}, "
              f"ratio median {st.median(ratio):.3f}, Q3 {q3(ratio):.3f}; median run: total {sum(r['questions'] for r in pick.values())}, {parts}, maximal sets {sum(r['max_questions'] for r in pick.values())}, other candidates {other}, "
              f"FDs found through a set {sum(r['found'] for r in pick.values())}, secs {sum(r['secs'] for r in pick.values()):.0f}")
    for a, b in (("Cert3NF", "EC2 order + Find"), ("Cert3NF", "EC2 order"), ("EC2 order + Find", "EC2 order")):
        md, w, t, l, p = paired(Q[a], Q[b], B3)
        print(f"%   {a} over {b}: median ratio {md:.3f}, fewer {w}, equal {t}, more {l}, Wilcoxon p {p:.2g}; sums {sum(Q[a].values()):g} / {sum(Q[b].values()):g}")
    share[T] = (G["EC2 order"] - G["EC2 order + Find"]) / (G["EC2 order"] - G["Cert3NF"])
    print(f"%   share of the gap above the price that the Find step closes: ({G['EC2 order']:g} - {G['EC2 order + Find']:g}) / ({G['EC2 order']:g} - {G['Cert3NF']:g}) = {share[T]:.3f}; "
          f"EC2 order + Find spends {G['EC2 order + Find'] / G['Cert3NF']:.2f}x the answers of Cert3NF above the price, EC2 order {G['EC2 order'] / G['Cert3NF']:.2f}x")
    f = f"{BASE}/ec2find/ec2find_{T}.check.txt"
    if os.path.exists(f):
        lines = open(f, encoding="utf-8").read().strip().split("\n")
        print(f"% check_cert {T}: {len(lines) - 1} rows, {sum('DISAGREES' in x for x in lines)} disagreements, last line: {lines[-1]}")

# =============================== (c) the designer at the measured rates ===============================
print("%% ==== (c) careful mode, a designer at the rates of the practitioners: (eps, phi), three seeds, budget 1000 ====")
HUMAN = ["fresh3_fec_candidate", "fresh3_synthea_claims", "fresh3_tpcc_customer"]
IND = {"dev": f"v6f_runs/err75_{C}_dev_{{}}.jsonl", "b2": f"v6f_runs/err75_{C}_b2_{{}}.jsonl", "b3": "v6f_fresh3_extra/err75/err_b3_{}.jsonl"}


def count(rs):
    c = [r for r in rs if r.get("certified")]
    c1 = [r for r in c if r["questions"] <= 100]
    return [len(rs), len(c), sum(bool(r.get("wrong_cert")) for r in c), len(c1), sum(bool(r.get("wrong_cert")) for r in c1)]


for eps, phi in ((0.10, 0.12), (0.15, 0.18)):
    E, I, ok = {}, {}, True
    for S, ds in SETS.items():
        for T in TRUTHS:
            rs = load(f"{BASE}/designer/designer_rho{phi}_{S}_{T}.jsonl")
            if rs is None:
                ok = False
                continue
            keys = Counter((r["dataset"], r["seed"]) for r in rs)
            want = {(d, s) for d in ds for s in range(3)}
            bad = [r for r in rs if not (r["variant"] == MAIN and r["designer_err"] == eps and r["rho"] == phi and r["careful"] and not r["repeated"] and r["code"] == C and r["budget"] == 1000)]
            print(f"% ({eps:.2f}, {phi}) {S} {T}: {len(rs)} rows, duplicate keys {sum(n > 1 for n in keys.values())}, missing {len(want - set(keys))}, extra {len(set(keys) - want)}, rows of another setting {len(bad)}")
            E[S, T] = rs
            I[S, T] = [r for r in P.rows(IND[S].format(T)) if r["variant"] == MAIN and r["designer_err"] == eps and r.get("careful")]
    if not ok:
        continue
    for lab, src in ((f"phi {phi}", E), ("independent", I)):
        cells, tot = [], [0] * 5
        for group in (("dev", "b2"), ("b3",)):
            for T in TRUTHS:
                c = count([r for S in group for r in src[S, T]])
                cells.append(f"{c[3]} & {c[4]}")
                tot = [a + b for a, b in zip(tot, c)]
        print(f"{eps:.2f}, {lab} & careful & " + " & ".join(cells) + rf"\\  % development full, sure; confirmatory full, sure; within 100 answers: certificates & wrong")
        n, c, w, c1, w1 = tot
        flat = [r for v in src.values() for r in v]
        print(f"%   pooled {n} runs: within 100: {c1} certificates, {w1} wrong ({w1 / max(c1, 1):.3f}), {c1 - w1} correct; budget 1000: {c} certificates, {w} wrong ({w / max(c, 1):.3f}), {c - w} correct; "
              f"first answers wrong {sum(r['first_wrong'] for r in flat)}/{sum(r['first_answers'] for r in flat)} = {sum(r['first_wrong'] for r in flat) / sum(r['first_answers'] for r in flat):.3f}, "
              f"questions asked again with both first answers wrong {sum(r['pairs_both_wrong'] for r in flat)}/{sum(r['pairs'] for r in flat)}"
              f" = {sum(r['pairs_both_wrong'] for r in flat) / max(sum(r['pairs'] for r in flat), 1):.4f}")
        # The questions asked again are no random sample: a conflict asks again the answers it involves, and these are wrong more often.
        # Hence the share above exceeds eps^2 also for the independent designer, and the rows give no estimate of phi.
        for T in TRUTHS:
            rs = [r for r in src["b3", T] if r["dataset"] in HUMAN]
            n, c, w, c1, w1 = count(rs)
            per = {P.name(d): f"{sum(1 for r in rs if r['dataset'] == d and r.get('certified') and r['questions'] <= 100)}/{sum(1 for r in rs if r['dataset'] == d)}" for d in HUMAN}
            print(f"%   study relations {T}: {n} runs, certified within 100 {c1}, wrong {w1}, per relation {per}; budget 1000: {c} certificates, {w} wrong; answers median {st.median(r['questions'] for r in rs):g}")
print("% practitioners of the study (Tab. human): P 6 of 9 certified, 1 wrong; U 4 of 9, 1 wrong")
