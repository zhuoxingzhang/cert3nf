"""
F9 on the second confirmatory batch (design note items 28 and 37): do gpt-oss-20b and Qwen3.5-9B err on the same
candidates?  Per relation and truth, every candidate that both models answered gives one cell of a 2x2 table (Qwen
wrong or right x gpt-oss wrong or right; an answer is wrong when it says yes to a false candidate or no to a true one).
The Mantel-Haenszel odds ratio over the strata (relation, truth) with the Robins-Breslow-Greenland 95% interval is
the statistic of F9 (item 28): a lower end above 1 means the errors are decided by the candidate, not by the model.
One call handles one truth (the benchmark truth is fixed at import), writes the strata to a JSON file and reports the
odds ratio over them; --combine reads several such files and reports the odds ratio over all their strata.
Usage (in confirm, CONFIRM_BATCH=2):
  CONFIRM_TRUTH=full python scripts/f9_fresh2.py --out v5_fresh2_gptoss/f9_full.json
  CONFIRM_TRUTH=sure python scripts/f9_fresh2.py --out v5_fresh2_gptoss/f9_sure.json
  python scripts/f9_fresh2.py --combine v5_fresh2_gptoss/f9_full.json v5_fresh2_gptoss/f9_sure.json
"""
import argparse, json, math, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.environ.setdefault("CONFIRM_BATCH", "2")


def mh(strata):
    """Mantel-Haenszel odds ratio and its RBG 95% interval over strata {name: [a, b, c, d]} (a: both wrong, b: first
    wrong only, c: second wrong only, d: both right)"""
    R = S = PR = PSQR = QS = 0.0
    for a, b, c, d in strata.values():
        n = a + b + c + d
        if n == 0:
            continue
        P, Q, r, s = (a + d) / n, (b + c) / n, a * d / n, b * c / n
        R += r; S += s; PR += P * r; PSQR += P * s + Q * r; QS += Q * s
    if R == 0 or S == 0:
        return float("inf") if S == 0 and R > 0 else 0.0, None, None
    o = R / S
    var = PR / (2 * R * R) + PSQR / (2 * R * S) + QS / (2 * S * S)
    lo, hi = math.exp(math.log(o) - 1.96 * math.sqrt(var)), math.exp(math.log(o) + 1.96 * math.sqrt(var))
    return o, lo, hi


def pooled(strata):
    a, b, c, d = (sum(t[i] for t in strata.values()) for i in range(4))
    return (a * d / (b * c)) if b * c else float("inf"), (a, b, c, d)


def report(strata, label):
    o, lo, hi = mh(strata)
    po, (a, b, c, d) = pooled(strata)
    n = a + b + c + d
    if n == 0:
        print(f"{label}: no candidate answered by both models")
        return
    print(f"{label}: {len(strata)} strata, {n} candidates answered by both; both wrong {a}, first only {b}, "
          f"second only {c}, both right {d}; error rates {(a + b) / n:.3f} vs {(a + c) / n:.3f}")
    print(f"  Mantel-Haenszel odds ratio {o:.2f}" + (f", 95% interval [{lo:.2f}, {hi:.2f}]" if lo else "")
          + f"; pooled {po:.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", default="llm_fresh2")
    ap.add_argument("--models", default="q35,gptoss")
    ap.add_argument("--datasets", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--combine", nargs="*", default=[])
    a = ap.parse_args()
    if a.combine:
        strata = {}
        for f in a.combine:
            with open(f, encoding="utf-8") as fh:
                strata.update(json.load(fh)["strata"])
        report(strata, "all truths")
        return
    import auto_common as AC
    import auto_confirm as ACF
    T = AC.truth_mode()
    m1, m2 = a.models.split(",")
    dss = a.datasets.split(",") if a.datasets else AC.FRESH
    bs = ACF.benches()
    A1 = ACF.read_answers(os.path.join(HERE, f"{a.answers}_{T}_{m1}"), m1)["expert"]
    A2 = ACF.read_answers(os.path.join(HERE, f"{a.answers}_{T}_{m2}"), m2)["expert"]
    strata = {}
    for ds in dss:
        truth = set(bs[ds]["truth"])
        t = [0, 0, 0, 0]
        for p in bs[ds]["P"]:
            y1, y2 = A1.get(ds, {}).get(p), A2.get(ds, {}).get(p)
            if not isinstance(y1, bool) or not isinstance(y2, bool):   # read_answers gives True (yes) / False (no) / None
                continue
            w1, w2 = y1 != (p in truth), y2 != (p in truth)
            t[0 if w1 and w2 else 1 if w1 else 2 if w2 else 3] += 1
        strata[f"{ds}|{T}"] = t
        print(f"  {ds} {T}: both wrong {t[0]}, {m1} only {t[1]}, {m2} only {t[2]}, both right {t[3]}")
    report(strata, f"truth {T} ({m1} vs {m2})")
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump({"truth": T, "models": [m1, m2], "strata": strata}, fh, indent=1)


if __name__ == "__main__":
    main()
