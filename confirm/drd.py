"""
Prototype of design-targeted confirmation under uncertain FDs (formalization note, section 11).

Setting: confirmed FDs sigma0, candidates P with estimated probabilities pi, an oracle that answers
"does p hold in the domain?".  A hypothesis h is a subset of P closed under implication together with sigma0.
A decision is a design D (set of schemata).  For tolerance eps, D is good for h if D is (sigma0 + h)-valid
(lossless, dependency-preserving, 3NF) and |D| <= |alg(sigma0 + h)| + eps.  A policy asks questions until some
decision is good for at least a fraction 1 - delta of the sampled hypotheses that are consistent with the answers
(delta = 0: for every sample, the worst-case rule).

Policies (same stopping rule, different question order):
  drd     EC2 over the classes of a greedy cover of the hypotheses by decision regions (ours)
  voi     myopic value of information: the gain in the best decision's posterior mass
  marg    largest posterior marginal P(p in h | answers): the greedy cover of Theorem 19
  struct  EC2 over the classes "same synthesized structure" (identify alg(Sigma*), the original O5 plan)
  unc     uncertainty sampling on the posterior marginals
  pi      ask in decreasing estimated probability
  rand    random order
"""
import bisect, collections, itertools, math, os, random, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "e2"))
import sensitivity_bruteforce as S  # noqa: E402
import e2_tpch as E2                # noqa: E402  (fast atomic closure, Lucchesi-Osborn)

B = S.B


# ---- attribute sets as bitmasks ----
# The FD machinery below computes the same values as sensitivity_bruteforce, e2_tpch and baselines (closures, keys,
# atomic closures, synthesis), with bitmask closures in place of set closures.  Where a result of the originals depends
# on the iteration order of Python sets (the order of the minimal keys, hence which key synthesis adds), the same set
# operations are kept, so the results are identical, not only equivalent.

def _merge(F):
    """FDs given as (lhs mask, rhs mask), merged by left-hand side: the same closures in fewer steps"""
    d = {}
    for l, r in F:
        d[l] = d.get(l, 0) | r
    return [(l, r) for l, r in d.items() if r & ~l]


def _closure(m, F, full):
    """closure of the attribute mask m under F, a list of (lhs mask, rhs mask)"""
    c = m
    changed = True
    while changed and c != full:
        changed = False
        for l, r in F:
            if r & ~c and not l & ~c:
                c |= r
                changed = True
    return c


def _closure_np(m, la, ra, full):
    """_closure for a long F given as numpy arrays of lhs and rhs masks: every pass applies all applicable FDs at
    once and drops them (their right-hand sides are in the closure from then on)"""
    c = m
    while c != full:
        nc = np.int64(~c)
        app = (la & nc) == 0
        if not app.any():
            break
        add = int(np.bitwise_or.reduce(ra[app]))
        if not add & ~c:
            break
        c |= add
        keep = ~app
        la, ra = la[keep], ra[keep]
    return c


def _reaches_np(m, la, ra, target):
    """_reaches for a long F given as numpy arrays of lhs and rhs masks (all applicable FDs at once per pass)"""
    c = m
    while target & ~c:
        app = (la & np.int64(~c)) == 0
        add = int(np.bitwise_or.reduce(ra[app])) if app.any() else 0
        if not add & ~c:
            return False
        c |= add
    return True


def _reaches(m, F, target):
    """target within the closure of m under F (pairs lhs mask, rhs mask)"""
    c = m
    if not target & ~c:
        return True
    changed = True
    while changed:
        changed = False
        for l, r in F:
            if r & ~c and not l & ~c:
                c |= r
                if not target & ~c:
                    return True
                changed = True
    return False


def _bits(m):
    out = []
    while m:
        b = m & -m
        out.append(b.bit_length() - 1)
        m ^= b
    return out


def _closure1(m, F):
    """closure under a complete atomic closure F: one pass suffices, since for every implied X -> A some minimal
    Y within X has Y -> A in F"""
    c = m
    for l, r in F:
        if not l & ~m:
            c |= r
    return c


# _LOW6[k]: the 64-bit word whose bit x is set iff the 6-bit mask x holds the 6-bit mask k
_LOW6 = np.array([sum(1 << x for x in range(64) if x & k == k) for k in range(64)], dtype=np.uint64)


