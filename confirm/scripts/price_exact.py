"""Design note item 67: the price of every evaluated relation of a CONFIRM_BATCH from the truth and the data alone, no run of
any method: the exact smallest cover of cover_milp.py plus the held sets m* of price_gold.analyse.  On batch 2 it must give
the recorded v5_fresh2/price_gold.json.
Usage (in confirm/):  CONFIRM_ORACLE=gold CONFIRM_BATCH=3 python scripts/price_exact.py OUT.json MILPDIR [WORKERS]"""
import json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.getcwd())
out, milp = sys.argv[1], sys.argv[2]
workers = int(sys.argv[3]) if len(sys.argv) > 3 else 6
os.makedirs(milp, exist_ok=True)
import auto_common as AC
import price_gold as PG
from price import closure, min_keys

keys = [f"{T}/{ds}" for T in ("full", "sure") for ds in AC.FRESH]


def solve(key):
    f = os.path.join(milp, key.replace("/", "_") + ".json")
    if not os.path.exists(f):
        with open(f + ".log", "w", encoding="utf-8") as log:
            done = subprocess.run(["nice", "-n", "19", sys.executable, "cover_milp.py", key, f, "3000"], stdout=log, stderr=subprocess.STDOUT)
        if done.returncode:
            if "`c` must be a one-dimensional" not in open(f + ".log", encoding="utf-8").read():   # the solver refuses a problem without variables
                raise RuntimeError(f"{key}: see {f}.log")
            return key, {"key": key, "exact": True, "cover": 0, "empty": True}
    return key, json.load(open(f, encoding="utf-8"))


with ThreadPoolExecutor(workers) as ex:
    covers = dict(ex.map(solve, keys))
P = {}
for key in keys:
    T, ds = key.split("/")
    os.environ["CONFIRM_TRUTH"] = T
    b = AC.load(ds)
    A = PG.analyse(b)
    c = covers[key]
    if not c["exact"]:
        sys.exit(f"{key}: cover not exact, {c}")
    if c.get("empty"):      # no FD of Sigma* outside the closure of Sigma0: the smallest cover is empty; recomputed as in cover_milp.py
        n, full = len(b["R"]), (1 << len(b["R"])) - 1
        mask = lambda s: sum(1 << i for i in s)
        S0 = [(mask(l), mask(r)) for l, r in b["sigma0"]]
        F = S0 + (A["gens"] if not A["same"] else [(mask(l), mask(r)) for l, r in b["truth"]])
        for x_ in range(n):
            for k in min_keys(F + [(1 << x_, full)], full):
                if k != 1 << x_ and not closure(k & ~(1 << x_), S0) >> x_ & 1:
                    sys.exit(f"{key}: the solver failed on a problem with variables")
    P[key] = {"attributes": len(b["R"]), "candidates": len(b["P"]), "cover": c["cover"], "cover_lb": c["cover"], "cover_exact": True, "m_star": A["m_star"],
              "m_r": A["m_star"], "m_r_pairs": A["pairs"], "price": c["cover"] + A["m_star"], "violated_keys": A["violated_keys"], "same_as_reach": A["same"]}
    print(key, {k: P[key][k] for k in ("attributes", "candidates", "cover", "m_star", "price", "violated_keys", "same_as_reach")}, flush=True)
with open(out, "w", encoding="utf-8") as fh:
    json.dump(P, fh, indent=1)
print("written", out, len(P))
