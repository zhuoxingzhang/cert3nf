"""
Star Schema Benchmark (O'Neil, O'Neil, Chen, Revision 3, 2009) tables for E3, derived from TPC-H dbgen output by the
rules of the SSB specification, Sections 2.2 to 2.6 (no ssb-dbgen was available).  Where the specification leaves a
column open, the choice made here is stated in CHOICES and in truth/ssb.json, and the FDs it forces are marked
"sure": false there.

The date table is a pure function of the calendar, so calendar(y0, y1) also generates the 400-year table on which
build.py checks that Sigma* of ssb_date holds on every range of years and implies every FD that does.

Usage:  python gen_ssb.py <dir with the TPC-H SF 0.1 .tbl files>
"""
import datetime, os, sys
import numpy as np
import gen_tpch
from gen_tpch import Col

SF = 0.1
SEED = 20091605
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
SEASON = {12: "Christmas", 1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring", 5: "Spring", 6: "Summer",
          7: "Summer", 8: "Summer", 9: "Fall", 10: "Fall", 11: "Fall"}
HOLIDAYS = {(1, 1), (7, 4), (12, 25)}
COLORS = ("almond antique aquamarine azure beige bisque black blanched blue blush brown burlywood burnished "
          "chartreuse chiffon chocolate coral cornflower cornsilk cream cyan dark deep dim dodger drab firebrick "
          "floral forest frosted gainsboro ghost goldenrod green grey honeydew hot indian ivory khaki lace lavender "
          "lawn lemon light lime linen magenta maroon medium metallic midnight mint misty moccasin navajo navy olive "
          "orange orchid pale papaya peach peru pink plum powder puff purple red rose rosy royal saddle salmon sandy "
          "seashell sienna sky slate smoke snow spring steel tan thistle tomato turquoise violet wheat white "
          "yellow").split()   # TPC-H Clause 4.2.3, P_NAME word list (92 words)

N_CUST, N_SUPP, N_PART = int(SF * 30000), int(SF * 2000), int(SF * 200000)
CHOICES = {
    "scale": f"SF = {SF}: {N_CUST} customers (SF*30,000), {N_SUPP} suppliers (SF*2,000), {N_PART} parts. The part "
             "cardinality 200,000*floor(1+log2 SF) of Section 2.3 is not positive for SF < 1, so SF*200,000 is used, "
             "which keeps every TPC-H L_PARTKEY a valid LO_PARTKEY.",
    "customer": "The TPC-H customers with C_CUSTKEY <= 3,000, keeping name, address, phone and market segment. "
                "C_NATION and C_REGION are the TPC-H N_NAME and R_NAME of the customer's nation. C_CITY is the "
                "nation name padded or cut to 9 characters followed by a random digit 0-9.",
    "supplier": "The TPC-H suppliers with S_SUPPKEY <= 200, built as the customers.",
    "part": "All TPC-H parts. P_NAME is the first two of the five distinct colour words of the TPC-H P_NAME. P_MFGR "
            "is 'MFGR#M' and P_CATEGORY is 'MFGR#MN' for the TPC-H 'Manufacturer#M' and 'Brand#MN'. P_BRAND1 is "
            "P_CATEGORY followed by a random number 1-40. P_COLOR is a random word of the TPC-H colour list (92 "
            "words; the specification says CARD = 94), drawn independently of P_NAME. Type, size and container are "
            "copied.",
    "date": "Every day from 1992-01-01 to 1998-12-31 (2,557 days). D_DAYNUMINWEEK numbers Sunday = 1 to Saturday = 7 "
            "(Section 2.6 lists Sunday..Saturday). D_WEEKNUMINYEAR counts weeks starting on Sunday, week 1 being "
            "the week of January 1. D_SELLINGSEASON is a function of the month (Christmas = December, Winter = "
            "January-February, Spring, Summer, Fall). D_HOLIDAYFL marks January 1, July 4 and December 25. "
            "D_LASTDAYINWEEKFL marks Saturday, D_WEEKDAYFL marks Monday to Friday.",
    "lineorder": "TPC-H LINEITEM joined with ORDERS. LO_CUSTKEY = (O_CUSTKEY - 1) mod 3,000 + 1 and LO_SUPPKEY = "
                 "(L_SUPPKEY - 1) mod 200 + 1 map the TPC-H keys onto the smaller SSB dimensions; the four suppliers "
                 "of a part stay distinct under this map at SF 0.1. Dates become YYYYMMDD keys, prices are in "
                 "cents, LO_DISCOUNT and LO_TAX are percentages. LO_REVENUE = LO_EXTENDEDPRICE * (100 - "
                 "LO_DISCOUNT) / 100 with integer division (Section 2.2). LO_SUPPLYCOST is the PS_SUPPLYCOST of the "
                 "TPC-H (L_PARTKEY, L_SUPPKEY) pair, the column of the frozen PARTSUPP that Section 2.1 moves into "
                 "the fact table. LO_SHIPPRIORITY is the constant TPC-H O_SHIPPRIORITY = 0 and is dropped.",
}


