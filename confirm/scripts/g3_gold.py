"""Design note item 43: the g3 share of every documented FD that the data violate, per confirmatory relation and truth,
so that the theta at which the certificate covers it can be read off (an FD is covered once g3 <= theta).
Usage (in confirm):  CODES_DIR=<codes_rep or codes_raw> CONFIRM_BATCH=2 python scripts/g3_gold.py [datasets]"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import auto_common as AC
from price import closure
from v5tau import Violations


def main():
    names = sys.argv[1:] or AC.FRESH
    for truth in ("full", "sure"):
        os.environ["CONFIRM_TRUTH"] = truth
        print(f"== truth {truth}")
        for ds in names:
            b = AC.load(ds)
            n = len(b["R"])
            mask = lambda s: sum(1 << i for i in s)
            mined = [(mask(l), mask(r)) for l, r in b["P"]] + [(mask(l), mask(r)) for l, r in b["implied0"]]
            viol = None
            for l, r in sorted({(mask(l), mask(r)) for l, r in b["gold"]}):
                if closure(l, mined) & r:
                    continue  # holds on the data
                viol = viol or Violations(ds)
                lhs = ",".join(b["names"][i] for i in range(n) if l >> i & 1)
                print(f"  {ds:20s} g3 {viol.g3(l, r):.5f}  {lhs} -> {b['names'][r.bit_length() - 1]}", flush=True)


if __name__ == "__main__":
    main()
