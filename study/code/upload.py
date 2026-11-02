"""
A table that a visitor uploads on the start page (server.py, POST /upload), designed like a try: the method in the
trusting mode with the statistics advisor, since there are no LLM answers for an unknown table and no documented FDs.

  check(name, text, key)  parses the CSV (a header row; comma, semicolon, tab or bar), drops duplicate rows, checks the
                          limits and that no two rows agree on the key columns the visitor ticked; returns the instance
  build(folder)           run in a process of its own (python upload.py <folder>): drops the constant columns, mines all
                          minimal FDs (e3/fdmine.py, exact), refuses more than MAX_CANDIDATES candidates, computes the
                          features of every candidate as e3/build.py does,
                          and pickles (Rel, b, advisor) in the shape of common.prebuilt into <folder>/block.pkl: sigma0
                          from the key, no documented FDs, the learned prior with the weights of make_upload_prior.py
  load(folder)            a fresh copy of that triple for one session

Every question the method asks holds on the uploaded rows, as for the study's relations.  The file stays in the
folder of its session on the instance's disk and server.py deletes it after KEEP_HOURS.
"""
import csv, io, json, os, pickle, random, re, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as K

MAX_COLS, MAX_ROWS, MAX_BYTES = 25, 50000, 10 * 2 ** 20
MAX_CANDIDATES = 5000                # the advisor keeps about 3 KB per candidate in the server's memory
SAMPLE = 10


class UploadRel(K.Rel):
    """K.Rel of an uploaded table: no documented FDs, so a question has no truth to log"""

    def __init__(self, names, sig0, minfd, sample, rows):
        self.ds, self.names, self.n = "upload", names, len(names)
        self.full = (1 << self.n) - 1
        self.sig0, self.supplement = sig0, []
        self.gold = {t: sig0 for t in ("full", "sure", "supp")}
        self.minfd, self.sample, self.rows = minfd, sample, rows

    def truth(self, z, a, t):
        return None


