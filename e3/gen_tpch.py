"""
Denormalized TPC-H tables for E3: wide tables obtained by joining dbgen output along the foreign keys of
Clause 1.4.2.3 (the joins, column lists and Sigma* are in truth/tpch.json).

Columns are kept dictionary-encoded (Col: integer codes and the list of distinct values), which keeps the 600,572
rows of LINEITEM in memory cheaply; joins are index lookups on the referenced primary key.

Usage:  python gen_tpch.py <dir with the dbgen .tbl files> [--csv OUTDIR]
"""
import json, os, sys
from array import array
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

COLUMNS = {   # Clause 1.4.1, in .tbl order
    "region": ["r_regionkey", "r_name", "r_comment"],
    "nation": ["n_nationkey", "n_name", "n_regionkey", "n_comment"],
    "supplier": ["s_suppkey", "s_name", "s_address", "s_nationkey", "s_phone", "s_acctbal", "s_comment"],
    "part": ["p_partkey", "p_name", "p_mfgr", "p_brand", "p_type", "p_size", "p_container", "p_retailprice",
             "p_comment"],
    "partsupp": ["ps_partkey", "ps_suppkey", "ps_availqty", "ps_supplycost", "ps_comment"],
    "customer": ["c_custkey", "c_name", "c_address", "c_nationkey", "c_phone", "c_acctbal", "c_mktsegment",
                 "c_comment"],
    "orders": ["o_orderkey", "o_custkey", "o_orderstatus", "o_totalprice", "o_orderdate", "o_orderpriority",
               "o_clerk", "o_shippriority", "o_comment"],
    "lineitem": ["l_orderkey", "l_partkey", "l_suppkey", "l_linenumber", "l_quantity", "l_extendedprice",
                 "l_discount", "l_tax", "l_returnflag", "l_linestatus", "l_shipdate", "l_commitdate",
                 "l_receiptdate", "l_shipinstruct", "l_shipmode", "l_comment"],
}


class Col:
    """A dictionary-encoded column: codes (int32 array) into the list of distinct values."""

    def __init__(self, codes, values):
        self.codes, self.values = np.asarray(codes, dtype=np.int32), list(values)

    def take(self, idx):
        return Col(self.codes[idx], self.values)

    def map(self, f):
        uniq = {}
        remap = np.array([uniq.setdefault(f(v), len(uniq)) for v in self.values], dtype=np.int32)
        return Col(remap[self.codes], list(uniq))

    def decoded(self):
        return [self.values[c] for c in self.codes.tolist()]

    def __len__(self):
        return len(self.codes)


def read_tbl(path, names):
    vocab = [dict() for _ in names]
    codes = [array("i") for _ in names]
    with open(path, encoding="latin-1") as fh:
        for line in fh:
            f = line.rstrip("\r\n").split("|")
            for j, d in enumerate(vocab):
                c = d.get(f[j])
                if c is None:
                    c = d[f[j]] = len(d)
                codes[j].append(c)
    return {nm: Col(np.frombuffer(codes[j], dtype=np.int32), vocab[j]) for j, nm in enumerate(names)}


def load(tbl_dir, tables=None):
    return {t: read_tbl(os.path.join(tbl_dir, t + ".tbl"), COLUMNS[t]) for t in (tables or COLUMNS)}


def lookup(fk, pk):
    """Row index in the referenced table for every row of the referencing column (pk is unique)."""
    pos = {v: i for i, v in enumerate(pk.decoded())}
    m = np.array([pos[v] for v in fk.values], dtype=np.int64)    # raises KeyError on a dangling reference
    return m[fk.codes]


def wide_tables(T):
    spec = json.load(open(os.path.join(HERE, "truth", "tpch.json"), encoding="utf-8"))["datasets"]
    out = {}

    # tpch_orders_customer: ORDERS -> CUSTOMER -> NATION -> REGION
    o = T["orders"]
    ci = lookup(o["o_custkey"], T["customer"]["c_custkey"])
    c = {k: v.take(ci) for k, v in T["customer"].items()}
    ni = lookup(c["c_nationkey"], T["nation"]["n_nationkey"])
    n = {k: v.take(ni) for k, v in T["nation"].items()}
    ri = lookup(n["n_regionkey"], T["region"]["r_regionkey"])
    r = {k: v.take(ri) for k, v in T["region"].items()}
    cols = {**{k: v for k, v in o.items() if k != "o_shippriority"},
            **{k: v for k, v in c.items() if k != "c_custkey"},
            **{k: v for k, v in n.items() if k != "n_nationkey"},
            **{k: v for k, v in r.items() if k != "r_regionkey"}}
    out["tpch_orders_customer"] = cols

    # tpch_partsupp_part_supplier: PARTSUPP -> PART, PARTSUPP -> SUPPLIER
    ps = T["partsupp"]
    p = {k: v.take(lookup(ps["ps_partkey"], T["part"]["p_partkey"])) for k, v in T["part"].items()}
    s = {k: v.take(lookup(ps["ps_suppkey"], T["supplier"]["s_suppkey"])) for k, v in T["supplier"].items()}
    out["tpch_partsupp_part_supplier"] = {**ps, **{k: v for k, v in p.items() if k != "p_partkey"},
                                          **{k: v for k, v in s.items() if k != "s_suppkey"}}

    # tpch_lineitem_orders: LINEITEM -> ORDERS
    li = T["lineitem"]
    oi = lookup(li["l_orderkey"], o["o_orderkey"])
    out["tpch_lineitem_orders"] = {**li, **{k: v.take(oi) for k, v in o.items()
                                            if k not in ("o_orderkey", "o_shippriority")}}

    for ds, cols in out.items():
        attrs = spec[ds]["attributes"]
        assert sorted(cols) == sorted(attrs), (ds, set(cols) ^ set(attrs))
        out[ds] = {"attributes": attrs, "cols": [cols[a] for a in attrs]}
    return out


def write_csv(path, attrs, cols):
    import csv
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(attrs)
        w.writerows(zip(*[c.decoded() for c in cols]))


if __name__ == "__main__":
    T = load(sys.argv[1])
    for t, cols in T.items():
        print(t, len(next(iter(cols.values()))), "rows")
    W = wide_tables(T)
    for ds, d in W.items():
        print(ds, len(d["attributes"]), "columns", len(d["cols"][0]), "rows")
        if "--csv" in sys.argv:
            write_csv(os.path.join(sys.argv[sys.argv.index("--csv") + 1], ds + ".csv"), d["attributes"], d["cols"])
