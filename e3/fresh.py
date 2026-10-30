"""
The fresh family of E3: the relations of the confirmatory evaluation (design notes, component selection item 28),
never read during development and never used for training.  Each relation is fixed in truth/fresh.json before its data
are downloaded: which files, which many-to-one joins along documented keys, which columns under which names; its
Sigma* is taken from the publisher's documentation alone.

Construction of an instance (instance(ds, spec)):
  load      every table of spec["tables"] from FRESH_RAW/<file> (csv with a delimiter, or parquet), values as published
            up to leading and trailing white space, with the rows that pass its filter ({column: [allowed values]},
            compared after normalisation)
  join      from spec["root"], the joins in order: {"left": ["<table>.<column>", ...], "right": table, "key": [columns]};
            on the published values, since keys such as XBRL tags are case-sensitive; a left join, so a row whose
            reference is missing keeps '?' in the columns of the referenced table; the key of the referenced table
            must be unique after its filter, otherwise the join is not many-to-one.  A file referenced in two roles
            (a city and the country of a message) is two tables with the same file
  columns   spec["columns"] maps "<table>.<column>" to the attribute name, in the order of spec["attributes"]
  clean     as real.py does for the real data of development, after the joins: every value trimmed, white space
            collapsed, upper case, empty as '?' (documented.norm of prior work); values that differ only in case
            or spacing become equal here, and the repair below settles any FD this breaks; duplicate records
            removed; above MAX_ROWS records a sample
            of MAX_ROWS with a fixed seed; then the greedy subset repair of prior work (documented.subset_repair) for
            the sure FDs of Sigma*, so that they hold on the instance; the records it removes are reported per FD.
            FRESH_NO_REPAIR=1 skips the repair (design note item 42 (a): the data as published, sampled the same way)

python fresh.py check  validates truth/fresh.json against the rules above without reading any data.
"""
import csv, json, os, random, re, sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
FRESH_RAW = os.environ.get("FRESH_RAW", os.path.join(HERE, "fresh_raw"))
MAX_ROWS, MAX_COLS, MIN_ROWS, SEED = 1_000_000, 25, 1000, 0
WS = re.compile(r"\s+")
csv.field_size_limit(1 << 30)


def norm(v):
    """documented.norm of prior work"""
    v = WS.sub(" ", "" if v is None else str(v)).strip().upper()
    return v if v else "?"


def subset_repair(rows, fds, names):
    """documented.subset_repair of prior work: the indices of the records kept; per FD the records it removed"""
    alive = list(range(len(rows)))
    removed = Counter()
    changed = True
    while changed:
        changed = False
        for X, A in fds:
            groups = defaultdict(Counter)
            for i in alive:
                groups[tuple(rows[i][x] for x in X)][rows[i][A]] += 1
            keep = {k: min(c.items(), key=lambda t: (-t[1], t[0]))[0] for k, c in groups.items() if len(c) > 1}
            if not keep:
                continue
            new = [i for i in alive if keep.get(tuple(rows[i][x] for x in X), rows[i][A]) == rows[i][A]]
            removed[",".join(names[x] for x in X) + "->" + names[A]] += len(alive) - len(new)
            alive = new
            changed = True
    return alive, removed


def needed(spec):
    """per table, the source columns that the joins and the attributes read"""
    out = defaultdict(set)
    for q in spec["columns"]:
        t, c = q.split(".", 1)
        out[t].add(c)
    for j in spec["joins"]:
        for q in j["left"]:
            t, c = q.split(".", 1)
            out[t].add(c)
        out[j["right"]].update(j["key"])
    return out


def load(name, tab, cols):
    """the rows of one table as dicts over cols (published values, stripped), after its filter"""
    return list(stream(name, tab, cols))


def stream(name, tab, cols):
    """load() as a generator, in file order: the root table of a join is read this way, never held as a whole"""
    path = os.path.join(FRESH_RAW, tab["file"])
    flt = {c: {norm(v) for v in vs} for c, vs in tab.get("filter", {}).items()}
    want = sorted(set(cols) | set(flt))
    raw = lambda v: "" if v is None else str(v).strip()
    if path.endswith(".parquet"):
        import pyarrow.parquet as pq
        T = pq.read_table(path, columns=want)
        data = {c: T.column(c).to_pylist() for c in want}
        recs = ({c: raw(data[c][i]) for c in want} for i in range(T.num_rows))
    else:
        fh = open(path, encoding=tab.get("encoding", "utf-8"), newline="")
        r = csv.DictReader(fh, delimiter=tab.get("delimiter", ","))
        missing = [c for c in want if c not in r.fieldnames]
        assert not missing, f"{name}: columns {missing} not in {tab['file']}"
        recs = ({c: raw(rec[c]) for c in want} for rec in r)
    return (rec for rec in recs if all(norm(rec[c]) in vs for c, vs in flt.items()))


