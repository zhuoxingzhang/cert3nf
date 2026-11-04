"""The price of Thm. price for the FD set the simulated designer answers from since item 32 (CONFIRM_ORACLE=gold).

price.py, price_sets.py and cover_bounds.py take F = sigma0 + the true candidates ("reach").  The runs answer from
sigma0 + gold, and a certificate decides C = closure(sigma0 + gold) intersected with the FDs that hold on r.  The two differ
on a relation where a documented FD is not minimal on the data, or does not hold on it.

  m*_g   the distinct maximal sets of sigma0 + gold that hold on r for some attribute (a maximal set M of A with M -> A
         holding on r is maximal for C as well, and conversely, so these are the held sets of C)
  cover  the bounds of cover_bounds.py for C, whose left-reduced FDs for A are the minimal X u Y with X a minimal
         determinant of A under gold and Y a minimal determinant of A on r

Relations where reach and gold agree keep the recorded values.  Writes <in dir>/price_gold.json with the fields of
price_min.json, "cover", "price", "m_star", "m_r", "cover_lb", "cover_exact" replaced, the recorded ones kept as
"reach_price", "reach_cover", "reach_m_star".
Usage (in confirm):  CONFIRM_ORACLE=gold python price_gold.py IN_price_min.json OUT.json [results.jsonl ...]"""
import json, os, sys
import auto_common as AC
import cover_bounds as CB
from price import closure, maxsets, min_keys


def analyse(b):
    n = len(b["R"])
    full = (1 << n) - 1
    mask = lambda s: sum(1 << i for i in s)
    S0 = [(mask(l), mask(r)) for l, r in b["sigma0"]]
    G = S0 + [(mask(l), mask(r)) for l, r in b["gold"]]
    Rt = S0 + [(mask(l), mask(r)) for l, r in b["truth"]]
    minfd = {}
    for p in b["P"] + b["implied0"]:
        minfd.setdefault(mask(p[1]), []).append(mask(p[0]))
    holds = lambda z, a: any(x & ~z == 0 for x in minfd.get(a, []))
    held, pairs = set(), 0
    for a in range(n):
        for M in maxsets(G, 1 << a, full):
            if holds(M, 1 << a):
                held.add(M)
                pairs += 1
    # does C differ from the reachable truth?  Both are closed, and Rt lies within C, so check the generators of C
    gens, viol = [], 0
    for a in range(n):
        keys = [k & ~(1 << a) for k in min_keys(G + [(1 << a, full)], full) if k != 1 << a]
        zs = set()
        for x in keys:
            if holds(x, 1 << a):
                zs.add(x)
            else:
                viol += 1
                zs.update(x | y for x in [x] for y in minfd.get(1 << a, []))
        zs = sorted(zs, key=lambda z: bin(z).count("1"))
        mins = []
        for z in zs:
            if not any(m & ~z == 0 for m in mins):
                mins.append(z)
        gens += [(z, 1 << a) for z in mins if not closure(z, S0) >> a & 1]
    same = all(closure(z, Rt) & a for z, a in gens) and all(closure(z, Rt + []) & a for z, a in Rt)
    return {"gens": gens, "m_star": len(held), "pairs": pairs, "violated_keys": viol, "same": bool(same)}


def main():
    pin, pout, res = sys.argv[1], sys.argv[2], sys.argv[3:]
    pm = json.load(open(pin, encoding="utf-8"))
    runs = {}
    for f in res:
        for x in open(f, encoding="utf-8"):
            try:
                r = json.loads(x)
            except ValueError:
                continue
            if r.get("certified") and r.get("oracle", "gold") == "gold" and isinstance(r.get("certificate"), dict):
                runs.setdefault((r["truth"], r["dataset"]), []).append(r["certificate"]["yes"])
    out = {}
    if os.path.exists(pout):
        out = json.load(open(pout, encoding="utf-8"))
    for key in sorted(pm, key=lambda k: (k.split("/")[0] != "full", k)):
        if key in out:
            continue
        T, ds = key.split("/")
        os.environ["CONFIRM_TRUTH"] = T
        b = AC.load(ds)
        A = analyse(b)
        p = pm[key]
        rec = dict(p, reach_price=p["price"], reach_cover=p["cover"], reach_m_star=p["m_star"], m_star=A["m_star"],
                   m_r=A["m_star"], m_r_pairs=A["pairs"], violated_keys=A["violated_keys"], same_as_reach=A["same"])
        if not A["same"]:
            n = len(b["R"])
            idx = {x: i for i, x in enumerate(b["names"])}
            b2 = dict(b, truth=[(tuple(i for i in range(n) if z >> i & 1), tuple(i for i in range(n) if a >> i & 1)) for z, a in A["gens"]])
            ys = [[(sum(1 << idx[c] for c in l), 1 << idx[r]) for l, r in y] for y in runs.get((T, ds), [])]
            B = CB.bounds(b2, ys)
            rec.update(cover=B["cover_ub"], cover_lb=B["cover_lb"], cover_exact=B["cover_ub"] == B["cover_lb"])
        rec["price"] = rec["cover"] + rec["m_star"]
        out[key] = rec
        print(f"{key:44s} recorded {p['price']:4d} = {p['cover']:3d}+{p['m_star']:3d} | gold {rec['price']:4d} = {rec['cover']:3d}+{rec['m_star']:3d} (cover lb {rec['cover_lb']}) same {A['same']} violated keys {A['violated_keys']}", flush=True)
        with open(pout, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main()