def cents(v):
    return int(round(float(v) * 100))


def datekey(v):
    return int(v.replace("-", ""))


def encode(values):
    uniq = {}
    codes = np.array([uniq.setdefault(v, len(uniq)) for v in values], dtype=np.int32)
    return Col(codes, list(uniq))


def geography(T, table, key, nkey, n):
    """Rows with key <= n, with nation name, region name and SSB city (nation prefix + random digit)."""
    rows = np.nonzero(np.array([int(v) for v in T[table][key].decoded()]) <= n)[0]
    nat = {r: v for r, v in zip(T["nation"]["n_nationkey"].decoded(), T["nation"]["n_name"].decoded())}
    reg = {r: v for r, v in zip(T["region"]["r_regionkey"].decoded(), T["region"]["r_name"].decoded())}
    n2r = {k: reg[r] for k, r in zip(T["nation"]["n_nationkey"].decoded(), T["nation"]["n_regionkey"].decoded())}
    nk = T[table][nkey].take(rows)
    nation = nk.map(lambda k: nat[k])
    region = nk.map(lambda k: n2r[k])
    rng = np.random.default_rng([SEED, n])
    digit = rng.integers(0, 10, size=len(rows))
    city = encode([nm[:9].ljust(9) + str(d) for nm, d in zip(nation.decoded(), digit.tolist())])
    return rows, city, nation, region


def calendar(y0, y1):
    """The SSB DATE dimension for every day of the years y0..y1 (choices in CHOICES['date'])."""
    rows, d = [], datetime.date(y0, 1, 1)
    one = datetime.timedelta(days=1)
    while d.year <= y1:
        jan1 = datetime.date(d.year, 1, 1)
        doy = (d - jan1).days + 1
        dow = (d.weekday() + 1) % 7                       # Sunday = 0
        off = (jan1.weekday() + 1) % 7
        nxt = d + one
        rows.append((d.year * 10000 + d.month * 100 + d.day, f"{MONTHS[d.month - 1]} {d.day}, {d.year}",
                     DAYS[dow], MONTHS[d.month - 1], d.year, d.year * 100 + d.month,
                     f"{MONTHS[d.month - 1][:3]}{d.year}", dow + 1, d.day, doy, d.month, (doy - 1 + off) // 7 + 1,
                     SEASON[d.month], int(dow == 6), int(nxt.month != d.month), int((d.month, d.day) in HOLIDAYS),
                     int(1 <= dow <= 5)))
        d = nxt
    return [encode(c) for c in zip(*rows)]


DATE_ATTRS = ["d_datekey", "d_date", "d_dayofweek", "d_month", "d_year", "d_yearmonthnum", "d_yearmonth",
              "d_daynuminweek", "d_daynuminmonth", "d_daynuminyear", "d_monthnuminyear", "d_weeknuminyear",
              "d_sellingseason", "d_lastdayinweekfl", "d_lastdayinmonthfl", "d_holidayfl", "d_weekdayfl"]