def _min_keys(R, sigma, sm, is_key, bit, arrs=None):
    """B.minimal_keys(R, sigma) (Lucchesi-Osborn) with the same set operations, hence the same keys in the same order;
    is_key(mask) replaces the test R <= closure(X, sigma), and sm holds the masks of sigma.  An FD whose right-hand
    side misses the key cur yields S = lhs + cur, which holds cur, so it is skipped.  For a long sigma (arrs: numpy
    arrays of the lhs and rhs masks), the sets S of one key cur are tested at once against the keys known when cur is
    taken up; the others are then visited in the order of sigma and tested against the keys found since."""
    if arrs is None and len(sm) >= 48 and len(bit) < 63:
        arrs = (np.array([l for l, _ in sm], dtype=np.int64), np.array([r for _, r in sm], dtype=np.int64))

    def refine(key, km):                        # B.refine_min_key
        k = set(key)
        for a in list(key):
            b = bit[a]
            if is_key(km & ~b):
                k.discard(a)
                km &= ~b
        return frozenset(k), km
    k0, m0 = refine(R, sum(bit[a] for a in R))
    keys, kms, seen = [k0], [m0], {m0}
    # Once many keys are known, the test "some known key lies within S" is a lookup in a bitmap over all masks (bit m:
    # some key lies within m), kept current by marking the supersets of every new key; the batch test against all
    # keys costs |keys| per set S otherwise.  The bitmap is packed in words of the 64 masks that share their high
    # attributes: a key ORs, into every word whose high part holds its high attributes (an axis per high attribute,
    # fixed to 1 on the key's), the pattern of the low parts that hold its low attributes.
    nb = len(bit)
    nh = nb - 6
    U = Uv = None

    def mark(m):
        Uv[tuple(1 if m >> (nb - 1 - j) & 1 else slice(None) for j in range(nh))] |= _LOW6[m & 63]

    def covered(Sm):
        return int(U[Sm >> 6]) >> (Sm & 63) & 1
    i = 0
    while i < len(keys):
        cur, cm = keys[i], kms[i]
        if arrs is None:
            todo, n0 = ((t, lm | (cm & ~rm)) for t, (lm, rm) in enumerate(sm) if rm & cm), 0
        else:
            if U is None and len(kms) > (64 if len(sm) < 2000 else 0) and 8 <= nb <= 30:
                U = np.zeros(1 << nh, dtype=np.uint64)
                Uv = U.reshape((2,) * nh)
                for km in kms:
                    mark(km)
            la, ra = arrs
            ts = np.flatnonzero((ra & cm) != 0)
            Sa = la[ts] | (cm & ~ra[ts])
            if U is None:
                K = np.array(kms, dtype=np.int64)
                free = ~((K[None, :] & ~Sa[:, None]) == 0).any(axis=1)      # no key known now lies within S
            else:
                free = (U[Sa >> 6] >> (Sa & 63).astype(np.uint64)) & np.uint64(1) == 0
            todo, n0 = zip(ts[free].tolist(), Sa[free].tolist()), len(kms)
        for t, Sm in todo:
            if U is not None:
                if covered(Sm):                     # a key found since lies within S
                    continue
            else:
                nS = ~Sm
                if any(not km & nS for km in (kms[n0:] if n0 else kms)):      # some known key lies within S
                    continue
            lhs, rhs = sigma[t]
            mk, mm = refine(set(lhs) | (cur - rhs), Sm)
            if mm not in seen:
                keys.append(mk)
                kms.append(mm)
                seen.add(mm)
                if U is not None:
                    mark(mm)
        i += 1
    return keys


def _maximal(ms, nbits=0):
    """the masks of ms that lie in no other mask of ms"""
    if len(ms) > 2000 and 0 < nbits <= 24:
        # many masks over few attributes: sup[m] = some mask of ms holds m (a sum over supersets, one pass per bit);
        # m is maximal iff no m + {i} with i outside m has sup set
        arr = np.fromiter(ms, dtype=np.int64, count=len(ms))
        sup = np.zeros(1 << nbits, dtype=bool)
        sup[arr] = True
        for i in range(nbits):
            v = sup.reshape(-1, 2, 1 << i)
            v[:, 0, :] |= v[:, 1, :]
        strict = np.zeros(len(arr), dtype=bool)
        for i in range(nbits):
            free = (arr >> i & 1) == 0
            strict[free] |= sup[arr[free] | (1 << i)]
        return set(arr[~strict].tolist())
    small, big = [m for m in ms if bin(m).count("1") <= 8], [m for m in ms if bin(m).count("1") > 8]
    covered = set()
    for m in small:
        s = (m - 1) & m
        while s:
            covered.add(s)
            s = (s - 1) & m
    for m in big:
        for x in ms:
            if x != m and not x & ~m:
                covered.add(x)
    return {m for m in ms if m not in covered}


def _np_rng(rnd):
    """numpy's MT19937 in the state of rnd: random_sample draws the same doubles as rnd.random(), in bulk"""
    st = rnd.getstate()
    rs = np.random.RandomState()
    rs.set_state(("MT19937", np.array(st[1][:624], dtype=np.uint32), st[1][624]))
    return rs, st[2]


def _py_rng(rnd, rs, gauss):
    _, key, pos, _, _ = rs.get_state()
    rnd.setstate((3, tuple(int(x) for x in key) + (int(pos),), gauss))


def _key_masks(full, F):
    """all minimal keys (masks) of the schema full under its complete atomic FDs F; as a set, independent of order"""
    def refine(m):
        x = m
        while x:
            b = x & -x
            x ^= b
            if _closure1(m & ~b, F) == full:
                m &= ~b
        return m
    keys = [refine(full)]
    seen = set(keys)
    i = 0
    while i < len(keys):
        cur = keys[i]
        for l, r in F:
            Sm = l | (cur & ~r)
            if any(not k & ~Sm for k in keys):
                continue
            k = refine(Sm)
            if k not in seen:
                keys.append(k)
                seen.add(k)
        i += 1
    return keys


