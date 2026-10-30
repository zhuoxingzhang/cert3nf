"""The price of a certificate per relation and truth (design note item 32, T-e; Thm. price of the paper).

price (b) = |G \\ Sigma0+| + m_r(Sigma*): G a non-redundant, left-reduced, single-right-hand-side cover of Sigma0 + Sigma*
            (the smallest over a few elimination orders), counted without the FDs that Sigma0 implies; m_r the number of
            pairs (M, A), M a maximal set of Sigma0 + Sigma* for A, that hold on the data, i.e. that contain the left-hand
            side of a false candidate (Thm. price (a)).
no bound (c) = sum over A of the smallest number of maximal sets of A whose union covers the left-hand sides of the false
            candidates X -> A (exact set cover by branch and bound; greedy with a flag if the search is cut).
ratio       = questions of a certified run / price, for the rbms and rbms0 runs of items 29 and 30.

Usage (in confirm):  python price.py --results <dir with rbms_{dev,fresh}_{full,sure}.jsonl> --out price.json
The relations are the development relations and the fresh relations whose data file exists in e3/data."""
import argparse, json, os, statistics, sys, time

import auto_common as AC


def closure(x, F):
    while True:
        y = x
        for l, r in F:
            if l & ~y == 0:
                y |= r
        if y == x:
            return x
        x = y


def bits(m):
    while m:
        b = m & -m
        yield b
        m ^= b


def min_keys(F, full):
    """Lucchesi-Osborn: every minimal key of (R, F)"""
    iskey = lambda x: closure(x, F) == full

    def reduce(x):
        for b in list(bits(x)):
            if iskey(x & ~b):
                x &= ~b
        return x
    keys = [reduce(full)]
    i = 0
    while i < len(keys):
        k = keys[i]
        i += 1
        for l, r in F:
            if r & k:
                c = (k & ~r) | l
                if not any(q & ~c == 0 for q in keys):
                    keys.append(reduce(c))
    return keys


def transversals(edges):
    tr = [0]
    for e in edges:
        new = set()
        for t in tr:
            if t & e:
                new.add(t)
            else:
                new.update(t | b for b in bits(e))
        new = sorted(new, key=lambda m: bin(m).count("1"))
        tr = []
        for t in new:
            if not any(s & ~t == 0 for s in tr):
                tr.append(t)
    return tr


def maxsets(F, a, full):
    """max(F, A): the maximal M with A not in closure(M, F)"""
    return [full & ~t for t in transversals(min_keys(F + [(a, full)], full))]


def cover_count(F, S0, order):
    """FDs of a non-redundant, left-reduced, single-right-hand-side cover of F, eliminated in the given order,
    that S0 does not imply"""
    G = list(dict.fromkeys((l, b) for l, r in F for b in bits(r) if not b & l))
    G.sort(key=order)
    out = []
    for i, (l, b) in enumerate(G):
        rest = out + G[i + 1:]
        if not closure(l, rest) & b:
            out.append((l, b))
    red = []
    for l, b in out:
        for a in list(bits(l)):
            if closure(l & ~a, out) & b:
                l &= ~a
        red.append((l, b))
    return sum(1 for l, b in set(red) if not closure(l, S0) & b)


ORDERS = [lambda f: 0, lambda f: bin(f[0]).count("1"), lambda f: -bin(f[0]).count("1"), lambda f: (f[1], f[0])]


