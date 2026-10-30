"""The pre-listing of design-note item 33 before any method runs on the second confirmatory batch: witness.py on the
twelve relations of e3/truth/fresh2.json only, then every documented FD that the data violate, by name (outside the
certificate by its premise r |= Sigma*; the only allowed exception of rule K1).
Usage (in confirm):  python scripts/witness_fresh2.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import auto_common as AC
import witness
from price import closure

with open(os.path.join(AC._TRUTH, "fresh2.json"), encoding="utf-8") as fh:
    FRESH2 = list(json.load(fh)["datasets"])
missing = [ds for ds in FRESH2 if ds not in AC.FRESH]
assert not missing, ("no data file", missing)
AC.DATASETS[:] = []
AC.FRESH[:] = FRESH2
witness.main()
for truth in ("full", "sure"):
    os.environ["CONFIRM_TRUTH"] = truth
    print(f"== documented FDs violated by the data, truth {truth}")
    for ds in FRESH2:
        b = AC.load(ds)
        n = len(b["R"])
        mask = lambda s: sum(1 << i for i in s)
        mined = {}
        for l, r in b["P"] + b["implied0"]:
            mined.setdefault(mask(r), []).append(mask(l))
        nm = lambda m: ",".join(b["names"][i] for i in range(n) if m >> i & 1)
        bad = []
        for l, r in b["gold"]:
            z, a = mask(l), mask(r)
            if not any(x & ~z == 0 for x in mined.get(a, [])):
                bad.append(f"{nm(z)} -> {nm(a)}")
        print(f"   {ds:20s} {len(bad)}  {'; '.join(bad)}")
