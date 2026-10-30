"""
Bounds on the yes side of the price (design note item 45): the size c of a smallest set F of FDs with
closure(Sigma0 + F) = closure(Sigma*), which with m_r gives the length of a shortest certificate (Thm. price (d)).

upper bound: the smallest of the covers of price.py (its elimination orders and 200 random ones), of the covers that
             random elimination orders leave of all left-reduced FDs of Sigma* (the atoms; a smallest cover may need
             FDs that the documentation does not list, such as a cycle through equivalent attributes), and of the yes
             answers of every certified run in the given result files (each generates Sigma* with Sigma0);
lower bound: the sum over the attributes A of the smallest number of FDs with right-hand side A that, together with
             Sigma0 and every left-reduced FD of Sigma* with another right-hand side, imply every FD of Sigma* with
             right-hand side A (a set cover per attribute, exact by branch and bound; a cut search gives a lower bound
             of the greedy cover divided by its logarithmic factor and is flagged).
Every set F restricted to right-hand side A is such a set, since F can be left-reduced, so c lies between the bounds.

Usage (in confirm):  CONFIRM_TRUTH=full [CONFIRM_BATCH=2] python cover_bounds.py --out F --results F1,F2,...
  (the development relations, or with CONFIRM_BATCH=2 the confirmatory ones)
"""
import argparse, json, math, os, random, time
import auto_common as AC
from price import closure, bits, min_keys, cover_count, set_cover, ORDERS


ATOM_ORDERS = 300
EXACT_SECONDS = float(os.environ.get("COVER_EXACT_SECONDS", "600"))
NODE_LIMIT = int(os.environ.get("COVER_NODE_LIMIT", "300000"))


def eliminate(pool, S0, rng):
    """the FDs outside closure(S0) of the non-redundant cover that eliminating pool in a random order leaves"""
    G = [f for f in pool if f not in S0]
    rng.shuffle(G)
    keep = list(S0) + G
    i = len(S0)
    while i < len(keep):
        l, b = keep[i]
        if closure(l, keep[:i] + keep[i + 1:]) & b:
            del keep[i]
        else:
            i += 1
    return [(l, b) for l, b in keep[len(S0):] if not closure(l, S0) & b]


def hitting_set(rows, inc, limit):
    """a smallest set of indices that meets every row (frozensets), by branch and bound from the incumbent inc, with
    a packing of disjoint rows as the bound.  Returns (solution, exact)."""
    rows = sorted(set(rows), key=len)
    keep = []
    for r in rows:                                    # a row that contains another is met whenever the other is
        if not any(k <= r for k in keep):
            keep.append(r)
    best = [list(inc)]
    nodes = [0]

    def rec(chosen, excl, unmet):
        nodes[0] += 1
        if nodes[0] > limit:
            raise TimeoutError
        if not unmet:
            best[0] = list(chosen)
            return
        free = [u - excl for u in unmet]
        if not all(free):
            return
        used, pack = set(), 0
        for u in sorted(free, key=len):
            if not u & used:
                used |= u
                pack += 1
        if len(chosen) + pack >= len(best[0]):
            return
        r = min(free, key=len)
        ex = set(excl)
        for v in sorted(r, key=lambda v: -sum(1 for u in free if v in u)):
            rec(chosen + [v], frozenset(ex), [u for u in unmet if v not in u])
            ex.add(v)
    try:
        rec([], frozenset(), keep)
        return best[0], True
    except TimeoutError:
        return best[0], False


def exact_cover(pool, S0, need, inc, seconds, limit=300_000):
    """the size of a smallest F within pool with closure(S0 + F) implying every FD of need, by lazy cuts: a set C that is
    closed under S0 + F but not under Sigma* needs an FD of F with its left-hand side in C and its right-hand side
    outside.  Returns (size, exact, lower bound)."""
    t0 = time.time()
    idx = {f: i for i, f in enumerate(pool)}

    def cut(c):
        return frozenset(i for i, (l, b) in enumerate(pool) if l & ~c == 0 and not b & c)
    rows = {cut(closure(x, S0)) for x, a in need if not closure(x, S0) & a}
    sol = [idx[f] for f in inc]
    lb = 0
    while time.time() - t0 < seconds:
        s, ex = hitting_set(rows, sol if len(sol) else [], limit)
        if not ex:
            return len(sol), False, lb
        lb = max(lb, len(s))
        F = S0 + [pool[i] for i in s]
        bad = [(x, a) for x, a in need if not closure(x, F) & a]
        if not bad:
            return len(s), True, len(s)
        rows |= {cut(closure(x, F)) for x, a in bad}      # the incumbent, a cover, meets every new row
    return len(sol), False, lb


