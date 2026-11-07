"""
Design note item 74: Normalize (Papenbrock and Naumann, Data-driven Schema Normalization, EDBT 2017, Secs. 3-7) in its
fully automatic mode, as a baseline that asks no designer, and its score of a violating FD, which v6f_norm.py uses as the
prior of Cert3NF's advisor.

Input: the minimal FDs mined on the instance (the candidates P and the mined FDs implied0 that the declared key implies),
and the declared key as the primary key of the input relation (none for the three relations without one).
  closure      every minimal left-hand side X extends to X -> cl(X) \\ X over the mined FDs (Sec. 4)
  FDs of Ri    the mined left-hand sides X within Ri, with right-hand side cl(X) & Ri \\ X (Lemma 3)
  keys of Ri   the left-hand sides whose closure covers Ri, and the primary key of Ri (Sec. 5)
  violations   Algorithm 4: skip a left-hand side with an attribute that holds '?' (the cleaned empty value), one that
               contains a key of Ri, and one whose split would break a foreign key of Ri (it meets Y and is not inside
               X u Y); with a primary key, its attributes leave Y, and an empty Y is skipped
  score        the mean of four features (Sec. 7.2), on the instance of Ri (the projection of the data, duplicates removed):
               length 1/2 (1/|X| + |Y| / (|Ri| - 2)), at most 1; value 1 / max(1, |max(X)| - 7), max(X) the longest
               concatenation of the values of X; position 1/2 (1/(|between(X)| + 1) + 1/(|between(Y)| + 1)), between(Z)
               the attributes of Ri outside Z that lie between the first and the last attribute of Z; duplication
               1/2 (2 - |uniques(X)|/|values(X)| - |uniques(Y)|/|values(Y)|), uniques the distinct combinations and
               values the records of Ri (counted exactly instead of the paper's Bloom-filter estimate)
  choice       per relation the violating FD of largest score; ties: the smaller X, then X and Y in attribute order
  split        R1 = (Ri \\ Y) u X keeps the primary key of Ri and gets the foreign key X; R2 = X u Y with primary key X;
               the existing foreign keys go to the part that contains them, R1 first; until no relation has a violation.
The design is judged as every automatic method is (auto_confirm.evaluate), with the candidates that the declared key and
the FDs of the splits imply as its predicted FDs.

Usage (in confirm/):
  CONFIRM_TRUTH=full CONFIRM_ORACLE=gold CONFIRM_BATCH=3 python normalize.py run --out v6f_fresh3_extra/normalize/normalize_full.jsonl
  CONFIRM_BATCH=3 python normalize.py prior   the scores of the candidates for v6f_norm.py, v6f_fresh3_extra/normalize/prior/<ds>.json
  python normalize.py test        the example of the paper and the three skips of Algorithm 4 on small instances
"""
import argparse, json, os, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
INST = os.path.join(HERE, "v6f_fresh3_extra", "normalize", "inst")


def mask(xs):
    m = 0
    for x in xs:
        m |= 1 << x
    return m


def members(m):
    out, i = [], 0
    while m:
        if m & 1:
            out.append(i)
        m >>= 1
        i += 1
    return out


def popcount(m):
    return bin(m).count("1")


class Data:
    """an instance as integer codes, with the length of every value and the attributes that hold '?'"""

    def __init__(self, M, lens, null):
        self.M, self.lens, self.null = np.asarray(M, dtype=np.int64), lens, mask(j for j, x in enumerate(null) if x)
        self.n = self.M.shape[0]
        self._distinct, self._maxlen = {}, {}

    @classmethod
    def load(cls, ds):
        z = np.load(os.path.join(INST, ds + ".npz"))
        m = z["M"].shape[1]
        return cls(z["M"], [z[f"len{j}"] for j in range(m)], z["null"]), [str(x) for x in z["names"]]

    def distinct(self, m):
        """the number of distinct combinations of the attributes in m over the records"""
        if m not in self._distinct:
            cols = members(m)
            if not cols:
                self._distinct[m] = 1
            else:
                code = self.M[:, cols[0]].copy()
                for j in cols[1:]:
                    _, code = np.unique(code, return_inverse=True)
                    code = code.astype(np.int64).ravel() * (int(self.M[:, j].max()) + 1) + self.M[:, j]
                self._distinct[m] = int(len(np.unique(code)))
        return self._distinct[m]

    def maxlen(self, m):
        """the length of the longest concatenation of the values of the attributes in m"""
        if m not in self._maxlen:
            tot = np.zeros(self.n, dtype=np.int64)
            for j in members(m):
                tot += self.lens[j][self.M[:, j]]
            self._maxlen[m] = int(tot.max()) if self.n else 0
        return self._maxlen[m]


