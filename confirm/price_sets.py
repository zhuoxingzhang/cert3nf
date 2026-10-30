"""The price of Thm. price as the paper states it (design note items 35 and 41): |G \\ Sigma0+| + m_r, where m_r counts
the held sets, i.e. the distinct maximal sets M of Sigma0 + Sigma* that hold on r for some attribute A, once each.
price.py counts the held pairs (M, A) instead, which is at least m_r; its cover and pair counts are recomputed here
and checked against its price.json.

Writes <dir>/price_sets.json with the fields of <dir>/price.json, "price" replaced by cover + m_star, and the pair
count kept as "m_r_pairs" and "price_pairs".  The report scripts read it with PRICE_FILE=price_sets.json.
Usage (in confirm):  python price_sets.py v5_dev v5_fresh2"""
import json, os, sys

import auto_common as AC
from price import ORDERS, closure, cover_count, maxsets


def price_sets(b):
    n = len(b["R"])
    full = (1 << n) - 1
    mask = lambda s: sum(1 << i for i in s)
    S0 = [(mask(l), mask(r)) for l, r in b["sigma0"]]
    F = S0 + [(mask(l), mask(r)) for l, r in b["truth"]]
    false = [(mask(l), next(iter(r))) for l, r in b["P"] if not closure(mask(l), F) & mask(r)]
    cover = min(cover_count(F, S0, o) for o in ORDERS)
    pairs, held = 0, set()
    for a in range(n):
        ms = maxsets(F, 1 << a, full)
        fa = [l for l, r in false if r == a]
        hit = [M for M in ms if any(l & ~M == 0 for l in fa)]
        pairs += len(hit)
        held.update(hit)
    return cover, pairs, len(held)


def main():
    for d in sys.argv[1:]:
        old = json.load(open(os.path.join(d, "price.json"), encoding="utf-8"))
        out = {}
        for key in sorted(old, key=lambda k: (k.split("/")[0] != "full", k)):
            T, ds = key.split("/")
            os.environ["CONFIRM_TRUTH"] = T
            cover, pairs, mstar = price_sets(AC.load(ds))
            o = old[key]
            assert (cover, pairs) == (o["cover"], o["m_r"]), (key, cover, pairs, o["cover"], o["m_r"])
            out[key] = dict(o, m_r_pairs=pairs, price_pairs=o["price"], m_star=mstar, m_r=mstar, price=cover + mstar)
            print(f"{d:10s} {key:36s} cover {cover:3d} pairs {pairs:3d} sets {mstar:3d} price {o['price']:3d} -> {cover + mstar:3d}",
                  flush=True)
        with open(os.path.join(d, "price_sets.json"), "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main()