def ssb_tables(T):
    out = {}

    rows, city, nation, region = geography(T, "customer", "c_custkey", "c_nationkey", N_CUST)
    c = {k: v.take(rows) for k, v in T["customer"].items()}
    out["ssb_customer"] = {"attributes": ["c_custkey", "c_name", "c_address", "c_city", "c_nation", "c_region",
                                          "c_phone", "c_mktsegment"],
                           "cols": [c["c_custkey"], c["c_name"], c["c_address"], city, nation, region, c["c_phone"],
                                    c["c_mktsegment"]]}

    rows, city, nation, region = geography(T, "supplier", "s_suppkey", "s_nationkey", N_SUPP)
    s = {k: v.take(rows) for k, v in T["supplier"].items()}
    out["ssb_supplier"] = {"attributes": ["s_suppkey", "s_name", "s_address", "s_city", "s_nation", "s_region",
                                          "s_phone"],
                           "cols": [s["s_suppkey"], s["s_name"], s["s_address"], city, nation, region, s["s_phone"]]}

    p = T["part"]
    assert len(p["p_partkey"]) == N_PART
    rng = np.random.default_rng([SEED, 3])
    category = p["p_brand"].map(lambda b: "MFGR#" + b.split("#")[1])
    out["ssb_part"] = {"attributes": ["p_partkey", "p_name", "p_mfgr", "p_category", "p_brand1", "p_color",
                                      "p_type", "p_size", "p_container"],
                       "cols": [p["p_partkey"], p["p_name"].map(lambda v: " ".join(v.split()[:2])),
                                p["p_mfgr"].map(lambda v: "MFGR#" + v.split("#")[1]), category,
                                encode([cat + str(k) for cat, k in
                                        zip(category.decoded(), rng.integers(1, 41, size=N_PART).tolist())]),
                                encode(rng.choice(COLORS, size=N_PART).tolist()),
                                p["p_type"], p["p_size"], p["p_container"]]}

    out["ssb_date"] = {"attributes": DATE_ATTRS, "cols": calendar(1992, 1998)}

    li, o = T["lineitem"], T["orders"]
    oi = gen_tpch.lookup(li["l_orderkey"], o["o_orderkey"])
    o = {k: v.take(oi) for k, v in o.items()}
    ps = T["partsupp"]
    cost = {(a, b): cents(v) for a, b, v in zip(ps["ps_partkey"].decoded(), ps["ps_suppkey"].decoded(),
                                                ps["ps_supplycost"].decoded())}
    ext = li["l_extendedprice"].map(cents)
    disc = li["l_discount"].map(cents)
    supp = li["l_suppkey"].map(lambda v: (int(v) - 1) % N_SUPP + 1)
    pairs = list(zip(li["l_partkey"].decoded(), li["l_suppkey"].decoded()))
    assert len(set(zip(li["l_partkey"].decoded(), supp.decoded()))) == len(set(pairs))   # supplier map injective
    out["ssb_lineorder"] = {
        "attributes": ["lo_orderkey", "lo_linenumber", "lo_custkey", "lo_partkey", "lo_suppkey", "lo_orderdate",
                       "lo_orderpriority", "lo_quantity", "lo_extendedprice", "lo_ordtotalprice", "lo_discount",
                       "lo_revenue", "lo_supplycost", "lo_tax", "lo_commitdate", "lo_shipmode"],
        "cols": [li["l_orderkey"], li["l_linenumber"], o["o_custkey"].map(lambda v: (int(v) - 1) % N_CUST + 1),
                 li["l_partkey"], supp, o["o_orderdate"].map(datekey), o["o_orderpriority"], li["l_quantity"],
                 ext, o["o_totalprice"].map(cents), disc,
                 encode([e * (100 - d) // 100 for e, d in zip(ext.decoded(), disc.decoded())]),
                 encode([cost[pr] for pr in pairs]), li["l_tax"].map(cents), li["l_commitdate"].map(datekey),
                 li["l_shipmode"]]}
    return out


if __name__ == "__main__":
    T = gen_tpch.load(sys.argv[1])
    for ds, d in ssb_tables(T).items():
        print(ds, len(d["attributes"]), "columns", len(d["cols"][0]), "rows")
        for a, c in zip(d["attributes"], d["cols"]):
            print("   ", a, len(c.values), "distinct, e.g.", c.values[:3])
