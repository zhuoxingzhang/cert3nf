"""A smallest cover where the branch and bound of cover_bounds.py leaves a gap: the lazy cuts of exact_cover, with a MILP
(HiGHS through scipy) as the hitting-set solver and the per-attribute cuts of the lower bound from the start.  A set C
closed under S0 + F but not under Sigma* needs an FD of F with its left-hand side in C and its right-hand side outside, so
the optimum over any set of such cuts is a lower bound, and an optimum that implies every FD of Sigma* is a smallest cover.

Usage (in confirm):  CONFIRM_ORACLE=gold python cover_milp.py full/fresh_seats OUT.json [SECONDS]
                    python cover_milp.py merge PRICE.json DIR   (DIR/full_fresh_seats.json into PRICE.json)"""
import json, os, sys, time

if sys.argv[1] == "merge":
    path, d = sys.argv[2], sys.argv[3]
    P = json.load(open(path, encoding="utf-8"))
    for key, rec in P.items():
        r = json.load(open(os.path.join(d, key.replace("/", "_") + ".json"), encoding="utf-8"))
        if not r["exact"]:
            sys.exit(f"{key}: not exact")
        if r["cover"] != rec["cover"]:
            print(key, "cover", rec["cover"], "->", r["cover"])
        rec.update(cover=r["cover"], cover_lb=r["cover"], cover_exact=True, price=r["cover"] + rec["m_star"])
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(P, fh, indent=1)
    sys.exit(0)

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix

key, out = sys.argv[1], sys.argv[2]
limit = float(sys.argv[3]) if len(sys.argv) > 3 else 3000
T, ds = key.split("/")
os.environ["CONFIRM_TRUTH"] = T
import auto_common as AC
import price_gold as PG
from price import closure, min_keys

b = AC.load(ds)
A = PG.analyse(b)
n = len(b["R"])
full = (1 << n) - 1
mask = lambda s: sum(1 << i for i in s)
S0 = [(mask(l), mask(r)) for l, r in b["sigma0"]]
F = S0 + (A["gens"] if not A["same"] else [(mask(l), mask(r)) for l, r in b["truth"]])
atoms = {a: [k & ~(1 << a) for k in min_keys(F + [(1 << a, full)], full) if k != 1 << a] for a in range(n)}
need = [(x, 1 << a) for a in range(n) for x in atoms[a]]
pool = [(x, a) for x, a in need if not closure(x, S0) & a]
print(key, "same as reach", A["same"], "left-reduced FDs", len(pool), flush=True)


def cut(c):
    return frozenset(i for i, (l, r) in enumerate(pool) if l & ~c == 0 and not r & c)


rows = set()
for a in range(n):
    rest = S0 + [(x, 1 << c) for c in range(n) if c != a for x in atoms[c]]
    for x in atoms[a]:
        c = closure(x, rest)
        if not c >> a & 1:
            rows.add(cut(c))
rows |= {cut(closure(x, S0)) for x, a in need if not closure(x, S0) & a}


def solve(rows, seconds):
    rl = [sorted(r) for r in rows]
    ij = [(i, j) for i, r in enumerate(rl) for j in r]
    M = csr_matrix((np.ones(len(ij)), ([p[0] for p in ij], [p[1] for p in ij])), shape=(len(rl), len(pool)))
    res = milp(np.ones(len(pool)), constraints=LinearConstraint(M, lb=1), integrality=np.ones(len(pool)), bounds=Bounds(0, 1),
               options={"time_limit": seconds, "mip_rel_gap": 0})
    return res


t0 = time.time()
lb, it = 0, 0
result = {"key": key, "exact": False}
while time.time() - t0 < limit:
    it += 1
    res = solve(rows, max(limit - (time.time() - t0), 10))
    bound = getattr(res, "mip_dual_bound", None)
    if res.status != 0:
        if bound is not None:
            lb = max(lb, int(np.ceil(bound - 1e-6)))
        print(f"  solver stopped: status {res.status}, bound {bound}", flush=True)
        break
    s = [i for i, v in enumerate(res.x) if v > .5]
    lb = max(lb, len(s))
    H = S0 + [pool[i] for i in s]
    bad = [(x, a) for x, a in need if not closure(x, H) & a]
    print(f"  iteration {it}: cuts {len(rows)}, optimum {len(s)}, FDs still not implied {len(bad)}, {time.time() - t0:.0f} s", flush=True)
    if not bad:
        result.update(exact=True, cover=len(s), F=[list(pool[i]) for i in s])
        break
    rows |= {cut(closure(x, H)) for x, a in bad}
result.update(lb=lb, seconds=round(time.time() - t0), iterations=it)
print(key, {k: v for k, v in result.items() if k != "F"}, flush=True)
with open(out, "w", encoding="utf-8") as fh:
    json.dump(result, fh)