class Instance:
    """R, sigma0, candidates P (single-rhs FDs), pi, and the true hypothesis used by the oracle."""

    def __init__(self, R, sigma0, P, pi, truth, mode="synthesis", name="", recal=False):
        self.R, self.sigma0, self.P, self.pi, self.mode, self.name = list(R), list(sigma0), list(P), dict(pi), mode, name
        self._Rf = frozenset(self.R)
        self._bit = {a: 1 << i for i, a in enumerate(self.R)}
        self._ix = {a: i for i, a in enumerate(self.R)}
        self._full = (1 << len(self.R)) - 1
        self._mk, self._ii, self._sm = {}, {}, {}
        # the candidates' left-hand sides, indexed; has[i] is the bitset of those whose closure holds attribute i
        lix = {}
        for p in self.P:
            lix.setdefault(self.masks(p)[0], len(lix))
        self._lfull = (1 << len(lix)) - 1
        self._has0 = [0] * len(self.R)
        for m, j in lix.items():
            for i in range(len(self.R)):
                if m >> i & 1:
                    self._has0[i] |= 1 << j
        self._pj = {p: (lix[self.masks(p)[0]], self.indices(p)[1]) for p in self.P}
        self._single = all(len(r) == 1 for _, r in self._pj.values())
        self._pj1 = [(self._pj[p][0], self._pj[p][1][0]) for p in self.P] if self._single else None
        self._s0 = [self.indices(f) for f in self.sigma0]
        self._s0m = [self.masks(f) for f in self.sigma0]
        # caches per hypothesis (atomic closure, design, cover, validity), dropped once an answer contradicts it
        self._hc, self._applied = {}, {}
        self._robc, self._deadc, self._dead_last, self._gridc, self._grid_last = {}, {}, None, {}, None
        self._pix, self._prc, self._njg, self._xa, self._above = {p: i for i, p in enumerate(self.P)}, {}, None, {}, {}
        # for many candidates: their masks XA, lhs and rhs, and (single rhs) rhs attribute and lhs index, in numpy
        self._big = len(self.P) > 2000 and len(self.R) < 63
        if self._big:
            self._lq = np.array([self.masks(p)[0] for p in self.P], dtype=np.int64)
            self._rq = np.array([self.masks(p)[1] for p in self.P], dtype=np.int64)
            self._xam = self._lq | self._rq
        if self._single:
            self._pj_i = np.array([i for _, i in self._pj1], dtype=np.int64)
            self._pj_j = np.array([j for j, _ in self._pj1], dtype=np.int64)
        self._fidx, self._base0 = [self.indices(p) for p in self.P], None
        # recalibration from the answers: rho_ab(p) = sigmoid(a * logit(rho(p)) + b), with a grid prior on (a, b)
        # centred at the estimator itself (a = 1, b = 0); the answers update the grid posterior (Bayesian, exchangeable)
        self.recal = recal
        self.logit = {p: math.log(v / (1 - v)) for p, v in self.pi.items()}
        self.grid, self.grid_prior = GRID, GRID_PRIOR
        self.truth = self.close(truth)

    # ---- FD machinery with caches ----
    def masks(self, f):
        m = self._mk.get(f)
        if m is None:
            b = self._bit
            m = self._mk[f] = (sum(b[a] for a in f[0]), sum(b[a] for a in f[1]))
        return m

    def indices(self, f):
        """(lhs attribute indices, rhs attribute indices, lhs mask)"""
        m = self._ii.get(f)
        if m is None:
            m = self._ii[f] = (tuple(self._ix[a] for a in f[0]), tuple(self._ix[a] for a in f[1]), self.masks(f)[0])
        return m

    def smask(self, s):
        m = self._sm.get(s)
        if m is None:
            m = self._sm[s] = sum(self._bit[a] for a in s)
        return m

    def _cache(self, h):
        c = self._hc.get(h)
        if c is None:
            c = self._hc[h] = {"h": h}
        return c

    def forget(self, answers):
        """drop the caches of the hypotheses that an answer contradicts; they never return to the sample"""
        new = [(p, a) for p, a in answers.items() if self._applied.get(p) != a]
        if not new:
            return
        for p, a in new:
            self._applied[p] = a
        for h in [h for h in self._hc if any((p in h) != a for p, a in new)]:
            del self._hc[h]

    def _prop(self, has, F, first, nj=None):
        """least fixpoint of the bitsets has[i] (the candidates' left-hand sides whose closure holds attribute i) under
        F; has is closed under the FDs of F outside first, so the first pass evaluates first only, and later passes
        only the FDs whose left-hand side met a change.  None once a refuted candidate (j, rhs) in nj is implied."""
        full = self._lfull
        todo = first
        while True:
            delta = 0
            for L, Rr, lm in todo:
                app = full
                for i in L:
                    app &= has[i]
                if app:
                    for i in Rr:
                        if app & ~has[i]:
                            has[i] |= app
                            delta |= 1 << i
            if not delta:
                return has
            if nj and self._refuted(has, nj):
                return None
            todo = [f for f in F if f[2] & delta]

    def _refuted(self, has, nj):
        """some refuted candidate (j, rhs) of nj is implied.  With single right-hand sides, nj is grouped once into
        the bitset of refuted left-hand sides per attribute, and the test is one AND per attribute"""
        g = self._njg
        if g is None or g[0] is not nj:
            if all(len(rr) == 1 for _, rr in nj):
                m = [0] * len(self.R)
                for j, (i,) in nj:
                    m[i] |= 1 << j
                g = self._njg = (nj, [(i, b) for i, b in enumerate(m) if b])
            else:
                g = self._njg = (nj, None)
        if g[1] is not None:
            return any(has[i] & b for i, b in g[1])
        return any(all(has[i] >> j & 1 for i in rr) for j, rr in nj)

    def _has(self, sub):
        """bitsets has[i]: the candidates' left-hand sides whose closure under sigma0 + sub holds attribute i"""
        F = self._s0 + [self.indices(f) for f in sub]
        return self._prop(self._has0[:], F, F)

    def _implied(self, has):
        if self._single and self._big:          # the bitsets unpacked once, the candidates looked up in numpy
            nl = self._lfull.bit_length()
            nbytes = (nl + 7) // 8
            Bm = np.stack([np.unpackbits(np.frombuffer(x.to_bytes(nbytes, "little"), dtype=np.uint8),
                                         bitorder="little")[:nl] for x in has])
            P = self.P
            return frozenset([P[k] for k in np.flatnonzero(Bm[self._pj_i, self._pj_j]).tolist()])
        if self._single:
            return frozenset([p for p, (j, i) in zip(self.P, self._pj1) if has[i] >> j & 1])
        return frozenset([p for p in self.P if all(has[i] >> self._pj[p][0] & 1 for i in self._pj[p][1])])

    def has_of(self, pos):
        """the bitsets has of sigma0 plus the candidates at positions pos of P: the fixpoint of close(), from the
        bitsets closed under sigma0 (computed once)"""
        if self._base0 is None:
            self._base0 = self._prop(self._has0[:], self._s0, self._s0)
        Fs = [self._fidx[i] for i in pos]
        return self._prop(self._base0[:], self._s0 + Fs, Fs)

    def holds(self, has, pos):
        """for the candidates at positions pos (a numpy array), whether the bitsets has imply them"""
        if self._single and len(pos) < 1000:
            pj = self._pj1
            return np.array([has[pj[k][1]] >> pj[k][0] & 1 for k in pos.tolist()], dtype=bool)
        if self._single:
            nl = self._lfull.bit_length()
            nbytes = (nl + 7) // 8
            Bm = np.stack([np.unpackbits(np.frombuffer(x.to_bytes(nbytes, "little"), dtype=np.uint8),
                                         bitorder="little")[:nl] for x in has])
            return Bm[self._pj_i[pos], self._pj_j[pos]].astype(bool)
        return np.array([all(has[i] >> self._pj[self.P[k]][0] & 1 for i in self._pj[self.P[k]][1])
                         for k in pos.tolist()], dtype=bool)

    def close(self, sub):
        return self._cache(self._implied(self._has(sub)))["h"]       # one object per hypothesis

    def _atomic(self, sigma):
        """E2.atomic_closure(R, sigma): X -> A for every minimal key X other than {A} of (R, sigma + {A -> R})"""
        R, full, bit = self._Rf, self._full, self._bit
        sm = [self.masks(f) for f in sigma]
        F = _merge(sm)
        memo = {}
        if len(F) > 300 and len(self.R) < 63:
            la = np.array([l for l, _ in F], dtype=np.int64)
            ra = np.array([r for _, r in F], dtype=np.int64)

            def cl(m):
                c = memo.get(m)
                if c is None:
                    c = memo[m] = _closure_np(m, la, ra, full)
                return c
        else:
            def cl(m):
                c = memo.get(m)
                if c is None:
                    c = memo[m] = _closure(m, F, full)
                return c

        out = []
        arrs = None
        if len(sm) >= 47 and len(self.R) < 63:          # the masks of sigma + [A -> R], the last one set per attribute
            arrs = (np.array([l for l, _ in sm] + [0], dtype=np.int64),
                    np.array([r for _, r in sm] + [full], dtype=np.int64))
        for a in sorted(R):
            ia = bit[a]
            if arrs is not None:
                arrs[0][-1] = ia
            ks = _min_keys(R, list(sigma) + [(frozenset({a}), R)], sm + [(ia, full)],
                           lambda m: bool(cl(m) & ia) or cl(m) == full, bit, arrs)
            out += [S.fd(k, a) for k in ks if a not in k]
        return sorted(out, key=lambda f: (len(f[0]), sorted(f[0]), sorted(f[1])))

    def atomic(self, h):
        c = self._cache(h)
        if "ac" not in c:
            c["ac"] = self._atomic(self.sigma0 + sorted(h, key=repr))
            acr = [[] for _ in self.R]
            for f in c["ac"]:
                l, r = self.masks(f)
                for i in _bits(r):
                    acr[i].append((l, r))
            c["acr"] = acr
        return c["ac"]

    def _eliminate(self, sa, sm=None):
        """the elimination skeleton in list order (S.canonical_cover, and B._eliminate in mode synthesis): the kept FDs
        and their schemata in order of first appearance"""
        sm = [self.masks(f) for f in sa] if sm is None else sm
        idx, work = {}, []                      # the work list, merged by left-hand side
        for l, r in sm:
            if l in idx:
                work[idx[l]][1] |= r
            else:
                idx[l] = len(work)
                work.append([l, r])
        kept, D, seen = [], [], set()
        big = len(work) > 1500 and len(self.R) < 63     # a long work list: the closures in numpy, same booleans
        if big:
            wl = np.array([w[0] for w in work], dtype=np.int64)
            wr = np.array([w[1] for w in work], dtype=np.int64)
        for f, (l, r) in zip(sa, sm):
            j = idx[l]
            e = work[j]
            e[1] &= ~r                          # the rest of the work list (B.is_redundant)
            if big:
                wr[j] = e[1]
            if not (_reaches_np(l, wl, wr, r) if big else _reaches(l, work, r)):
                e[1] |= r
                if big:
                    wr[j] = e[1]
                kept.append(f)
                XA = f[0] | f[1]
                if XA not in seen:
                    seen.add(XA)
                    D.append(XA)
        return kept, D

    def _synth(self, sa):
        """S.design(R, sa, mode) and S.canonical_cover(sa); in mode synthesis one elimination serves both, and the
        minimal keys are computed only when no schema holds a key"""
        if self.mode != "synthesis":
            return (frozenset(frozenset(s) for s in S.design(self.R, sa, self.mode)),
                    [self.masks(f) for f in S.canonical_cover(sa)])
        sm = [self.masks(f) for f in sa]
        kept, D = self._eliminate(sa, sm)
        if len(D) > 200 and len(self.R) < 63:                           # subset removal, on masks
            M = np.array([self.smask(x) for x in D], dtype=np.int64)
            D = [x for x, m in zip(D, M.tolist()) if not (((m & ~M) == 0) & (M != m)).any()]
        else:
            D = [XA for XA in D if not any(XA < XA2 for XA2 in D)]      # subset removal
        Fa = _merge(sm)
        if not any(_closure1(self.smask(XA), Fa) == self._full for XA in D):
            keys = _min_keys(frozenset(self.R), sa, sm, lambda m: _closure1(m, Fa) == self._full, self._bit)
            D.append(frozenset(min(keys, key=len)))
        return frozenset(frozenset(s) for s in D), [self.masks(f) for f in kept]

    def alg(self, h):
        c = self._cache(h)
        if "alg" not in c:
            c["alg"], c["cover"] = self._synth(self.atomic(h))
        return c["alg"]

    def cover(self, h):
        """the canonical cover of the atomic closure of sigma0 + h, as masks"""
        self.alg(h)
        return self._cache(h)["cover"]

    def schema_ok(self, s, h):
        # projection (masks, merged) and 3NF of one schema, cached per (schema, hypothesis): schemata recur across
        # decisions.  The projection of the atomic closure is the atomic closure of the projection (B.projection).
        nf = self._cache(h).setdefault("nf", {})
        if s not in nf:
            sm = self.smask(s)
            self.atomic(h)
            acr = self._hc[h]["acr"]
            p = [(l, r) for i in _bits(sm) for l, r in acr[i] if not l & ~sm]
            F = _merge(p)
            ks = _key_masks(sm, F)
            prime = 0
            for k in ks:
                prime |= k
            nf[s] = (F, all(not r & ~l or any(not k & ~l for k in ks) or not r & ~prime for l, r in p))
        return nf[s]

    def valid(self, D, h):
        v = self._cache(h).setdefault("valid", {})
        if D in v:
            return v[D]
        full = self._full
        res = True
        E = []
        for s in D:
            p, nf = self.schema_ok(s, h)
            if not nf:
                res = False
                break
            E += p
        if res:                                 # dependency preservation
            E = _merge(E)
            sms = [self.smask(s) for s in D]
            for l, r in self.cover(h):
                if any(not (l | r) & ~x for x in sms):      # embedded in a schema, hence in its projection
                    continue
                if r & ~_closure(l, E, full):
                    res = False
                    break
        if res:
            # losslessness: a schema that is a superkey under the embedded FDs suffices (Theorem 5.7(b));
            # since the design preserves sigma0 + h here, that is also necessary
            res = any(_closure(x, E, full) == full for x in sms)
        v[D] = res
        return res

    def unpreserved(self, D, h):
        """the FDs of the atomic closure of sigma0 + h that the projections onto the schemata of D do not imply (u_str
        of the evaluation, with h in place of the truth)"""
        E = []
        for s in D:
            E += self.schema_ok(s, h)[0]
        E, full = _merge(E), self._full
        n = 0
        for f in self.atomic(h):
            l, r = self.masks(f)
            n += bool(r & ~_closure(l, E, full))
        return n

    def good(self, D, h, eps):
        # the size test first: it is cheap, and a design with too many tables is not good whether valid or not (the
        # hedge design of a wide relation has thousands of schemata, each needing a projection and a 3NF test)
        return len(D) <= len(self.alg(h)) + eps and self.valid(D, h)

    # ---- hypothesis sampling ----
    def dead(self, answers):
        # open candidates that, with the confirmed ones, imply a refuted candidate: false in every consistent hypothesis.
        # With closures cl under sigma0 + confirmed, q = X -> A is dead iff some refuted Y -> B has X within c = cl(Y)
        # and B in cl(c + A).  While only refutations are added, only the new ones need checking.
        key = frozenset(answers.items())
        if key in self._deadc:
            return self._deadc[key]
        yes = frozenset(p for p, a in answers.items() if a)
        no = [p for p, a in answers.items() if not a]
        full = self._full
        res = set()
        if no:
            last = self._dead_last
            if last is not None and last[0] == yes and last[1] <= set(no):
                old, new_no = last[1], [r for r in no if r not in last[1]]
                res = {q for q in last[2] if q not in answers}
            else:
                old, new_no = set(), no
            base = _merge(self._s0m + [self.masks(p) for p in yes])
            memo = {}

            def cl(m):
                c = memo.get(m)
                if c is None:
                    c = memo[m] = _closure(m, base, full)
                return c

            groups, every = {}, False
            for r in new_no:
                l, b = self.masks(r)
                c = cl(l)
                if not b & ~c:          # the confirmed ones imply a refuted candidate: every open candidate is dead
                    every = True
                    break
                groups.setdefault(c, []).append(b)
            if every:
                res = {q for q in self.P if q not in answers}
            elif groups and self._big:      # the same set, a group at a time over all candidates in numpy
                P, kill = self.P, {}
                elig = np.ones(len(P), dtype=bool)
                elig[[self._pix[q] for q in answers if q in self._pix]] = False
                elig[[self._pix[q] for q in res]] = False
                for c, bs in groups.items():
                    nc = np.int64(~c)
                    sel = np.flatnonzero(elig & ((self._lq & nc) == 0) & ((self._rq & nc) != 0))
                    if not len(sel):
                        continue
                    rqs = self._rq[sel]
                    for rq in np.unique(rqs).tolist():
                        v = kill.get((c, rq))
                        if v is None:
                            t = cl(c | rq)
                            v = kill[(c, rq)] = any(not b & ~t for b in bs)
                        if v:
                            hit = sel[rqs == rq]
                            res.update(P[k] for k in hit.tolist())
                            elig[hit] = False
            elif groups:
                gl = list(groups.items())
                kill = {}
                for q in self.P:
                    if q in answers or q in res:
                        continue
                    lq, rq = self.masks(q)
                    for c, bs in gl:
                        if lq & ~c or not rq & ~c:
                            continue
                        v = kill.get((c, rq))
                        if v is None:
                            t = cl(c | rq)
                            v = kill[(c, rq)] = any(not b & ~t for b in bs)
                        if v:
                            res.add(q)
                            break
            self._dead_last = (yes, old | set(new_no), res)
        self._deadc = {key: res}
        return res

    def _akey(self, answers):
        """the answer set as a compact exact key: bitmaps of the asked and of the confirmed candidates (a frozenset of
        the answers if one is outside the candidates).  A frozenset per answer set costs quadratic memory over a run
        that asks every candidate (tens of GB on tpch_lineitem_orders)."""
        pix = self._pix
        ix = [pix.get(p) for p in answers]
        if None in ix:
            return frozenset(answers.items())
        n = len(self.P)
        m = np.zeros(2 * n, dtype=bool)
        m[ix] = True
        m[[n + i for i, a in zip(ix, answers.values()) if a]] = True
        return np.packbits(m).tobytes()

    def grid_posterior(self, answers):
        # incremental over the answers in their order: the same sums as a fresh computation
        key = self._akey(answers)
        if key not in self._gridc:
            items = list(answers.items())
            last = self._grid_last
            if last is not None and items[:len(last[0])] == last[0]:
                lw, rest = list(last[1]), items[len(last[0]):]
            else:
                lw, rest = [math.log(w0) for w0 in self.grid_prior], items
            for g, (a, b) in enumerate(self.grid):
                l = lw[g]
                for p, y in rest:
                    z = a * self.logit[p] + b
                    l += -math.log1p(math.exp(-z)) if y else -math.log1p(math.exp(z))
                lw[g] = l
            self._grid_last = (items, lw)
            m = max(lw)
            w = [math.exp(x - m) for x in lw]
            t = sum(w)
            self._gridc[key] = [x / t for x in w]       # keyed by the set, as before: the first order wins
        return self._gridc[key]

    def sample(self, answers, rnd, k, tries=200):
        # exact posterior: drop the dead candidates (implied refutations), reject what joint implications still refute
        # (the random numbers are those of a per-candidate loop, drawn in bulk: rnd.choices takes one, then one per
        # open candidate, so the samples and the state of rnd afterwards are unchanged)
        out = []
        yes = [p for p, a in answers.items() if a]
        nj = [self._pj[p] for p, a in answers.items() if not a and p in self._pj]
        dead = self.dead(answers)
        open_ = [p for p in self.P if p not in answers and p not in dead]
        post = self.grid_posterior(answers) if self.recal else None
        prc = {None: np.array([self.pi[p] for p in open_], dtype=float)} if post is None else {}
        if post is not None:
            cum = list(itertools.accumulate(post))              # as in random.choices
            total, hi = cum[-1] + 0.0, len(cum) - 1
            # the recalibrated probabilities of every candidate under (a, b), kept across calls (the same expression
            # per candidate as before, so the same doubles), and the positions of the open candidates among them
            oi = np.array([self._pix[p] for p in open_], dtype=np.int64)
        Fb = self._s0 + [self.indices(p) for p in yes]
        base = self._prop(self._has0[:], Fb, Fb)
        fo = [self.indices(p) for p in open_]
        n = len(open_)
        rs, gauss = _np_rng(rnd)
        try:
            for _ in range(k):
                for _ in range(tries):
                    if post is None:
                        pr, u = prc[None], rs.random_sample(n)
                    else:
                        u = rs.random_sample(n + 1)
                        a, b = self.grid[bisect.bisect(cum, float(u[0]) * total, 0, hi)]
                        u = u[1:]
                        pr = prc.get((a, b))
                        if pr is None:
                            full = self._prc.get((a, b))
                            if full is None:
                                full = self._prc[(a, b)] = np.array(
                                    [1 / (1 + math.exp(-(a * self.logit[p] + b))) for p in self.P], dtype=float)
                            pr = prc[(a, b)] = full[oi]
                    Fs = [fo[i] for i in np.flatnonzero(u < pr).tolist()]
                    has = self._prop(base[:], Fb + Fs, Fs, nj)
                    if has is not None and not (nj and self._refuted(has, nj)):
                        out.append(self._cache(self._implied(has))["h"])
                        break
        finally:
            _py_rng(rnd, rs, gauss)
        return out

    # ---- hedge decisions ----
    def robust(self, answers):
        """S.robust_design(R, sigma0 + confirmed, open): schemata XA for a cover of the confirmed FDs and for every open
        candidate, the maximal ones, plus a key when none holds one"""
        key = frozenset(answers.items())
        if key in self._robc:
            return self._robc[key]
        yes = [p for p, a in answers.items() if a]
        open_ = [p for p in self.P if p not in answers]
        # S.atomic_closure inserts the attributes of every left-hand side in sorted order; rebuilding them so keeps
        # the order of the minimal keys below identical
        Ca = [S.fd(tuple(sorted(f[0])), next(iter(f[1]))) for f in self._atomic(self.sigma0 + yes)]
        rep = {}                                # mask -> the schema XA first met (the cover first, then P in order)
        for f in self._eliminate(Ca)[0]:
            x = f[0] | f[1]
            rep.setdefault(self.smask(x), x)
        if len(self.P) > 2000:
            # many candidates: their masks XA in numpy; a maximal mask takes its schema from the first open candidate
            oi = self._open_idx(answers)
            xm = self._xam[oi]
            mx = _maximal(set(rep) | set(np.unique(xm).tolist()), len(self.R))
            Sx = [x for m, x in rep.items() if m in mx]
            need = [m for m in mx if m not in rep]
            if need:
                sel = np.flatnonzero(np.isin(xm, np.array(need, dtype=np.int64)))
                _, first = np.unique(xm[sel], return_index=True)
                Sx += [self._xa_of(self.P[int(oi[sel[k]])]) for k in first.tolist()]
        else:
            for p in open_:
                x = self._xa_of(p)
                rep.setdefault(self.smask(x), x)
            mx = _maximal(set(rep), len(self.R))
            Sx = [x for m, x in rep.items() if m in mx]
        sm = [self.masks(f) for f in Ca]
        Fa = _merge(sm)
        if not any(_closure1(self.smask(x), Fa) == self._full for x in Sx):
            keys = _min_keys(frozenset(self.R), Ca, sm, lambda m: _closure1(m, Fa) == self._full, self._bit)
            Sx.append(min(keys, key=len))
        self._robc = {key: frozenset(frozenset(s) for s in Sx)}
        return self._robc[key]

    def _xa_of(self, p):
        x = self._xa.get(p)
        if x is None:
            x = self._xa[p] = p[0] | p[1]
        return x

    def _open_idx(self, answers):
        """positions in P of the unanswered candidates, in order"""
        keep = np.ones(len(self.P), dtype=bool)
        keep[[self._pix[p] for p in answers if p in self._pix]] = False
        return np.flatnonzero(keep)

    def threshold(self, answers, tau):
        yes = [p for p, a in answers.items() if a]
        above = self._above.get(tau)            # the candidates with pi >= tau, in the order of P
        if above is None:
            above = self._above[tau] = [p for p in self.P if self.pi[p] >= tau]
        sub = yes + [p for p in above if p not in answers]
        h = self._implied(self._has(sub))
        bad = {p for p, a in answers.items() if not a}
        return self.alg(self._cache(h)["h"]) if not (h & bad) else None


