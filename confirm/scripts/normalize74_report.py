"""
Design note item 74: what Normalize gives on batch 3, counted as paper_tables_v6f.py counts the other methods.
  (a) the automatic Normalize (normalize_<T>.jsonl): good and lossless designs of the 23 relations, tables against synthesis
  (b) Normalize order (order_<T>_b1000.jsonl, order_<T>_b100.jsonl): relations certified within 50 and 100 answers, certified
      runs, answers in total and above the price, the median ratio to the price, the paired ratio of Cert3NF over it (median,
      95% bootstrap interval over relations, wins, ties, losses, exact Wilcoxon signed-rank p), good designs at budget 100
Usage (in confirm/): python scripts/normalize74_report.py
"""
import contextlib, io, json, math, os, random, statistics as st, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
with contextlib.redirect_stdout(io.StringIO()):
    import paper_tables_v6f as P          # the paper's loaders and counts
    import paired_tests_v6f as PT         # the exact signed-rank test and the bootstrap over relations

B3, D, MAIN = P.B3, P.D, P.MAIN
OUT = "v6f_fresh3_extra/normalize"


def load(f, var=None):
    rs = P.rows(os.path.join(OUT, f))
    return {r["dataset"]: r for r in rs if var is None or r["variant"] == var}


for T in P.TRUTHS:
    print(f"truth {T}")
    a = load(f"normalize_{T}.jsonl")
    if len(a) == 23:
        good = sum(bool(a[d]["gold_good"]) for d in B3)
        lossless = sum(bool(a[d]["gold_lossless"]) for d in B3)
        more = sum(a[d]["tables"] > a[d]["gold_opt_tables"] for d in B3)
        print(f"  (a) Normalize: good {good}/23, lossless {lossless}/23, preserving {sum(bool(a[d]['gold_preserving']) for d in B3)}/23, 3NF {sum(bool(a[d]['gold_nf3']) for d in B3)}/23, "
              f"more tables than synthesis {more}; splits median {st.median(len(a[d]['splits']) for d in B3)}")
        print(f"      lossy: {', '.join(P.name(d) for d in B3 if not a[d]['gold_lossless'])}")
    else:
        print(f"  (a) Normalize: {len(a)} of 23 rows")
    o, o100 = load(f"order_{T}_b1000.jsonl", "v6n|lc+hone+kf+rl"), load(f"order_{T}_b100.jsonl", "v6n|lc+hone+kf+rl")
    if len(o) != 23:
        print(f"  (b) Normalize order: {len(o)} of 23 rows at budget 1000")
        continue
    m = D[T]["main3"][MAIN]
    for d in B3:          # a run certified within 100 answers is the same run at budget 100 (as for Cert3NF)
        if d in o100 and P.within(o[d], 100):
            assert o100[d]["certified"] and o100[d]["questions"] == o[d]["questions"], (T, d)
    q = {d: o[d]["questions"] for d in B3}
    price = sum(P.price(T, d) for d in B3)
    ratio = sorted(q[d] / P.price(T, d) for d in B3 if o[d].get("certified"))
    pair = {d: m[d]["questions"] / q[d] for d in B3}
    rng = random.Random(74)
    lo, hi = PT.boot(pair, None, rng)
    clo, chi = PT.boot(pair, PT.PUB, rng)
    logs = [math.log(x) for x in pair.values()]
    w, l = sum(x < 0 for x in logs), sum(x > 0 for x in logs)
    print(f"  (b) Normalize order: within 50 {sum(P.within(o[d], 50) for d in B3)}, within 100 {sum(P.within(o[d], 100) for d in B3)} "
          f"(Cert3NF {sum(P.within(m[d], 50) for d in B3)}, {sum(P.within(m[d], 100) for d in B3)}); certified {sum(bool(o[d].get('certified')) for d in B3)}/23, "
          f"wrong {sum(bool(o[d].get('certified')) and not o[d].get('gold_good') and d not in P.VIOL[T] for d in B3)}")
    print(f"      answers {sum(q.values())} (Cert3NF {sum(m[d]['questions'] for d in B3)}), above the price {sum(q.values()) - price} (Cert3NF {sum(m[d]['questions'] for d in B3) - price}), "
          f"ratio to the price median {st.median(ratio):.3f}, Q3 {st.quantiles(ratio, n=4)[2]:.3f}")
    print(f"      Cert3NF over it: median {st.median(pair.values()):.3f}, 95% bootstrap [{lo:.3f}, {hi:.3f}] over relations, [{clo:.3f}, {chi:.3f}] over publishers, wins {w}, ties {23 - w - l}, losses {l}, "
          f"Wilcoxon p {PT.wilcoxon_p([x for x in logs if x != 0]):.2g}")
    if len(o100) == 23:
        print(f"      good at budget 100: {sum(bool(o100[d]['gold_good']) for d in B3)}/23 (Cert3NF {sum(bool(D[T]['b100'][MAIN][d]['gold_good']) for d in B3)}/23)")