def closures(lhss, F):
    """cl(X) for every X in lhss over the FDs F, as (lhs mask, rhs mask) pairs"""
    L = np.array([l for l, _ in F], dtype=np.int64)
    R = np.array([r for _, r in F], dtype=np.int64)
    c = np.array(list(lhss), dtype=np.int64)
    while True:
        prev = c.copy()
        for l, r in zip(L, R):
            c[(c & l) == l] |= r
        if (c == prev).all():
            return dict(zip(lhss, (int(x) for x in c)))


def between(Z, Ri):
    """the attributes of Ri outside Z between the first and the last attribute of Z"""
    zs = members(Z)
    if len(zs) < 2:
        return 0
    lo, hi = zs[0], zs[-1]
    return sum(1 for a in members(Ri) if lo < a < hi and not Z >> a & 1)


def score(X, Y, Ri, data):
    """the violating-FD score of X -> Y in the relation with attributes Ri (Sec. 7.2), and its four features"""
    n = data.distinct(Ri)
    length = min(1.0, 0.5 * (1 / popcount(X) + popcount(Y) / max(1, popcount(Ri) - 2)))
    value = 1 / max(1, data.maxlen(X) - 7)
    position = 0.5 * (1 / (between(X, Ri) + 1) + 1 / (between(Y, Ri) + 1))
    duplication = 0.5 * (2 - data.distinct(X) / n - data.distinct(Y) / n)
    return (length + value + position + duplication) / 4, (length, value, position, duplication)


def normalize(nattr, fds, pk, data, fks=()):
    """the automatic Normalize on a relation of nattr attributes: fds the mined minimal FDs as (lhs mask, rhs index),
    pk the mask of the primary key (0: none), fks foreign keys of the input (only the test sets them); returns the
    relations (masks) and the splits (X, Y, score, features)"""
    F = [(l, 1 << r) for l, r in fds]
    lhss = sorted({l for l, _ in fds}, key=lambda x: (popcount(x), members(x)))
    cl = closures(lhss, F)
    todo, done, splits = [(mask(range(nattr)), pk, list(fks))], [], []
    while todo:
        Ri, pki, fks = todo.pop(0)
        keys = [X for X in lhss if X & ~Ri == 0 and cl[X] & Ri == Ri] + ([pki] if pki else [])
        viol = []
        for X in lhss:
            if X & ~Ri:
                continue
            Y = cl[X] & Ri & ~X
            if not Y or X & data.null:
                continue
            if any(k & ~X == 0 for k in keys):
                continue
            if pki:
                Y &= ~pki
            if not Y or any(fk & Y and fk & ~(X | Y) for fk in fks):
                continue
            s, feats = score(X, Y, Ri, data)
            viol.append((-s, popcount(X), members(X), members(Y), X, Y, feats))
        if not viol:
            done.append(Ri)
            continue
        _, _, _, _, X, Y, feats = min(viol)
        R1, R2 = (Ri & ~Y) | X, X | Y
        fk1 = [fk for fk in fks if fk & ~R1 == 0] + [X]
        fk2 = [fk for fk in fks if fk & ~R1 and fk & ~R2 == 0]
        splits.append((X, Y, sum(feats) / 4, feats))
        todo += [(R1, pki, fk1), (R2, X, fk2)]
    return done, splits