def decisions(inst, answers, samples, max_alg=15):
    cnt = collections.Counter(inst.alg(h) for h in samples)
    ds = [d for d, _ in cnt.most_common(max_alg)]
    ds.append(inst.robust(answers))
    for tau in (0.5, 0.7, 0.9, 1.01):
        d = inst.threshold(answers, tau)
        if d is not None:
            ds.append(d)
    return list(dict.fromkeys(ds))


def good_matrix(inst, ds, samples, eps):
    return {d: [inst.good(d, h, eps) for h in samples] for d in ds}


def covering(inst, ds, samples, eps, delta=0.0, G=None):
    """decision whose region holds at least 1 - delta of the (posterior) samples; most mass, then fewest tables"""
    if not samples:
        return None
    G = G or good_matrix(inst, ds, samples, eps)
    best, key = None, None
    for d in ds:
        frac = sum(G[d]) / len(samples)
        if frac >= 1 - delta - 1e-12:
            k = (-frac, len(d))
            if key is None or k < key:
                best, key = d, k
    return best


def voi_score(G, samples, p):
    # myopic value of information: expected gain in the best decision's posterior mass after asking p
    idx_y = [i for i, h in enumerate(samples) if p in h]
    idx_n = [i for i, h in enumerate(samples) if p not in h]
    n = len(samples)

    def best(idx):
        return max(sum(g[i] for i in idx) for g in G.values()) / len(idx) if idx else 0.0

    return (len(idx_y) / n) * best(idx_y) + (len(idx_n) / n) * best(idx_n) - best(range(n))


