"""How often is a true FD not minimal on the data (design note item 32, the correction of the certification loop)?

For each relation and truth, the single-right-hand-side FDs of the documented truth Sigma* (gold) that Sigma0 and the
true candidates do not imply are split into: violated by the data (no minimal FD of the data lies below them; outside
the certificate by assumption) and holding on the data with every minimal FD below them false (a "witness failure":
the loop that asks only maximal sets holding an open candidate would miss them).
Usage (in confirm):  python witness.py"""
import os
import auto_common as AC
from price import closure


def main():
    for truth in ("full", "sure"):
        os.environ["CONFIRM_TRUTH"] = truth
        print(f"== truth {truth}")
        print(f"{'relation':28s} {'gold':>5s} {'unreach':>7s} {'violated':>8s} {'witness':>7s}  examples of witness failures")
        for ds in AC.DATASETS + AC.FRESH:
            b = AC.load(ds)
            n = len(b["R"])
            mask = lambda s: sum(1 << i for i in s)
            S0 = [(mask(l), mask(r)) for l, r in b["sigma0"]]
            reach = S0 + [(mask(l), mask(r)) for l, r in b["truth"]]
            mined = [(mask(l), mask(r)) for l, r in b["P"]] + [(mask(l), mask(r)) for l, r in b["implied0"]]
            gold = {(mask(l), mask(r)) for l, r in b["gold"]}
            unreach = [(l, r) for l, r in gold if not closure(l, reach) & r]
            wit = [(l, r) for l, r in unreach if any(r2 == r and l2 & ~l == 0 for l2, r2 in mined)]
            ex = "; ".join(f"{','.join(b['names'][i] for i in range(n) if l >> i & 1)} -> {b['names'][r.bit_length() - 1]}"
                           for l, r in wit[:2])
            print(f"{ds:28s} {len(gold):5d} {len(unreach):7d} {len(unreach) - len(wit):8d} {len(wit):7d}  {ex}", flush=True)


if __name__ == "__main__":
    main()
