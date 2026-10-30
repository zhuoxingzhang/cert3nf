"""
Exact discovery of all minimal non-trivial FDs X -> A of a relation without nulls, in the style of HyFD
(Papenbrock and Naumann, SIGMOD 2016).  Pairs of tuples give agree sets (non-FDs: X within an agree set that misses
A means X does not determine A); the candidate left-hand sides of A are the minimal transversals of the complements
of these agree sets, induced incrementally as in HyFD's FD tree; every candidate is validated on the whole relation,
and a violated candidate contributes the agree sets of its violating pairs.  The loop ends when every candidate
holds.  The result is the complete set of minimal FDs, which is unique for a relation without nulls, so it equals
the output of HyFD.

No HyFD or Metanome binary was available (prior work mined its sets elsewhere), hence this implementation.
--test compares it with a brute-force enumeration on random small relations.

API:  mine(columns) -> list of (lhs bitmask, rhs index);  write_metanome(path, table, names, fds)
"""
import sys, time
import numpy as np


def encode(columns):
    """Integer-code every column; returns the n x m int32 matrix and the column cardinalities."""
    codes, card = [], []
    for col in columns:
        _, inv = np.unique(np.asarray(col), return_inverse=True)
        codes.append(inv.astype(np.int32).ravel())
        card.append(int(inv.max()) + 1 if len(inv) else 1)
    return np.stack(codes, axis=1), card


def bits(x):
    out, i = [], 0
    while x:
        if x & 1:
            out.append(i)
        x >>= 1
        i += 1
    return out


class Miner:
    def __init__(self, M, card, verbose=False):
        self.M, self.card = M, card
        self.n, self.m = M.shape
        self.weights = (np.int64(1) << np.arange(self.m, dtype=np.int64))
        self.full = (1 << self.m) - 1
        self.L = [np.zeros(1, dtype=np.int64) for _ in range(self.m)]   # candidate lhs per rhs (antichain)
        self.valid = [set() for _ in range(self.m)]                       # validated lhs per rhs
        self.seen = set()                                                 # agree sets already induced
        self.verbose = verbose

    # ---------- agree sets ----------
    def agree(self, I, J):
        return np.unique((self.M[I] == self.M[J]).astype(np.int64) @ self.weights)

    def sample(self, window=3, seed=0):
        # neighbours in the order of every column (ties broken at random): pairs that agree at least there
        rng = np.random.default_rng(seed)
        tie = rng.permutation(self.n)
        found = []
        for c in range(self.m):
            order = np.lexsort((tie, self.M[:, c]))
            for w in range(1, window + 1):
                if w < self.n:
                    found.append(self.agree(order[:-w], order[w:]))
        return np.unique(np.concatenate(found)) if found else np.zeros(0, dtype=np.int64)

    # ---------- induction ----------
    def induce(self, ags):
        ags = [int(a) for a in ags if int(a) not in self.seen and int(a) != self.full]
        self.seen.update(ags)
        ags.sort(key=lambda a: -bin(a).count("1"))
        for a in range(self.m):
            abit = 1 << a
            L = self.L[a]
            for ag in ags:
                if ag & abit:
                    continue
                hit = (L & ~np.int64(ag)) == 0                  # candidates inside the agree set are refuted
                if not hit.any():
                    continue
                old, L = L[hit], L[~hit]
                comp = bits(self.full & ~ag & ~abit)
                new = set()
                for X in old.tolist():
                    for b in comp:
                        Y = X | (1 << b)
                        if L.size and ((L & ~np.int64(Y)) == 0).any():
                            continue                            # a smaller candidate already covers Y
                        new.add(Y)
                if new:
                    new = sorted(new, key=lambda y: bin(y).count("1"))
                    keep = []
                    for Y in new:                               # minimal among the new ones
                        if not any(Z & ~Y == 0 for Z in keep):
                            keep.append(Y)
                    L = np.concatenate([L, np.array(keep, dtype=np.int64)])
            self.L[a] = L
            self.valid[a] &= set(L.tolist())

    # ---------- validation ----------
    def labels(self, cols):
        if not cols:
            return np.zeros(self.n, dtype=np.int64)
        k = self.M[:, cols[0]].astype(np.int64)
        bound = self.card[cols[0]]
        for c in cols[1:]:
            if bound * self.card[c] >= (1 << 62):
                _, k = np.unique(k, return_inverse=True)
                k = k.astype(np.int64).ravel()
                bound = int(k.max()) + 1
            k = k * self.card[c] + self.M[:, c]
            bound *= self.card[c]
        return k

    def validate(self, max_pairs=64):
        bylhs = {}
        for a in range(self.m):
            for X in self.L[a].tolist():
                if X not in self.valid[a]:
                    bylhs.setdefault(X, []).append(a)
        I, J = [], []
        for X, rhs in bylhs.items():
            k = self.labels(bits(X))
            order = np.argsort(k, kind="stable")
            same = k[order][1:] == k[order][:-1]
            for a in rhs:
                col = self.M[order, a]
                bad = np.nonzero(same & (col[1:] != col[:-1]))[0]
                if bad.size:
                    pick = bad[:: max(1, bad.size // max_pairs)][:max_pairs]
                    I.append(order[pick])
                    J.append(order[pick + 1])
                else:
                    self.valid[a].add(X)
        if not I:
            return np.zeros(0, dtype=np.int64), len(bylhs)
        return self.agree(np.concatenate(I), np.concatenate(J)), len(bylhs)

    def run(self):
        t0 = time.time()
        self.induce(self.sample())
        rounds = 0
        while True:
            rounds += 1
            ags, nl = self.validate()
            if self.verbose:
                print(f"  round {rounds}: {nl} lhs checked, {len(ags)} new agree sets, "
                      f"{sum(len(L) for L in self.L)} candidates, {time.time() - t0:.1f}s", flush=True)
            if len(ags) == 0:
                break
            self.induce(ags)
        return sorted(((X, a) for a in range(self.m) for X in self.L[a].tolist()),
                      key=lambda f: (bin(f[0]).count("1"), f[1], f[0]))


def mine(columns, verbose=False):
    M, card = encode(columns)
    return Miner(M, card, verbose).run()


def write_metanome(path, table, names, fds):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# TABLES\n{table}.csv\t1\n# COLUMN\n")
        for i, nm in enumerate(names):
            fh.write(f"1.{nm}\t{i + 1}\n")
        fh.write("# RESULTS\n")
        for X, a in fds:
            fh.write(",".join(str(b + 1) for b in bits(X)) + f"->{a + 1}\n")


def brute(columns):
    import itertools
    rows = list(zip(*columns))
    m = len(columns)
    out = []
    for a in range(m):
        found = []
        for k in range(m):
            for X in itertools.combinations([b for b in range(m) if b != a], k):
                mask = sum(1 << b for b in X)
                if any(Y & ~mask == 0 for Y in found):
                    continue
                g = {}
                if all(g.setdefault(tuple(r[b] for b in X), r[a]) == r[a] for r in rows):
                    found.append(mask)
        out += [(X, a) for X in found]
    return sorted(out, key=lambda f: (bin(f[0]).count("1"), f[1], f[0]))


if __name__ == "__main__":
    if "--test" in sys.argv:
        rng = np.random.default_rng(1)
        bad = 0
        for t in range(400):
            m, n = int(rng.integers(2, 8)), int(rng.integers(1, 40))
            cols = [rng.integers(0, int(rng.integers(1, 6)), size=n).tolist() for _ in range(m)]
            bad += mine(cols) != brute(cols)
        print("random relations, mismatches with brute force:", bad, "of 400")