def classes_cover(inst, ds, samples, eps):
    # greedy set cover of the samples by decision regions; each sample gets the first decision that covers it
    left = set(range(len(samples)))
    label = {}
    regions = {d: {i for i in left if inst.good(d, samples[i], eps)} for d in ds}
    while left:
        d = max(regions, key=lambda d: len(regions[d] & left))
        got = regions[d] & left
        if not got:
            for i in left:          # cannot happen: alg(h) is good for h, but alg(h) may be outside ds
                label[i] = ("own", samples[i])
            break
        for i in got:
            label[i] = d
        left -= got
    return [label[i] for i in range(len(samples))]


def ec2_score(labels, samples, p):
    # expected weight of cut edges (edges join samples of different classes), uniform sample weights
    def w(idx):
        c = collections.Counter(labels[i] for i in idx)
        n = len(idx)
        return (n * n - sum(v * v for v in c.values())) / 2

    all_idx = range(len(samples))
    W = w(all_idx)
    yes = [i for i in all_idx if p in samples[i]]
    no = [i for i in all_idx if p not in samples[i]]
    n = len(samples)
    return (len(yes) / n) * (W - w(yes)) + (len(no) / n) * (W - w(no))


def run(inst, policy, eps, seed=0, K=80, max_q=None, log=False, delta=0.0, trace=None, return_design=False,
        answers0=None, fresh="check", oracle_noise=0.0, oracle=None):
    """oracle_noise > 0 makes the oracle answer wrongly with that probability while Confirm still trusts every answer
    (the naive baseline of noisy.py). oracle (a callable p -> bool, for example a table of LLM answers) replaces the
    answer p in inst.truth; the final design is still judged against inst.truth"""
    rnd = random.Random(seed)
    ornd = random.Random(7919 * seed + 1)
    answers = dict(answers0 or {})
    max_q = len(inst.P) if max_q is None else max_q
    order = None
    if policy == "rand":
        order = inst.P[:]
        rnd.shuffle(order)
    elif policy == "pi":
        order = sorted(inst.P, key=lambda p: -inst.pi[p])
    samples = inst.sample(answers, rnd, K)
    while True:
        inst.forget(answers)
        if fresh == "always":
            samples = inst.sample(answers, rnd, K)
        samples = [h for h in samples if consistent(h, answers)]
        if len(samples) < K // 2:
            samples += inst.sample(answers, rnd, K - len(samples))
        ds = decisions(inst, answers, samples)
        G = good_matrix(inst, ds, samples, eps)
        d = covering(inst, ds, samples, eps, delta, G)
        if len(samples) < max(10, K // 4):     # too few posterior samples to certify anything
            d = None
        if d is not None and fresh == "check":
            # the working sample chose the questions, and a refuted candidate removes exactly the samples that held it,
            # so the survivors drift towards hypotheses that avoid every asked candidate; certify only on an independent
            # sample, and replace the working sample by it when the check fails
            new = inst.sample(answers, rnd, 2 * K)
            if len(new) < max(10, K // 4) or sum(inst.good(d, h, eps) for h in new) < (1 - delta - 1e-12) * len(new):
                d = None
                if new:
                    samples = new[:K]
                    ds = decisions(inst, answers, samples)
                    G = good_matrix(inst, ds, samples, eps)
        if trace is not None:
            # anytime view: the decision with the most posterior mass now, its mass, and whether it is good for the truth
            b = covering(inst, ds, samples, eps, 1.0, G)
            if b is not None:
                trace.append((len(answers), round(sum(G[b]) / len(samples), 3), inst.good(b, inst.truth, eps)))
        open_ = [p for p in inst.P if p not in answers]
        if d is not None or not open_ or len(answers) >= max_q:
            break
        # candidates on which the samples disagree; the others carry no information
        cnt = collections.Counter(p for h in samples for p in h)
        informative = [p for p in open_ if 0 < cnt[p] < len(samples)]
        if not informative:
            informative = open_
        if not samples:                         # no consistent sample found: ask the most probable open candidate
            p = max(open_, key=lambda q: inst.pi[q])
        elif policy in ("rand", "pi"):
            p = next(q for q in order if q in informative)
        elif policy == "unc":
            p = min(informative, key=lambda q: abs(cnt[q] / len(samples) - 0.5))
        elif policy == "drd":
            labels = classes_cover(inst, ds, samples, eps)
            p = max(informative, key=lambda q: ec2_score(labels, samples, q))
        elif policy == "struct":
            labels = [inst.alg(h) for h in samples]
            p = max(informative, key=lambda q: ec2_score(labels, samples, q))
        elif policy == "marg":
            p = max(informative, key=lambda q: (cnt[q], inst.pi[q]))
        elif policy == "voi":
            p = max(informative, key=lambda q: (voi_score(G, samples, q), inst.pi[q]))
        else:
            raise ValueError(policy)
        answers[p] = (oracle(p) if oracle is not None else p in inst.truth) != (oracle_noise > 0 and ornd.random() < oracle_noise)
        if log:
            print("  ask", p, "->", answers[p])
    certified = d is not None       # found by covering (and, with fresh="check", confirmed on the fresh sample)
    if d is None:   # budget exhausted or no covering decision: fall back to the most frequent design
        d = (collections.Counter(inst.alg(h) for h in samples).most_common(1)[0][0] if samples
             else inst.alg(inst.close([p for p, a in answers.items() if a])))
    opt = inst.alg(inst.truth)
    out = {"questions": len(answers), "valid": inst.valid(d, inst.truth), "good": inst.good(d, inst.truth, eps),
           "extra_tables": len(d) - len(opt), "exact": d == opt, "tables": len(d)}
    if trace is not None:
        out["trace"] = trace
    if return_design:
        out["design"] = d
        out["certified"] = certified
    return out


SD_LOG_A, SD_B = 0.5, 1.5     # prior of the recalibration: log a ~ N(0, SD_LOG_A^2), b ~ N(0, SD_B^2)
GRID = [(math.exp(0.4 * i), 0.5 * j) for i in range(-4, 7) for j in range(-16, 17)]
GRID_PRIOR = [math.exp(-0.5 * (math.log(a) / SD_LOG_A) ** 2 - 0.5 * (b / SD_B) ** 2) for a, b in GRID]


def recalibrated(pi, answers):
    """posterior-mean probabilities sigmoid(a * logit(pi) + b) under the grid posterior of (a, b) given the answers"""
    lg = {p: math.log(v / (1 - v)) for p, v in pi.items()}
    lw = []
    for (a, b), w0 in zip(GRID, GRID_PRIOR):
        l = math.log(w0)
        for p, y in answers.items():
            z = a * lg[p] + b
            l += -math.log1p(math.exp(-z)) if y else -math.log1p(math.exp(z))
        lw.append(l)
    m = max(lw)
    w = [math.exp(x - m) for x in lw]
    t = sum(w)
    return {p: sum(wi / t / (1 + math.exp(-(a * lg[p] + b))) for wi, (a, b) in zip(w, GRID)) for p in pi}


def certification_bound(pi, false, delta):
    """Theorem 18: questions on the false candidates C before the posterior of 'no member of C holds' reaches
    1 - delta, if candidates were implication-free; the largest-pi-first order attains it"""
    w = sorted((-math.log(1 - pi[p]) for p in false), reverse=True)
    budget, rest, k = -math.log(1 - delta) if delta > 0 else 0.0, sum(w), 0
    while rest > budget + 1e-12 and k < len(w):
        rest -= w[k]
        k += 1
    return k


def consistent(h, answers):
    return all((p in h) == a for p, a in answers.items())


def identify(inst, seed=0, K=80):
    """questions until all consistent samples share the synthesized structure (struct policy, own stopping rule)"""
    rnd = random.Random(seed)
    answers = {}
    samples = inst.sample(answers, rnd, K)
    while True:
        samples = [h for h in samples if consistent(h, answers)]
        if len(samples) < K // 2:
            samples += inst.sample(answers, rnd, K - len(samples))
        labels = [inst.alg(h) for h in samples]
        open_ = [p for p in inst.P if p not in answers]
        if len(set(labels)) <= 1 or not open_:
            break
        cnt = collections.Counter(p for h in samples for p in h)
        informative = [p for p in open_ if 0 < cnt[p] < len(samples)] or open_
        p = max(informative, key=lambda q: ec2_score(labels, samples, q))
        answers[p] = p in inst.truth
    return len(answers)