def check(name, text, key):
    """the instance {name, names, rows, key} of an uploaded CSV, or ValueError with a message for the visitor"""
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError(f"The file is larger than {MAX_BYTES // 2 ** 20} MB.")
    text = text.lstrip("﻿")
    head = text[:20000]
    try:
        dialect = csv.Sniffer().sniff(head.splitlines()[0] if head else "", delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 3:
        raise ValueError("The file needs a header row and at least two records.")
    if rows[0] and not rows[0][-1].strip() and all(len(r) == len(rows[0]) and not r[-1].strip() for r in rows):
        rows = [r[:-1] for r in rows]                   # a delimiter at the end of every line
    names = [c.strip() for c in rows[0]]
    if len(names) < 2 or len(names) > MAX_COLS:
        raise ValueError(f"The table needs between 2 and {MAX_COLS} columns; this one has {len(names)}.")
    if any(not x for x in names) or len(set(names)) < len(names):
        raise ValueError("Every column needs a name of its own in the header row.")
    bad = next((i for i, r in enumerate(rows[1:], 2) if len(r) != len(names)), None)
    if bad is not None:
        k = len(rows[bad - 1])
        raise ValueError(f"Line {bad} has {k} value{'' if k == 1 else 's'}, but the header names {len(names)} columns.")
    data = list(dict.fromkeys(tuple(c.strip() for c in r) for r in rows[1:]))      # a relation is a set of rows
    if len(data) < 2:
        raise ValueError("The table needs at least two different records.")
    if len(data) > MAX_ROWS:
        raise ValueError(f"The table has {len(data):,} distinct records; the demo takes up to {MAX_ROWS:,}.")
    key = [k for k in names if k in set(key or ())]
    if key:
        ix = [names.index(k) for k in key]
        if len({tuple(r[i] for i in ix) for r in data}) < len(data):
            raise ValueError("Two records agree on the key " + ", ".join(key) + ", so it is not a key of this table.")
    return {"name": name, "names": names, "rows": [list(r) for r in data], "key": key}


def sqltype(values):
    vs = [v for v in values if v != ""]
    if any(re.fullmatch(r"0\d+", v) for v in vs):         # a code with leading zeros (zip, phone) stays text
        return "TEXT"
    if vs and all(re.fullmatch(r"[+-]?\d{1,18}", v) for v in vs):
        return "INTEGER"
    if vs and all(re.fullmatch(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?", v) for v in vs):
        return "NUMERIC"
    if vs and all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) for v in vs):
        return "DATE"
    return "TEXT"


def tokens(name):                                    # as e3/build.py
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    return [t.lower() for t in re.split(r"[_\s\d#()+\-.]+", s) if t]


def build(folder):
    sys.path.insert(0, os.path.join(K.REPO, "e3"))
    K.setenv("full")
    import fdmine
    import bench
    import estimators as EST
    import v5
    S = bench.S
    with open(os.path.join(folder, "data.json"), encoding="utf-8") as fh:
        d = json.load(fh)
    rows, n = d["rows"], len(d["rows"])
    cols = list(zip(*rows))
    keep = [j for j, c in enumerate(cols) if len(set(c)) > 1]
    dropped = [d["names"][j] for j in range(len(cols)) if j not in keep]
    names = [d["names"][j] for j in keep]
    if len(names) < 2:
        raise ValueError("Fewer than two columns have more than one value.")
    M, card = fdmine.encode([cols[j] for j in keep])
    miner = fdmine.Miner(M, card)
    fds = miner.run()
    idx = {a: i for i, a in enumerate(names)}
    km = [idx[a] for a in d["key"] if a in idx]
    sigma0 = [S.fd(km, x) for x in range(len(names)) if x not in km] if km else []
    with open(os.path.join(K.PREBUILT, "upload_prior.json"), encoding="utf-8") as fh:
        pr = json.load(fh)
    w = np.array(pr["weights"])
    P, X, fdn, implied0, distinct = [], {}, {}, [], {}
    cand = []
    for z, a in sorted(fds, key=lambda f: (bin(f[0]).count("1"), f[0], f[1])):
        p = S.fd(fdmine.bits(z), a)
        if sigma0 and S.implies(sigma0, p):
            implied0.append(p)
        else:
            cand.append((z, a, p))
    if len(cand) > MAX_CANDIDATES:
        raise ValueError(f"The records suggest {len(cand):,} candidate rules, more than the {MAX_CANDIDATES:,} the demo "
                         "can ask about. A table with fewer columns, or with more records, has fewer.")
    for z, a, p in cand:
        if z not in distinct:
            distinct[z] = len(np.unique(miner.labels(fdmine.bits(z))))
        lhs = [names[i] for i in fdmine.bits(z)]
        f = {"lhs_size": len(lhs), "redundancy": n - distinct[z], "lhs_unique": distinct[z] == n,
             "distinct_lhs": distinct[z], "distinct_rhs": card[a],
             "lhs_tokens": [tokens(x) for x in lhs], "rhs_tokens": tokens(names[a])}
        P.append(p)
        X[p] = bench.features(f, n) + EST.name_features(f)
        fdn[p] = (lhs, names[a])
    # the features only give the prior: b keeps none of them (X is empty), the advisor keeps about 3 KB per candidate
    pi = bench.clip({p: float(1 / (1 + np.exp(-np.dot(w, [X[p][c] for c in pr["columns"]])))) for p in P},
                    lo=pr["rho_min"])
    b = {"name": os.path.basename(folder), "R": list(range(len(names))), "names": names, "sigma0": sigma0,
         "key": d["key"] or None, "gold": [], "P": P, "X": {}, "truth": [], "true_out_of_scope": 0, "rows": n,
         "fdnames": fdn, "implied0": implied0}
    minfd = {}
    for l, r in P + implied0:
        minfd.setdefault(K.mask(r), []).append(K.mask(l))
    sample = [[r[j] for j in keep] for r in random.Random(b["name"]).sample(rows, min(SAMPLE, n))]
    rel = UploadRel(names, [(K.mask(l), K.mask(r)) for l, r in sigma0], minfd, sample, n)
    info = {"title": d["name"], "dropped": dropped, "key": [a for a in d["key"] if a in idx],
            "types": {a: sqltype(cols[j]) for a, j in zip(names, keep)}, "candidates": len(P)}
    with open(os.path.join(folder, "block.tmp"), "wb") as fh:
        pickle.dump((rel, b, v5.Advisor(P, pi, None, True)), fh)
    with open(os.path.join(folder, "info.json"), "w", encoding="utf-8") as fh:
        json.dump(info, fh)
    os.replace(os.path.join(folder, "block.tmp"), os.path.join(folder, "block.pkl"))


def load(folder):
    with open(os.path.join(folder, "block.pkl"), "rb") as fh:
        rel, b, adv = pickle.load(fh)
    with open(os.path.join(folder, "info.json"), encoding="utf-8") as fh:
        return rel, b, adv, json.load(fh)


if __name__ == "__main__":
    import upload                     # pickle UploadRel as upload.UploadRel, not __main__.UploadRel
    try:
        upload.build(sys.argv[1])
    except ValueError as e:
        with open(os.path.join(sys.argv[1], "error.txt"), "w", encoding="utf-8") as fh:
            fh.write(str(e))
        sys.exit(1)