def build(spec):
    """(attribute names, rows as tuples) of the joined relation, normalised (documented.norm), before cleaning.
    The root table is streamed and equal values share one string object (same rows, same order as loading it whole),
    so that a root of tens of millions of records (GHCN, ChEMBL, GeoNames of item 33) fits in memory."""
    need = needed(spec)
    root = spec["root"]
    whole = {j["right"] for j in spec["joins"]} | {t for t in spec["tables"] if t != root}
    tabs = {t: load(t, spec["tables"][t], need[t]) for t in whole}
    index = {}
    for j in spec["joins"]:
        r = j["right"]
        idx = {}
        for rec in tabs[r]:
            k = tuple(rec[c] for c in j["key"])
            assert k not in idx, f"key {j['key']} of {r} is not unique: {k}"
            idx[k] = rec
        index[id(j)] = idx
    names = spec["attributes"]
    source = {a: q for q, a in spec["columns"].items()}
    order = [source[a] for a in names]
    rows = []
    share = {}
    for rec in tabs[root] if root in tabs else stream(root, spec["tables"][root], need[root]):
        row = {f"{root}.{c}": v for c, v in rec.items()}
        for j in spec["joins"]:
            k = tuple(row.get(q, "") for q in j["left"])
            ref = index[id(j)].get(k) if all(k) else None
            for c in need[j["right"]]:
                row[f"{j['right']}.{c}"] = ref[c] if ref is not None else ""
        rows.append(tuple(share.setdefault(v, v) for v in (norm(row[q]) for q in order)))
    return names, rows


def single(truth, names, sure_only=True):
    """the FDs of Sigma* as (lhs indices, rhs index), one right-hand side each"""
    idx = {a: i for i, a in enumerate(names)}
    return [(tuple(idx[x] for x in f["lhs"]), idx[a]) for f in truth if f["sure"] or not sure_only
            for a in f["rhs"] if a not in f["lhs"]]


def clean(names, rows, truth):
    n = len(rows)
    rows = list(dict.fromkeys(rows))
    dedup = len(rows)
    sampled = None
    if len(rows) > MAX_ROWS:
        sampled = len(rows)
        rows = random.Random(SEED).sample(rows, MAX_ROWS)
    repair = os.environ.get("FRESH_NO_REPAIR") != "1"
    alive, removed = subset_repair(rows, single(truth, names), names) if repair else (range(len(rows)), Counter())
    kept = [rows[i] for i in alive]
    return kept, {"records": n, "records_after_deduplication": dedup, "sampled_from": sampled, "kept": len(kept),
                  "repaired_for": "the sure FDs of Sigma*" if repair else None, "removed_per_fd": dict(removed.most_common()),
                  "missing_values": "empty and missing references become '?', kept as a value (null = null)"}


def instance(ds, spec):
    from real import columns
    names, rows = build(spec["spec"])
    kept, info = clean(names, rows, spec["truth"])
    out = columns(names, kept)
    out["cleaning"] = info
    return out


def check(doc):
    """the rules of item 28 that the specification alone decides; returns the problems found"""
    bad = []
    for ds, e in doc["datasets"].items():
        sp, names = e["spec"], e["attributes"]
        if not e.get("construction"):
            bad.append(f"{ds}: no construction text")
        if sp["attributes"] != names:
            bad.append(f"{ds}: spec attributes differ from the entry")
        if len(names) > MAX_COLS:
            bad.append(f"{ds}: {len(names)} columns > {MAX_COLS}")
        if sorted(sp["columns"].values()) != sorted(names) or len(set(names)) != len(names):
            bad.append(f"{ds}: columns do not map one to one onto the attributes")
        tabs = set(sp["tables"])
        joined = {sp["root"]}
        for j in sp["joins"]:
            if not all(q.split(".", 1)[0] in joined for q in j["left"]):
                bad.append(f"{ds}: join to {j['right']} reads a table not joined yet")
            if len(j["left"]) != len(j["key"]):
                bad.append(f"{ds}: join to {j['right']} has {len(j['left'])} columns against a key of {len(j['key'])}")
            joined.add(j["right"])
        if joined != tabs:
            bad.append(f"{ds}: tables {sorted(tabs - joined)} never joined")
        for q in sp["columns"]:
            if q.split(".", 1)[0] not in tabs:
                bad.append(f"{ds}: column {q} of an unknown table")
        for f in e["truth"]:
            if not set(f["lhs"]) | set(f["rhs"]) <= set(names):
                bad.append(f"{ds}: FD {f['lhs']} -> {f['rhs']} outside the attributes")
            if not f.get("clause") or "sure" not in f:
                bad.append(f"{ds}: FD {f['lhs']} -> {f['rhs']} without a clause or a sure flag")
    return bad


if __name__ == "__main__":
    if sys.argv[1:2] == ["check"]:          # optional path: the second batch is truth/fresh2.json (item 33)
        path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "truth", "fresh.json")
        with open(path, encoding="utf-8") as fh:
            problems = check(json.load(fh))
        print("\n".join(problems) or f"{os.path.basename(path)}: no problems")
        sys.exit(1 if problems else 0)
    print(__doc__)
