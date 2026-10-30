"""
LLM estimator by belief elicitation: one prompt per relation, independent of the number of candidates.

The model sees the number of sample rows, the attribute names with their numbers of distinct values and the declared
key; never the data set's name, the mined candidates, the gold FDs or any label.  It answers with the rules it believes
to be genuine, each with a probability, and a base probability for any other FD.  As in Confirm's prior, a belief is a
random set of rules, each drawn independently with its probability; the probability of a candidate X -> A is the chance
that the drawn rules and the declared key imply it, mixed with the base probability:
    rho(X -> A) = f + (1 - f) * other,      f = P(A in closure of X under the drawn rules)   (Monte Carlo)

Usage:  python llm_rules.py prompts OUTDIR            writes OUTDIR/rNN.txt and llm/rules_batches.json
        python llm_rules.py score ANSWER_DIR TAG       writes llm/scores_TAG.json (same format as llm_collect.py)
"""
import json, os, random, sys
import bench

HERE = os.path.dirname(os.path.abspath(__file__))
SCREENED = {"abalone", "adult", "breast", "bridges", "echo", "hepatitis", "letter", "ncvoter"}
DRAWS = 2000

TEMPLATE = """You know how real-world data is structured. A relation has {rows} sample rows. Its attributes, with the number of distinct values in the sample:
{attrs}

Declared key, known to hold: {key}

Task: state which functional dependencies (FDs) you believe are genuine rules of this relation's domain. A genuine rule holds in every valid instance because of what the attributes mean, not by coincidence in one sample.

Write each rule with a minimal left-hand side and a single attribute on the right, using the exact attribute names above. Give each rule your probability that it is genuine. Include rules you are unsure about with a lower probability, down to 0.05. Do not list FDs that follow from the declared key, and do not list trivial FDs.

Then give one base probability, "other": the chance that an FD over these attributes that does not follow from your rules and the declared key is nonetheless genuine. Be calibrated.

Answer with one JSON object and nothing else, of the form
{{"rules": [{{"lhs": ["A1", "A2"], "rhs": "B", "p": 0.9}}], "other": 0.01}}
"""


def prompts(outdir):
    os.makedirs(outdir, exist_ok=True)
    all_b = bench.benches(3)
    index = {}
    for ds, b in sorted(all_b.items()):
        if ds in SCREENED or not b["P"]:
            continue
        d = json.load(open(os.path.join(bench.E3, ds + ".json"), encoding="utf-8"))
        names, dv, rows = b["names"], d["distinct_values"], d["instance"]["rows"]
        attrs = "\n".join(f"- {a} ({dv.get(a, '?')} distinct)" for a in names)
        key = ", ".join(sorted({names[x] for f in b["sigma0"] for x in f[0]})) if b["sigma0"] else "none"
        name = f"r{len(index) + 1:02d}"
        with open(os.path.join(outdir, name + ".txt"), "w", encoding="utf-8") as fh:
            fh.write(TEMPLATE.format(rows=rows, attrs=attrs, key=key))
        index[name] = ds
    os.makedirs(os.path.join(HERE, "llm"), exist_ok=True)
    json.dump(index, open(os.path.join(HERE, "llm", "rules_batches.json"), "w", encoding="utf-8"), indent=0)
    with open(os.path.join(HERE, "llm", "rules_template.txt"), "w", encoding="utf-8") as fh:
        fh.write(TEMPLATE)
    print(len(index), "relations")


def closure(X, rules):
    c = set(X)
    changed = True
    while changed:
        changed = False
        for l, r in rules:
            if r not in c and l <= c:
                c.add(r)
                changed = True
    return c


def score_relation(b, ans, seed=0):
    """probabilities of the candidates of b given one elicited answer"""
    names = b["names"]
    idx = {a: i for i, a in enumerate(names)}
    key = [(frozenset(f[0]), next(iter(f[1]))) for f in b["sigma0"]]
    rules, bad = [], 0
    for r in ans.get("rules", []):
        try:
            l = frozenset(idx[a] for a in r["lhs"])
            rules.append((l, idx[r["rhs"]], min(max(float(r["p"]), 0.0), 1.0)))
        except (KeyError, TypeError, ValueError):
            bad += 1
    other = min(max(float(ans.get("other", 0.01)), 1e-6), 0.5)
    rnd = random.Random(seed)
    hits = {p: 0 for p in b["P"]}
    for _ in range(DRAWS):
        drawn = key + [(l, r) for l, r, q in rules if rnd.random() < q]
        cache = {}
        for p in b["P"]:
            X = p[0]
            if X not in cache:
                cache[X] = closure(X, drawn)
            if next(iter(p[1])) in cache[X]:
                hits[p] += 1
    pi = {p: hits[p] / DRAWS + (1 - hits[p] / DRAWS) * other for p in b["P"]}
    return pi, len(rules), bad


def score(adir, tag):
    index = json.load(open(os.path.join(HERE, "llm", "rules_batches.json"), encoding="utf-8"))
    all_b = bench.benches(3)
    out = {}
    for name, ds in sorted(index.items()):
        runs = sorted(f for f in os.listdir(adir) if f.startswith(name) and f.endswith(".json"))
        if not runs:
            continue
        b = all_b[ds]
        acc = {p: 0.0 for p in b["P"]}
        for f in runs:                                       # average over repeated elicitations
            pi, n, bad = score_relation(b, json.load(open(os.path.join(adir, f), encoding="utf-8")))
            print(f"{ds:28s} {f:12s} rules={n:3d} unparsed={bad}")
            for p in acc:
                acc[p] += pi[p] / len(runs)
        out[ds] = [[sorted(b["names"][x] for x in p[0]), b["names"][next(iter(p[1]))], v] for p, v in acc.items()]
    json.dump(out, open(os.path.join(HERE, "llm", f"scores_{tag}.json"), "w", encoding="utf-8"), indent=0)
    return out


if __name__ == "__main__":
    if sys.argv[1] == "prompts":
        prompts(sys.argv[2])
    else:
        import llm_collect
        llm_collect.judge(score(sys.argv[2], sys.argv[3]))