def set_cover(cov, nsets, limit=2_000_000):
    """the smallest number of sets covering every element; cov[e] is the frozenset of sets that contain e.
    Returns (size, exact)."""
    elems = list({c for c in cov if c})          # identical coverage counts once
    # an element whose coverage contains another's coverage is covered whenever the other is
    elems = [c for c in elems if not any(d < c for d in elems)]
    if not elems:
        return 0, True
    members = {}
    for i, c in enumerate(elems):
        for s in c:
            members.setdefault(s, set()).add(i)
    # greedy upper bound
    left, chosen = set(range(len(elems))), 0
    while left:
        s = max(members, key=lambda s: len(members[s] & left))
        left -= members[s]
        chosen += 1
    best = [chosen]
    nodes = [0]
    maxcov = max(len(m) for m in members.values())

    def rec(left, k):
        nodes[0] += 1
        if nodes[0] > limit:
            raise TimeoutError
        if not left:
            best[0] = min(best[0], k)
            return
        if k + -(-len(left) // maxcov) >= best[0]:
            return
        e = min(left, key=lambda i: len(elems[i]))
        for s in sorted(elems[e], key=lambda s: -len(members[s] & left)):
            rec(left - members[s], k + 1)
    try:
        rec(frozenset(range(len(elems))), 0)
        return best[0], True
    except TimeoutError:
        return best[0], False


def price_of(b):
    n = len(b["R"])
    full = (1 << n) - 1
    mask = lambda s: sum(1 << i for i in s)
    # the designer answers from the reachable truth, sigma0 and the true candidates (as the runs do), so the price is
    # taken for that FD set; a candidate is false when it does not imply it
    S0 = [(mask(l), mask(r)) for l, r in b["sigma0"]]
    F = S0 + [(mask(l), mask(r)) for l, r in b["truth"]]
    false = [(mask(l), next(iter(r))) for l, r in b["P"] if not closure(mask(l), F) & mask(r)]
    cover = min(cover_count(F, S0, o) for o in ORDERS)
    m_r = lb_no = tot = 0
    exact = True
    sizes = []
    for a in range(n):
        ms = maxsets(F, 1 << a, full)
        tot += len(ms)
        fa = [l for l, r in false if r == a]
        cov = [frozenset(i for i, M in enumerate(ms) if l & ~M == 0) for l in fa]
        assert all(cov), ("a false candidate inside no maximal set", b["name"], a)
        held = {i for c in cov for i in c}
        m_r += len(held)
        sizes += [bin(ms[i]).count("1") for i in held]
        k, ex = set_cover(cov, len(ms))
        lb_no += k
        exact &= ex
    return {"attributes": n, "candidates": len(b["P"]), "true": len(b["P"]) - len(false), "cover": cover, "maxsets": tot,
            "m_r": m_r, "price": cover + m_r, "lb_no": lb_no, "lb_exact": exact,
            "M_size_median": statistics.median(sizes) if sizes else None,
            "question_attrs_median": statistics.median(min(s, n - s) + 1 for s in sizes) if sizes else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=None, help="directory with rbms_{dev,fresh}_{full,sure}.jsonl")
    ap.add_argument("--out", default="price.json")
    ap.add_argument("--datasets", default=None)
    args = ap.parse_args()
    dss = args.datasets.split(",") if args.datasets else AC.DATASETS + AC.FRESH
    out = {}
    for truth in ("full", "sure"):
        os.environ["CONFIRM_TRUTH"] = truth
        runs = []
        if args.results:
            for part in ("dev", "fresh"):
                p = os.path.join(args.results, f"rbms_{part}_{truth}.jsonl")
                if os.path.exists(p):
                    runs += [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()]
        print(f"== truth {truth}")
        print(f"{'relation':28s} {'|R|':>3s} {'cands':>6s} {'true':>5s} {'cover':>5s} {'maxs':>5s} {'m_r':>4s} {'price':>5s} "
              f"{'lb_no':>5s} {'|M|':>4s} {'qattr':>5s}  rbms q (ratio)             rbms0 q (ratio)        secs")
        for ds in dss:
            t0 = time.time()
            b = AC.load(ds)
            pr = price_of(b)
            cells = []
            for v in ("rbms", "rbms0"):
                qs = sorted((r["questions"], r["seed"]) for r in runs if r["dataset"] == ds and r["variant"] == v and r["certified"])
                nr = sum(1 for r in runs if r["dataset"] == ds and r["variant"] == v)
                rat = [q / pr["price"] for q, _ in qs]
                pr[f"{v}_questions"] = [q for q, _ in qs]
                pr[f"{v}_runs"] = nr
                pr[f"{v}_ratio_median"] = statistics.median(rat) if rat else None
                cells.append(f"{len(qs)}/{nr} " + (",".join(str(q) for q, _ in qs) + f" ({statistics.median(rat):.2f})" if rat else "-"))
            pr["secs"] = round(time.time() - t0, 1)
            out[f"{truth}/{ds}"] = pr
            print(f"{ds:28s} {pr['attributes']:3d} {pr['candidates']:6d} {pr['true']:5d} {pr['cover']:5d} {pr['maxsets']:5d} "
                  f"{pr['m_r']:4d} {pr['price']:5d} {pr['lb_no']:5d}{'' if pr['lb_exact'] else '~'} "
                  f"{pr['M_size_median'] or 0:4.0f} {pr['question_attrs_median'] or 0:5.0f}  {cells[0]:26s} {cells[1]:22s} {pr['secs']:5.1f}",
                  flush=True)
        for v in ("rbms", "rbms0"):
            rat = [r[f"{v}_ratio_median"] for k, r in out.items() if k.startswith(truth) and r[f"{v}_ratio_median"] is not None]
            if rat:
                print(f"  {v}: certified relations {len(rat)}, ratio median {statistics.median(rat):.2f}, "
                      f"range {min(rat):.2f}-{max(rat):.2f}")
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main()
