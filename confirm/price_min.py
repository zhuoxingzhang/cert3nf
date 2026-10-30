"""The price as a shortest proof (design note item 45, Thm. price (d)): |F| + m_r with F a smallest set of FDs that
generates Sigma* with Sigma0, from the bounds of cover_bounds.py (cb45/*.json; exact where its lower and upper bounds
meet), in place of the cover of price.py, which takes the smallest of four elimination orders of the documented FDs
and can be larger.  m_r counts the held sets once, as price_sets.py does.

Writes <dir>/price_min.json with the fields of <dir>/price_sets.json, "cover" and "price" replaced, the old values
kept as "cover_orders4" and "price_orders4", and "cover_lb" and "cover_exact" added.  The report scripts read it
with PRICE_FILE=price_min.json.
Usage (in confirm):  python price_min.py cb45 v5_dev v5_fresh2"""
import glob, json, os, sys

cb, dirs = sys.argv[1], sys.argv[2:]
B = {}
for f in glob.glob(os.path.join(cb, "*.json")):          # every bound holds, so the tightest pair is taken
    for k, r in json.load(open(f, encoding="utf-8")).items():
        o = B.get(k, r)
        B[k] = {"cover_ub": min(r["cover_ub"], o["cover_ub"]), "cover_lb": max(r["cover_lb"], o["cover_lb"])}
for d in dirs:
    P = json.load(open(os.path.join(d, "price_sets.json"), encoding="utf-8"))
    out = {}
    for k, p in P.items():
        c = B[k]
        out[k] = {**p, "cover_orders4": p["cover"], "price_orders4": p["price"], "cover": c["cover_ub"],
                  "cover_lb": c["cover_lb"], "cover_exact": c["cover_lb"] == c["cover_ub"],
                  "price": c["cover_ub"] + p["m_star"]}
        if out[k]["price"] != p["price"]:
            print(f"{d:10s} {k:34s} cover {p['cover']:3d} -> {c['cover_ub']:3d} (lb {c['cover_lb']}) "
                  f"price {p['price']:3d} -> {out[k]['price']:3d}")
    json.dump(out, open(os.path.join(d, "price_min.json"), "w", encoding="utf-8"), indent=1)
    print(d, "relations", len(out), "exact", sum(v["cover_exact"] for v in out.values()))
