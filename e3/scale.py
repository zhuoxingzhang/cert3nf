"""
Synthetic relations for the scale experiment (design note item 53): denormalized joins of a snowflake schema whose
Sigma* is given by construction and holds on the data by construction.  Two sweeps, 20,000 rows each:
  width:  n in {10, 20, 30, 40, 50} attributes, a share 0.6 of the non-key attributes on the entity side;
  FDs:    n = 30, an entity-side share in {0.2, 0.4, 0.6, 0.8};
three seeds per configuration.

The fact key (order, line) is the declared key, with one to seven lines per order.  Every other attribute is a measure,
which only the fact key determines, or belongs to an entity.  The entities form a tree under the fact: an entity has a
key attribute, one to four descriptive attributes and, with probability 0.3, a name that is a second key; its parent is
the fact, which references it directly, or an earlier entity, among them the order entity of the fact key.
Sigma*: the key of an entity determines its descriptive attributes, its name and the keys of its child entities, the
name determines the key, and the fact key determines every attribute.  A child entity has between 5 and half the
cardinality of its parent, log-uniformly; a descriptive attribute takes values from a domain of 2 to the entity's
cardinality, a measure from 2 to the number of rows, both log-uniformly, and every value is drawn uniformly.  The
attributes are named A01, A02, ... in a random order, so that neither names nor positions reveal the structure.

The relations then pass the stages of build.py, as every other relation does:
  python scale.py all            # writes truth/scale.json, mines (mined/), writes data/scale_*.json
  python scale.py gen | mine | json [--only ds1,ds2]
"""
import json, math, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build      # noqa: E402

ROWS = 20000
WIDTHS, SHARE = (10, 20, 30, 40, 50), 0.6
FD_WIDTH, SHARES = 30, (0.2, 0.4, 0.6, 0.8)
SEEDS = (0, 1, 2)
TRUTH = os.path.join(HERE, "truth", "scale.json")


def configs():
    out = [(n, SHARE) for n in WIDTHS] + [(FD_WIDTH, s) for s in SHARES if s != SHARE]
    return [(n, s, seed) for n, s in out for seed in SEEDS]


def name(n, share, seed):
    return f"scale_n{n:02d}_d{round(100 * share):02d}_s{seed}"


def loguni(rng, lo, hi):
    return int(round(math.exp(rng.uniform(math.log(lo), math.log(max(hi, lo))))))


def generate(n, share, seed, rows=ROWS):
    """(attribute names, columns as int arrays, Sigma* as {lhs, rhs, sure} items, declared key)"""
    rng = np.random.default_rng([n, round(100 * share), seed])
    orders = rows // 4
    lines = rng.integers(1, 8, orders)
    order = np.repeat(np.arange(orders), lines)
    line = np.concatenate([np.arange(k) for k in lines])
    R = len(order)
    attrs = [("order", order), ("line", line)]            # internal names; renamed at the end
    truth = []
    rest = n - 2
    ent_budget = round(share * rest)
    # entities: name -> (cardinality, value of its key per row); the order entity's key is part of the fact key
    ents = {"order": (orders, order)}
    parents = ["fact", "order"]
    used, k = 0, 0
    while used < ent_budget:
        k += 1
        e = f"e{k}"
        par = parents[rng.integers(len(parents))]
        if par == "fact":                                   # a reference of the fact: the fact key determines it
            card = loguni(rng, 5, orders // 2)
            key = rng.integers(card, size=R)
        else:                                               # a child entity, referenced by its parent's key
            pc, pkey = ents[par]
            card = loguni(rng, 5, max(5, pc // 2))
            key = rng.integers(card, size=pc)[pkey]
            truth.append({"lhs": [par], "rhs": [e]})
        ents[e] = (card, key)
        attrs.append((e, key))
        used += 1
        parents.append(e)
        size = min(int(rng.integers(1, 5)), ent_budget - used)
        for j in range(size):
            a = f"{e}_a{j}"
            dom = loguni(rng, 2, card)
            attrs.append((a, rng.integers(dom, size=card)[key]))
            truth.append({"lhs": [e], "rhs": [a]})
            used += 1
        if used < ent_budget and rng.random() < 0.3:
            a = f"{e}_name"
            attrs.append((a, rng.permutation(card)[key]))
            truth += [{"lhs": [e], "rhs": [a]}, {"lhs": [a], "rhs": [e]}]
            used += 1
    if used < ent_budget:                                   # cannot happen: the loop adds at least one attribute
        raise AssertionError
    # the remaining non-key attributes are measures of the fact
    for j in range(n - len(attrs)):
        dom = loguni(rng, 2, R)
        attrs.append((f"m{j}", rng.integers(dom, size=R)))
    assert len(attrs) == n
    perm = rng.permutation(n)
    new = {attrs[i][0]: f"A{p + 1:02d}" for i, p in enumerate(perm)}
    cols = [None] * n
    for i, (a, c) in enumerate(attrs):
        cols[perm[i]] = c
    names = [f"A{p + 1:02d}" for p in range(n)]
    key = [new["order"], new["line"]]
    sigma = [{"lhs": [new[x] for x in t["lhs"]], "rhs": [new[x] for x in t["rhs"]], "sure": True,
              "clause": "construction"} for t in truth]
    sigma.insert(0, {"lhs": key, "rhs": [a for a in names if a not in key], "sure": True, "clause": "fact key"})
    return names, cols, sigma, key


class Col:
    def __init__(self, codes):
        self.codes = codes


def gen():
    spec = {"truth_kind": "synthetic (construction)",
            "source": "e3/scale.py: synthetic snowflake joins for the scale experiment (design note item 53)",
            "rule": "Sigma* is the set of FDs of the construction: entity keys determine their attributes, names and "
                    "child keys, names determine keys, and the fact key determines every attribute",
            "datasets": {}}
    for n, s, seed in configs():
        names, _, sigma, key = generate(n, s, seed)
        spec["datasets"][name(n, s, seed)] = {"attributes": names, "truth": sigma, "key": key,
                                              "construction": f"scale.py generate({n}, {s}, {seed}), {ROWS} rows"}
    with open(TRUTH, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=1)
    print("wrote", TRUTH, len(spec["datasets"]), "relations")


def register():
    """make build.py treat the relations of truth/scale.json as the family "scale" """
    with open(TRUTH, encoding="utf-8") as fh:
        dss = list(json.load(fh)["datasets"])
    build.FAMILIES["scale"] = dss
    build.FAMILY.update({ds: "scale" for ds in dss})
    build.INSTANCE["scale"] = {"generator": "e3/scale.py (synthetic snowflake join)", "scale_factor": None}
    old = build.instances

    def instances(tbl_dir, wanted):
        out = {}
        for ds in wanted:
            if build.FAMILY[ds] != "scale":
                out.update(old(tbl_dir, [ds]))
                continue
            n, s, seed = (int(ds.split("_")[1][1:]), int(ds.split("_")[2][1:]) / 100, int(ds.split("_")[3][1:]))
            names, cols, _, _ = generate(n, s, seed)
            out[ds] = {"cols": [Col(c) for c in cols], "attributes": names}
        return out

    build.instances = instances
    return dss


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None
    if cmd in ("gen", "all"):
        gen()
    dss = register()
    wanted = [ds for ds in dss if only is None or ds in only]
    if cmd in ("mine", "all"):
        build.stage_mine(None, wanted)
    if cmd in ("json", "all"):
        build.stage_json(wanted)


if __name__ == "__main__":
    main()
