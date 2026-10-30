"""
Checks Lemma 13 and Theorem 14 of the formalization note (when one false positive makes the synthesized
design lossy) on the random instances of sensitivity_bruteforce.py, and conjecture C3 (the row-closure
fixpoint over distinguished symbols decides the chase).

Usage:  python o3_lossiness_check.py
"""
import os, sys, random, itertools, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sensitivity_bruteforce as S  # noqa: E402

B = S.B


def cl(Z, F):
    return frozenset(B.closure(frozenset(Z), F))


def chase_W(R, schemas, sigma):
    # tableau chase; returns, per row, the attributes on which the row holds the distinguished symbol
    R = sorted(R)
    rows = [{a: (0, a) if a in Sc else (1, i, a) for a in R} for i, Sc in enumerate(schemas)]
    ch = True
    while ch:
        ch = False
        for lhs, rhs in sigma:
            (a,) = tuple(rhs)
            g = collections.defaultdict(list)
            for r in rows:
                g[tuple(r[x] for x in sorted(lhs))].append(r)
            for grp in g.values():
                vals = {r[a] for r in grp}
                if len(vals) > 1:
                    t = min(vals)
                    for r in rows:
                        if r[a] in vals and r[a] != t:
                            r[a] = t
                            ch = True
    return [frozenset(a for a in R if r[a] == (0, a)) for r in rows]


def row_closure(D, F_a):
    # conjecture C3: least fixpoint of "rows i, j both distinguished on Y, Y->b true, j distinguished on b => i gets b"
    dist = [set(s) for s in D]
    ch = True
    while ch:
        ch = False
        for (Y, Bs) in F_a:
            (b,) = tuple(Bs)
            for i in range(len(D)):
                if b in dist[i] or not Y <= dist[i]:
                    continue
                if any(Y <= dist[j] and b in dist[j] for j in range(len(D)) if j != i):
                    dist[i].add(b)
                    ch = True
    return [frozenset(d) for d in dist]


def theorem14():
    H, bad = collections.Counter(), collections.Counter()
    for seed, ns, per in ((1, (4, 5, 6), 300), (7, (4, 5, 6), 300), (3, (7,), 150)):
        rnd = random.Random(seed)
        for n in ns:
            R = frozenset(range(n))
            for _ in range(per):
                st_a = S.atomic_closure(list(R), S.random_sigma(list(R), rnd))
                if not st_a:
                    continue
                fps = [S.fd(X, a) for a in R for k in (1, 2) for X in itertools.combinations([b for b in R if b != a], k)
                       if not S.implies(st_a, S.fd(X, a))]
                rnd.shuffle(fps)
                G = S.canonical_cover(st_a)
                for f in fps[:12]:
                    X, A = f[0], next(iter(f[1]))
                    sh_a = S.atomic_closure(list(R), st_a + [f])
                    new_key = any(cl(k, st_a) != R for k in B.minimal_keys(R, sh_a))
                    for m in S.MODES:
                        D = [frozenset(s) for s in S.design(list(R), sh_a, m)]
                        W = chase_W(R, D, G)
                        lossless = any(w == R for w in W)
                        star = [cl(s, st_a) for s in D]
                        hat = [cl(s, sh_a) for s in D]
                        E = [g for s in D for g in S.proj(st_a, s)]
                        e_superkey = any(cl(s, E) == R for s in D)
                        superkey = any(c == R for c in star)
                        dp = all(S.implies(E, g) for g in st_a)
                        for w, c in zip(W, star):                      # (a) unaffected rows
                            if not X <= c:
                                bad["(a) X-free row misses S*"] += w != c
                        for h, c in zip(hat, star):                    # Lemma 13 consequence used in (c)
                            if h == R:
                                bad["(c) hat-superkey: S*=R iff a in S*"] += (c == R) != (A in c)
                        keyloss = not superkey                         # (c)
                        bad["(c) key-loss criterion"] += keyloss != all(A not in c for h, c in zip(hat, star) if h == R)
                        bad["(c) key loss without new key"] += keyloss and not new_key
                        bad["(c) key loss but lossless"] += keyloss and lossless
                        bad["(b) E*-superkey but lossy"] += e_superkey and not lossless
                        bad["(b) DP, superkey, lossy"] += dp and superkey and not lossless
                        for g in st_a:                                 # (d) short-circuited FDs
                            if not S.implies(E, g):
                                bad["(d) lost FD with X not in Y*"] += not X <= cl(g[0], st_a)
                        tag = (m, "n<=6" if n <= 6 else "n=7")
                        H[tag + ("total",)] += 1
                        H[tag + ("lossy",)] += not lossless
                        H[tag + ("key loss",)] += keyloss
                        H[tag + ("path loss",)] += (not lossless) and superkey
                        H[tag + ("gap: superkey, no E*-superkey",)] += superkey and not e_superkey
                        H[tag + ("gap and lossless",)] += superkey and not e_superkey and lossless
    for k, v in sorted(H.items()):
        print(k, v)
    print("violations of Lemma 13 / Theorem 14:", dict(bad))


def conjecture_c3():
    # per row: does the fixpoint equal the chase row by row (refuted)?  weak: do both find an all-distinguished row?
    c3 = collections.Counter()

    def compare(tag, R, D, F_a):
        rc, ch = row_closure(D, F_a), chase_W(R, D, F_a)
        c3[tag] += 1
        c3[tag + ": per-row mismatch"] += rc != ch
        c3[tag + ": weak mismatch"] += any(w == R for w in rc) != any(w == R for w in ch)

    for seed, trials, ns, ks, twice in ((5, 4000, [4, 5, 6], (2, 4), False), (11, 30000, [5, 6, 7], (3, 6), True)):
        rnd = random.Random(seed)          # arbitrary decompositions and FD sets
        for _ in range(trials):
            n = rnd.choice(ns)
            R = frozenset(range(n))
            F = S.random_sigma(list(R), rnd) + (S.random_sigma(list(R), rnd) if twice else [])
            F_a = S.atomic_closure(list(R), F)
            D = [frozenset(rnd.sample(sorted(R), rnd.randint(2, n - 1))) for _ in range(rnd.randint(*ks))]
            miss = R - frozenset().union(*D)
            if miss:
                D.append(frozenset(miss | {rnd.choice(sorted(R))}))
            compare("arbitrary", R, D, F_a)
    rnd = random.Random(1)
    for n in (4, 5, 6):                    # the single-FP designs (seed 1)
        R = frozenset(range(n))
        for _ in range(300):
            st_a = S.atomic_closure(list(R), S.random_sigma(list(R), rnd))
            if not st_a:
                continue
            fps = [S.fd(X, a) for a in R for k in (1, 2) for X in itertools.combinations([b for b in R if b != a], k)
                   if not S.implies(st_a, S.fd(X, a))]
            rnd.shuffle(fps)
            for f in fps[:12]:
                sh_a = S.atomic_closure(list(R), st_a + [f])
                for m in S.MODES:
                    compare("FP designs", R, [frozenset(x) for x in S.design(list(R), sh_a, m)], st_a)
    print("conjecture C3:", dict(c3))


if __name__ == "__main__":
    theorem14()
    conjecture_c3()