def bounds(b, runs):
    n = len(b["R"])
    full = (1 << n) - 1
    mask = lambda s: sum(1 << i for i in s)
    S0 = [(mask(l), mask(r)) for l, r in b["sigma0"]]
    F = S0 + [(mask(l), mask(r)) for l, r in b["truth"]]
    rng = random.Random(0)
    keys = {}
    orders = list(ORDERS) + [lambda f, k=keys: k.setdefault(f, rng.random()) for _ in range(200)]
    ub = []
    for o in orders:
        keys.clear()
        ub.append(cover_count(F, S0, o))
    ub_orders = min(ub)
    ub_runs = min((len([1 for l, r in y if not closure(l, S0) & r]) for y in runs), default=None)
    # the left-reduced FDs of Sigma*: for each A, the minimal X with A in closure(X), X without A
    atoms = {a: [k & ~(1 << a) for k in min_keys(F + [(1 << a, full)], full) if k != 1 << a] for a in range(n)}
    pool = S0 + [(x, 1 << a) for a in range(n) for x in atoms[a]]
    inc = min((eliminate(pool, S0, rng) for _ in range(ATOM_ORDERS)), key=len)
    ub_atoms = len(inc)
    lb, exact = 0, True
    for a in range(n):
        rest = S0 + [(x, 1 << c) for c in range(n) if c != a for x in atoms[c]]
        need = [x for x in atoms[a] if not closure(x, rest) >> a & 1]
        if not need:
            continue
        cl = {x: closure(x, rest) for x in need}
        cov = [frozenset(i for i, y in enumerate(atoms[a]) if y & ~cl[x] == 0) for x in need]
        k, ex = set_cover(cov, len(atoms[a]))
        if not ex:                                    # greedy k is at most H(d) times the optimum
            d = max(sum(1 for c in cov if i in c) for i in range(len(atoms[a])))
            k = math.ceil(k / sum(1 / j for j in range(1, d + 1)))
        lb += k
        exact &= ex
    best = min(x for x in (ub_orders, ub_atoms, ub_runs) if x is not None)
    c_exact = None
    if lb < best and EXACT_SECONDS > 0:              # close the gap by lazy cuts within the atoms
        need = [(x, 1 << a) for a in range(n) for x in atoms[a]]
        apool = [f for f in pool if f not in S0 and not closure(f[0], S0) & f[1]]
        k, ex, klb = exact_cover(apool, S0, need, inc, EXACT_SECONDS, NODE_LIMIT)
        best = min(best, k)
        lb = max(lb, klb)
        c_exact = ex
    return {"cover_price_py": min(ub[:len(ORDERS)]), "cover_orders": ub_orders, "cover_atoms": ub_atoms,
            "cover_runs": ub_runs, "cover_ub": best, "cover_lb": lb, "lb_exact": exact, "cuts_exact": c_exact,
            "atoms": sum(len(v) for v in atoms.values()), "tight": lb == best}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--results", default="")
    a = ap.parse_args()
    runs = {}
    for f in filter(None, a.results.split(",")):
        for x in open(f, encoding="utf-8"):
            r = json.loads(x)
            if r.get("certified") and r.get("oracle", "gold") == "gold" and "certificate" in r:
                runs.setdefault((r["truth"], r["dataset"]), []).append(r["certificate"]["yes"])
    out = {}
    t = AC.truth_mode()
    dss = AC.DATASETS + AC.FRESH if os.environ.get("CONFIRM_BATCH") != "2" else AC.FRESH
    for ds in os.environ["COVER_ONLY"].split(",") if os.environ.get("COVER_ONLY") else dss:
        t0 = time.time()
        b = AC.load(ds)
        idx = {x: i for i, x in enumerate(b["names"])}
        ys = [[(sum(1 << idx[c] for c in l), 1 << idx[r]) for l, r in y] for y in runs.get((t, ds), [])]
        out[f"{t}/{ds}"] = r = {**bounds(b, ys), "secs": round(time.time() - t0, 1)}
        print(t, ds, r, flush=True)
    json.dump(out, open(a.out, "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
