"""
Design note item 73: uncertainty of the paired comparisons over the 23 confirmatory relations (round 6, R3 W6), added after the
verdicts and reported only; no rule depends on it.  For each truth and comparison, the ratio per relation is Cert3NF's answers over
the other method's (the median of three seeds for EC^2 order; an uncertified run counts as its budget of 1,000, as in the paper):
  V3   Cert3NF against the EC^2 order without the LLM (ec2full0), as in Sec. 6 (0.70x, 0.65x)
  V1   Cert3NF against the two phases with the LLM (v5), as in Q3 (0.89x, 0.85x)
  LLM  Cert3NF with the LLM against Cert3NF (1,786 against 1,774 answers under the full truth)
Reported: the median ratio, its 95% percentile bootstrap interval over relations and over the twelve publishers (clusters),
wins, ties and losses, and the two-sided Wilcoxon signed-rank test on the log ratios (ties dropped) and the sign test.
Usage (in confirm/): python scripts/paired_tests_v6f.py
"""
import contextlib, io, math, os, random, statistics as st, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
with contextlib.redirect_stdout(io.StringIO()):
    import paper_tables_v6f as P          # the paper's own loaders and counts; its printout is discarded
B3, D, MAIN, LLM = P.B3, P.D, P.MAIN, P.LLM


def wilcoxon_p(xs):
    """exact two-sided p of the signed-rank test on the nonzero values xs, average ranks for tied |x|, by enumerating the signs"""
    a = sorted(abs(x) for x in xs)
    rank = {}
    i = 0
    while i < len(a):
        j = i
        while j < len(a) and a[j] == a[i]:
            j += 1
        rank[a[i]] = i + j + 1              # twice the average rank (i+1 .. j), an integer
        i = j
    r2 = [rank[abs(x)] for x in xs]
    w = sum(r for r, x in zip(r2, xs) if x > 0)
    dist = {0: 1}
    for r in r2:
        nxt = dict(dist)
        for s, c in dist.items():
            nxt[s + r] = nxt.get(s + r, 0) + c
        dist = nxt
    tot = 2 ** len(xs)
    lo = sum(c for s, c in dist.items() if s <= w) / tot
    hi = sum(c for s, c in dist.items() if s >= w) / tot
    return min(1.0, 2 * min(lo, hi))


def sign_p(k, n):
    lo = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    hi = sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n
    return min(1.0, 2 * min(lo, hi))
PUB = {d: d.split("_")[1] for d in B3}
assert len(set(PUB.values())) == 12
NBOOT = 10000


def ec2_order(T):
    sd = P.seeded(D[T]["ec2"], "ec2full0")
    return {d: st.median(r["questions"] for r in sd[d]) for d in B3}


def boot(ratio, clusters, rng):
    keys = sorted(set(clusters.values())) if clusters else B3
    groups = {k: [d for d in B3 if (clusters[d] if clusters else d) == k] for k in keys}
    meds = []
    for _ in range(NBOOT):
        pick = [d for k in (rng.choice(keys) for _ in keys) for d in groups[k]]
        meds.append(st.median(ratio[d] for d in pick))
    meds.sort()
    return meds[int(0.025 * NBOOT)], meds[int(0.975 * NBOOT) - 1]


for T in P.TRUTHS:
    main = {d: D[T]["main3"][MAIN][d]["questions"] for d in B3}
    comps = (("V3 Cert3NF / EC2 order", main, ec2_order(T)),
             ("V1 Cert3NF / two phases", main, {d: D[T]["v53"]["v5"][d]["questions"] for d in B3}),
             ("LLM with / without", {d: D[T]["main3"][LLM][d]["questions"] for d in B3}, main))
    print(f"truth {T}")
    for lab, a, b in comps:
        ratio = {d: a[d] / b[d] for d in B3}
        rng = random.Random(73)
        lo, hi = boot(ratio, None, rng)
        clo, chi = boot(ratio, PUB, rng)
        logs = [math.log(ratio[d]) for d in B3]
        w, l = sum(x < 0 for x in logs), sum(x > 0 for x in logs)
        p_w = wilcoxon_p([x for x in logs if x != 0])
        p_s = sign_p(w, w + l)
        print(f"  {lab:26s}: median {st.median(ratio.values()):.3f}, 95% bootstrap [{lo:.3f}, {hi:.3f}] over relations, [{clo:.3f}, {chi:.3f}] over publishers; "
              f"wins {w}, ties {23 - w - l}, losses {l}; Wilcoxon p {p_w:.2g}, sign test p {p_s:.2g}; sums {sum(a.values()):g} / {sum(b.values()):g}")