def prior(b, data):
    """Normalize's score of the extended FD X -> cl(X) \\ X \\ primary key of every candidate's left-hand side X, on the
    input relation (item 74 (b)); candidates of one left-hand side share it"""
    nattr = len(b["R"])
    fds = mined(b)
    F = [(l, 1 << r) for l, r in fds]
    pk = mask(b["sigma0"][0][0]) if b["sigma0"] else 0
    Rm = mask(range(nattr))
    lhs = {p: mask(p[0]) for p in b["P"]}
    cl = closures(sorted(set(lhs.values())), F)
    out = {}
    for p, X in lhs.items():
        out[p] = score(X, cl[X] & ~X & ~pk, Rm, data)[0]
    return out


def mined(b):
    """every mined minimal FD of the relation file, as (lhs mask, rhs); the candidates and implied0 are among them"""
    import auto_common as AC
    idx = {a: i for i, a in enumerate(b["names"])}
    out = sorted({(mask(idx[x] for x in f["lhs"]), idx[f["rhs"]]) for f in AC.raw(b["name"])["fds"]})
    have = set(out)
    assert all((mask(l), next(iter(r))) in have for l, r in list(b["P"]) + list(b["implied0"])), b["name"]
    return out


PRIOR = os.path.join(HERE, "v6f_fresh3_extra", "normalize", "prior")


def write_priors(a):
    """the score of every candidate (item 74 (b)) by its fd_id, one file per relation; it reads no truth"""
    import auto_common as AC
    os.makedirs(PRIOR, exist_ok=True)
    for ds in (a.datasets.split(",") if a.datasets else AC.FRESH):
        b = AC.load(ds)
        data, names = Data.load(ds)
        assert names == b["names"], (ds, names, b["names"])
        pi = prior(b, data)
        out = {AC.fd_id(ds, *b["fdnames"][p]): round(v, 6) for p, v in pi.items()}
        with open(os.path.join(PRIOR, ds + ".json"), "w", encoding="utf-8") as fh:
            json.dump(out, fh, sort_keys=True)
        vs = sorted(out.values())
        print(f"{ds:34s} candidates {len(vs)}, score median {vs[len(vs) // 2]:.3f}, at least 1/2: {sum(v >= 0.5 for v in vs)}", flush=True)


def read_prior(b):
    import auto_common as AC
    with open(os.path.join(PRIOR, b["name"] + ".json"), encoding="utf-8") as fh:
        s = json.load(fh)
    return {p: s[AC.fd_id(b["name"], *b["fdnames"][p])] for p in b["P"]}


def run(a):
    import auto_common as AC
    import auto_confirm as C
    T = AC.truth_mode()
    done = set()
    if os.path.exists(a.out):
        done = {json.loads(x)["dataset"] for x in open(a.out, encoding="utf-8") if x.strip()}
    dss = [d for d in (a.datasets.split(",") if a.datasets else AC.FRESH) if d not in done]
    with open(a.out, "a", encoding="utf-8") as fo:
        for ds in dss:
            t0 = time.time()
            b = AC.load(ds)
            data, names = Data.load(ds)
            assert names == b["names"], (ds, names, b["names"])
            pk = mask(b["sigma0"][0][0]) if b["sigma0"] else 0
            D, splits = normalize(len(b["R"]), mined(b), pk, data)
            used = [(frozenset(members(X)), frozenset(members(Y))) for X, Y, _, _ in splits]
            pred = C.concluded(b, used)
            r = {"variant": "normalize", "dataset": ds, "truth": T, "oracle": AC.oracle_mode(), "batch": os.environ.get("CONFIRM_BATCH", "1"),
                 "candidates": len(b["P"]), "true": len(b["truth"]), "primary_key": [names[i] for i in members(pk)],
                 "design": [[names[i] for i in members(m)] for m in D],
                 "splits": [{"lhs": [names[i] for i in members(X)], "rhs": [names[i] for i in members(Y)], "score": round(s, 4),
                             "features": [round(f, 4) for f in feats]} for X, Y, s, feats in splits],
                 **C.evaluate(b, [set(members(m)) for m in D], pred)}
            r["secs"] = round(time.time() - t0, 1)
            fo.write(json.dumps(r) + "\n")
            fo.flush()
            print(f"{ds:34s} tables {r['tables']:2d} lossless {r['gold_lossless']!s:5s} good {r['gold_good']!s:5s} splits {len(splits)} {r['secs']}s", flush=True)


