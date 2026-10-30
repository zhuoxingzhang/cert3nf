"""Report of item 34 (design notes): the tolerant v5 (v5tol.py) on the development relations.
  check   the runs with eps = eps_m = 0 against item 32's v5 / v5s runs (certified, questions, gold_good)
  rules   U1 (wrong certificates of v5t <= 10% under eps 0.02, 0.05), U2 (v5t's share of wrong certificates below the
          trusting v5's), U3 (v5t more correct certificates than v5st); the cost of tolerance at eps = 0; stubborn
Usage:  python v5tol_report.py --tol T_full.jsonl --ref v5_full.jsonl [--tol T_sure.jsonl --ref v5_sure.jsonl]"""
import argparse, json, statistics
from collections import defaultdict


def load(f):
    with open(f, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def check(T, ref):
    R = {(r["variant"], r["dataset"]): r for r in ref if r["variant"] in ("v5", "v5s")}
    same = diff = 0
    for r in T:
        if r["designer_err"] or r["eps_m"] or r["variant"] not in ("v5", "v5s"):
            continue
        q = R.get((r["variant"], r["dataset"]))
        if q is None:
            continue
        a = (r["certified"], r["questions"], r["gold_good"])
        b = (q["certified"], q["questions"], q["gold_good"])
        if a == b:
            same += 1
        else:
            diff += 1
            print(f"  DIFF {r['variant']} {r['dataset']}: v5tol {a} item 32 {b}")
    print(f"  implementation check: {same} identical, {diff} different")
    return diff == 0


def rules(T):
    by = defaultdict(list)
    for r in T:
        by[(r["variant"], r["designer_err"], r["persistent"])].append(r)
    cert = lambda rs: sum(r["certified"] for r in rs)
    wrong = lambda rs: sum(r["wrong_cert"] for r in rs)
    right = lambda rs: sum(r["certified"] and r["cert_exact"] for r in rs)
    good = lambda rs: sum(bool(r["gold_good"]) for r in rs)
    med = lambda rs: statistics.median([r["questions"] for r in rs if r["certified"]]) if cert(rs) else None
    print(f"  {'variant':6s} {'eps':>5s} {'stub':>4s} {'runs':>4s} {'cert':>4s} {'right':>5s} {'wrong':>5s} {'share':>6s} "
          f"{'good':>4s} {'q_med':>6s} {'reask':>5s}")
    for k in sorted(by, key=lambda k: (k[1], k[2], k[0])):
        rs = by[k]
        c = cert(rs)
        print(f"  {k[0]:6s} {k[1]:5.2f} {'yes' if k[2] else '':>4s} {len(rs):4d} {c:4d} {right(rs):5d} {wrong(rs):5d} "
              f"{(wrong(rs) / c if c else 0):6.2f} {good(rs):4d} {str(med(rs)):>6s} "
              f"{sum(r['reask_questions'] for r in rs):5d}")
    g = lambda v, e, p=False: by.get((v, e, p), [])
    for e in (0.02, 0.05):
        t, v = g("v5t", e), g("v5", e)
        u1 = cert(t) > 0 and wrong(t) <= 0.10 * cert(t)
        u2 = cert(t) > 0 and (wrong(t) / cert(t)) < (wrong(v) / cert(v) if cert(v) else 1)
        u3 = right(t) > right(g("v5st", e))
        print(f"  eps {e}: U1 {'holds' if u1 else 'fails'} ({wrong(t)}/{cert(t)}); U2 {'holds' if u2 else 'fails'} "
              f"({wrong(t)}/{cert(t)} vs v5 {wrong(v)}/{cert(v)}); U3 {'holds' if u3 else 'fails'} "
              f"(right {right(t)} vs v5st {right(g('v5st', e))})")
    # the cost at eps = 0, paired by relation
    t0 = {r["dataset"]: r for r in g("v5t", 0.0)}
    v0 = {r["dataset"]: r for r in g("v5", 0.0)}
    both = [d for d in t0 if d in v0 and t0[d]["certified"] and v0[d]["certified"]]
    extra = [t0[d]["questions"] - v0[d]["questions"] for d in both]
    print(f"  cost at eps 0: certificates v5t {cert(list(t0.values()))} vs v5 {cert(list(v0.values()))}; "
          f"extra questions where both certify, median {statistics.median(extra) if extra else None} over {len(both)}")
    s = g("v5t", 0.05, True)
    print(f"  stubborn 0.05: wrong certificates {wrong(s)}/{cert(s)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tol", action="append", required=True)
    ap.add_argument("--ref", action="append", required=True)
    a = ap.parse_args()
    for t, f in zip(a.tol, a.ref):
        T = load(t)
        print(f"== {t}: truth {T[0]['truth'] if T else '?'}, {len(T)} runs")
        check(T, load(f))
        rules(T)


if __name__ == "__main__":
    main()
