"""
Real data with gold FDs for E3.  Runs on the experiment server, where the data of prior work are
(the environment variables KLOSS and HPI).

documented (truth/documented.json): the four sets of documented rules of prior work (src/meaningful.py) on the data
of src/documented.py.  The records are normalised as there (trim, collapse white space, upper case, empty value '?'),
duplicates are removed, and the greedy subset repair of documented.py removes records until the base FD set holds.
Unlike documented.py, food is repaired for `food` and not for `food+c1`, so the chains that DBAName -> Zip would
remove stay in.  tpcds_core is store_sales joined with item, store and date_dim of TPC-DS SF 1 (dsdgen), projected
to the 12 attributes of tpcds-core.

screened (truth/screened.json): data sets of the HPI repeatability page whose discovered FDs prior work screened by
the meaning of their attributes (a screening note), with the column names of src/fd_names.py and duplicates removed.

instances(names) -> {ds: {"attributes": [...], "cols": [Col]}};  metanome(ds) -> the discovered FD set of prior work
for the same data, as a set of (lhs names, rhs name), or None.
"""
import csv, json, os, sys
from collections import Counter, defaultdict
from gen_tpch import Col
from gen_ssb import encode

KLOSS = os.environ.get("KLOSS", "")
HPI = os.environ.get("HPI", "")
csv.field_size_limit(1 << 30)

DOCUMENTED = {"food": "food", "pricepaid": "uk", "hospital": "hospital"}   # dataset: base FD set of meaningful.py
TPCDS_CORE = ["ss_ticket_number", "ss_quantity", "ss_sales_price", "i_item_sk", "i_item_id", "i_item_desc",
              "i_current_price", "s_store_sk", "s_store_id", "s_store_name", "d_date_sk", "d_date"]

# file, delimiter, header, the name in prior work (fd_names.NAMES), the discovered FD file of prior work
SCREENED = {
    "abalone": ("abalone.csv", ",", False, "abalone", "complete/abalone.json"),
    "adult": ("adult.csv", ";", False, "adult", "complete/adult.json"),
    "breast": ("breast-cancer-wisconsin.csv", ",", False, "breast(null)", "null-equality/breast.json"),
    "bridges": ("bridges.csv", ",", False, "bridges(null)", "null-equality/bridges.json"),
    "echo": ("echocardiogram.csv", ",", False, "echo(null)", "null-equality/echo.json"),
    "hepatitis": ("hepatitis.csv", ",", False, "hepatitis(null)", "null-equality/hepatitis.json"),
    "letter": ("letter.csv", ",", False, "letter(non-dup)", "complete/letter(non-dup).json"),
    "ncvoter": ("ncvoter_1001r_19c.csv", ",", True, "ncvoter(null)", "null-equality/ncvoter.json"),
}


def kloss():
    src = os.path.join(KLOSS, "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    import documented, fd_names, experiments
    return documented, fd_names, experiments


def columns(names, rows):
    return {"attributes": names, "cols": [encode([r[j] for r in rows]) for j in range(len(names))]}


def documented_instance(ds):
    doc, _, _ = kloss()
    names, rows = doc.read(ds)                       # normalised, in the attribute order of the FD set
    rows = list(dict.fromkeys(rows))
    alive, removed = doc.subset_repair(rows, doc.fd_list(DOCUMENTED[ds]), names)
    out = columns(names, [rows[i] for i in alive])
    out["cleaning"] = {"records_after_deduplication": len(rows), "kept": len(alive), "repaired_for": DOCUMENTED[ds],
                       "removed_per_fd": dict(removed.most_common())}
    return out


def tpcds_core_instance():
    doc, _, _ = kloss()
    raw = os.path.join(KLOSS, "data", "documented", "tpcds", "raw")
    want = {"store_sales": ["ss_sold_date_sk", "ss_store_sk", "ss_item_sk", "ss_ticket_number", "ss_quantity",
                            "ss_sales_price"],
            "item": ["i_item_sk", "i_item_id", "i_item_desc", "i_current_price"],
            "store": ["s_store_sk", "s_store_id", "s_store_name"], "date_dim": ["d_date_sk", "d_date"]}

    def table(t):
        cols = doc.TPCDS_COLUMNS[t]
        pos = [cols.index(c) for c in want[t]]
        with open(os.path.join(raw, t + ".dat"), encoding="latin-1") as f:
            for line in f:
                rec = line.rstrip("\n").split("|")
                yield tuple(doc.norm(rec[p]) for p in pos)

    dims = {t: {r[0]: r for r in table(t)} for t in ("item", "store", "date_dim")}
    rows, missing = [], 0
    for date, store, item, ticket, qty, price in table("store_sales"):
        i, s, d = dims["item"].get(item), dims["store"].get(store), dims["date_dim"].get(date)
        if i is None or s is None or d is None:      # dsdgen leaves these keys empty for some sales
            missing += 1
            continue
        rows.append((ticket, qty, price) + i + s + d)
    n = len(rows)
    rows = list(dict.fromkeys(rows))
    out = columns(TPCDS_CORE, rows)
    out["cleaning"] = {"sales_joined": n, "sales_without_item_store_or_date": missing,
                       "records_after_deduplication": len(rows), "kept": len(rows), "repaired_for": None}
    return out


def screened_instance(ds):
    _, fd_names, experiments = kloss()
    path, delim, header, kname, _ = SCREENED[ds]
    names = fd_names.NAMES[kname]
    with open(os.path.join(HPI, path), encoding="utf-8", newline="") as f:
        r = csv.reader(f, delimiter=delim)
        if header:
            next(r)
        rows = [tuple(rec) for rec in r if rec]
    assert all(len(rec) == len(names) for rec in rows), ds
    n = len(rows)
    rows = list(dict.fromkeys(rows))
    out = columns(names, rows)
    out["cleaning"] = {"records": n, "records_after_deduplication": len(rows), "kept": len(rows),
                       "repaired_for": None, "missing_values": "kept as values (null = null), as in prior work"}
    return out


def instances(wanted):
    out = {}
    for ds in wanted:
        if ds in DOCUMENTED:
            out[ds] = documented_instance(ds)
        elif ds == "tpcds_core":
            out[ds] = tpcds_core_instance()
        else:
            out[ds] = screened_instance(ds)
    return out


def metanome(ds, names):
    """The discovered set of prior work (Metanome) on the same data, by attribute name, or None."""
    if ds not in SCREENED:
        return None
    _, fd_names, experiments = kloss()
    path = os.path.join(KLOSS, "data", "fds", SCREENED[ds][4])
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    nm = fd_names.names_of(SCREENED[ds][3], d["R"])
    return {(frozenset(nm[i] for i in f["lhs"]), nm[a]) for f in d["fds"] for a in f["rhs"]}, os.path.relpath(path, KLOSS)