def test():
    # the running example of the paper (Tab. 2): First, Last, Postcode, City, Mayor with Postcode -> City, Mayor
    # and City -> Mayor; the expected design is R1(First, Last, Postcode) and R2(Postcode, City, Mayor)
    rows = [("THOMAS", "MILLER", "14482", "POTSDAM", "JAKOBS"), ("SARAH", "MILLER", "14482", "POTSDAM", "JAKOBS"),
            ("PETER", "SMITH", "60329", "FRANKFURT", "FELDMANN"), ("JASMINE", "CONE", "01069", "DRESDEN", "OROSZ"),
            ("MIKE", "CONE", "14482", "POTSDAM", "JAKOBS"), ("THOMAS", "MOORE", "60329", "FRANKFURT", "FELDMANN")]

    def data_of(rows):
        cols = list(zip(*rows))
        M, lens = [], []
        for c in cols:
            u = {}
            M.append([u.setdefault(v, len(u)) for v in c])
            lens.append(np.array([len(v) for v in u], dtype=np.int32))
        return Data(np.array(M).T, lens, [any(v == "?" for v in c) for c in cols])

    import itertools

    def minimal_fds(rows):
        n = len(rows[0])
        holds = lambda X, a: len({tuple(r[i] for i in X) for r in rows}) == len({tuple(r[i] for i in X) + (r[a],) for r in rows})
        out = []
        for a in range(n):
            for k in range(1, n):
                for X in itertools.combinations([i for i in range(n) if i != a], k):
                    if holds(X, a) and not any(mask(Z) & ~mask(X) == 0 for Z, b_ in out if b_ == a):
                        out.append((X, a))
        return [(mask(X), a) for X, a in out]

    d = data_of(rows)
    D, splits = normalize(5, minimal_fds(rows), mask([0, 1]), d)
    got = sorted(sorted(members(m)) for m in D)
    assert got == [[0, 1, 2], [2, 3, 4]], (got, splits)
    assert members(splits[0][0]) == [2] and members(splits[0][1]) == [3, 4], splits
    # a value '?' in the left-hand side: Postcode holds '?', so no split has Postcode in its left-hand side
    rows_n = [r if i != 3 else r[:2] + ("?",) + r[3:] for i, r in enumerate(rows)]
    D, splits = normalize(5, minimal_fds(rows_n), mask([0, 1]), data_of(rows_n))
    assert splits and all(not X >> 2 & 1 for X, _, _, _ in splits), splits
    # the primary key leaves Y: with key {First, Last, Postcode}, no split moves Postcode
    D, splits = normalize(5, minimal_fds(rows), mask([0, 1, 2]), d)
    assert splits and all(not Y >> 2 & 1 for _, Y, _, _ in splits), splits
    # a foreign key {Last, City} that a split would break: Postcode -> City, Mayor and Mayor -> Postcode, City move City
    # away from Last, so the split is on City -> Postcode, Mayor
    D, splits = normalize(5, minimal_fds(rows), mask([0, 1]), d, fks=[mask([1, 3])])
    assert members(splits[0][0]) == [3] and members(splits[0][1]) == [2, 4], splits
    print("normalize test: the example of the paper and the three skips of Algorithm 4 pass")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "prior", "test"))
    ap.add_argument("--out")
    ap.add_argument("--datasets")
    a = ap.parse_args()
    {"run": run, "prior": write_priors, "test": lambda a: test()}[a.cmd](a)
