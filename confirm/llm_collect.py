"""
Collect the LLM's answers into per-candidate probabilities and judge them like eval_estimators.py.

Usage:  python llm_collect.py ANSWER_DIR TAG       reads ANSWER_DIR/qNN.json and llm/batches.json,
                                                  writes llm/scores_TAG.json  {data set: [[lhs names], rhs, p], ...}
"""
import json, os, sys
import bench
import estimators as EST

HERE = os.path.dirname(os.path.abspath(__file__))


def collect(adir, tag):
    batches = json.load(open(os.path.join(HERE, "llm", "batches.json"), encoding="utf-8"))
    out, missing = {}, 0
    for name, b in batches.items():
        f = os.path.join(adir, name + ".json")
        ans = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {}
        for i, (lhs, rhs) in b["ids"].items():
            v = ans.get(i)
            if v is None:
                missing += 1
                continue
            out.setdefault(b["dataset"], []).append([lhs, rhs, float(v)])
    json.dump(out, open(os.path.join(HERE, "llm", f"scores_{tag}.json"), "w", encoding="utf-8"), indent=0)
    return out, missing


def as_pi(b, rows, default=None):
    """probabilities keyed by the candidates of bench.load; default for candidates without an answer"""
    names = b["names"]
    idx = {(tuple(sorted(l)), r): p for l, r, p in rows}
    pi = {}
    for p in b["P"]:
        k = (tuple(sorted(names[x] for x in p[0])), names[next(iter(p[1]))])
        if k in idx:
            pi[p] = idx[k]
        elif default is not None:
            pi[p] = default
    return pi


def judge(scores, floors=(1e-3, 1e-4), delta=0.1):
    all_b = bench.benches(3)
    print(f"{'data set':28s} {'n':>5s} {'true':>4s} {'AUC llm':>7s} {'AUC lrn':>7s}  " +
          "  ".join(f"llm@{lo:g}  lrn@{lo:g}" for lo in floors))
    tot = {}
    for ds, rows in sorted(scores.items()):
        b = all_b[ds]
        truth = set(b["truth"])
        pi = as_pi(b, rows, default=0.5)
        train = [v for k, v in all_b.items() if k != ds]
        lr = bench.estimate(b, train, "learned")
        cells = []
        for lo in floors:
            for k, est in (("llm", pi), ("lrn", lr)):
                q, unsafe = EST.cert_cost(est, truth, delta, rho_min=lo, rho_max=0.98)
                t = tot.setdefault((k, lo), [0, 0])
                t[0] += q
                t[1] += unsafe
                cells.append(f"{q:5d}{'*' if unsafe else ' '}")
        a1, a2 = bench.auc(pi, truth), bench.auc(lr, truth)
        f = lambda a: "   -   " if a is None else f"{a:7.3f}"
        print(f"{ds:28s} {len(b['P']):5d} {len(truth):4d} {f(a1)} {f(a2)}  " + "  ".join(cells))
    print("totals (questions, unsafe sets):", {f"{k}@{lo:g}": v for (k, lo), v in tot.items()})


if __name__ == "__main__":
    s, miss = collect(sys.argv[1], sys.argv[2])
    print("missing answers:", miss)
    judge(s)
