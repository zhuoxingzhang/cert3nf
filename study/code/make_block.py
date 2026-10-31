"""
The fixed blocks of the human-designer study (study/README.md): per relation 18 questions, 6 of each
type and half of them true, plus 12 filler questions that the interface shows between two answers to the same
question.  Every question holds on the data, is not implied by the declared key, and has the same truth
under the full and the sure documented truth (true under sure, hence under full; false under full, hence under sure)
and under the full truth plus the FDs of supplement.json that the hand check found true but undocumented.

  cand  a candidate Z -> A, a minimal FD on the data
  max   false: M -> A for a maximal set M of the full truth that holds on the data (a held set);
        true:  M + B -> A for a maximal set M and an attribute B with which it determines A under the sure truth
  qx    Z -> A with 3 to 5 attributes in Z that is not minimal on the data, as QuickXplain asks inside a held set

Only questions with a(q) <= 6 are taken (at most five attributes listed besides A; the live questions have a median
a(q) of 2 to 4).  Within each (type, truth), 3 questions are stratified by a(q), in a random order seeded by
SHA-256(relation, type, truth), and 2 fillers are taken from the rest in the same way.  Writes block_<ds>.json and the
review file block_<ds>.md (truth, derivation from the documented FDs, form shown) for the check by hand.
Usage:  python study/code/make_block.py   (writes into study/blocks; needs STUDY_SOURCE, see common.py)
"""
import hashlib, itertools, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["STUDY_BUILD"] = "1"      # the method in STUDY_SOURCE, with all its inputs
import common as K

PER, FILL, AQ_MAX = 3, 2, 6


def rng_for(*tag):
    return np.random.default_rng(int.from_bytes(hashlib.sha256(repr(tag).encode()).digest()[:8], "big"))


def spread(pool, rel, k, tag):
    """k questions with a(q) <= AQ_MAX, stratified by a(q): k evenly spaced values among the distinct a(q) of the
    pool (repeated when there are fewer), a random question of each value (the nearest value once one runs out);
    the rest of the pool in a seeded random order"""
    rng = rng_for(*tag)
    left = [pool[i] for i in rng.permutation(len(pool)) if rel.show(*pool[i])[3] <= AQ_MAX]
    aq = {q: rel.show(*q)[3] for q in left}
    vals = sorted(set(aq.values()))
    if not vals:
        return [], []
    slots = ([vals[round(j * (len(vals) - 1) / (k - 1))] for j in range(k)] if len(vals) >= k and k > 1
             else sorted(vals[j % len(vals)] for j in range(k)))
    chosen = []
    for v in slots:
        if not left:
            break
        q = min(left, key=lambda q: abs(aq[q] - v))      # the first in the random order among the nearest value
        chosen.append(q)
        left.remove(q)
    return chosen, left


def pools(rel):
    n, full = rel.n, rel.full
    agree = lambda z, a: rel.truth(z, a, "full") == rel.truth(z, a, "sure") == rel.truth(z, a, "supp")
    ok = lambda z, a: rel.holds(z, a) and not rel.implied0(z, a) and agree(z, a)
    P = {"cand": {True: [], False: []}, "max": {True: [], False: []}, "qx": {True: [], False: []}}
    for z, a in rel.P:
        if ok(z, a):
            P["cand"][rel.truth(z, a, "sure")].append((z, a))
    from price import maxsets
    seen = set()
    for i in range(n):
        a = 1 << i
        for t in ("full", "sure"):
            for M in maxsets(rel.gold[t], a, full):
                if t == "full" and ok(M, a) and (M, a) not in seen:
                    seen.add((M, a))
                    P["max"][False].append((M, a))
                for j in range(n):
                    z = M | 1 << j
                    if z != M and not z & a and ok(z, a) and rel.truth(z, a, "sure") and (z, a) not in seen:
                        seen.add((z, a))
                        P["max"][True].append((z, a))
    for k in range(3, min(5, n - 2) + 1):
        for c in itertools.combinations(range(n), k):
            z = K.mask(c)
            for i in range(n):
                a = 1 << i
                if z & a or (z, a) in seen or rel.minimal(z, a) or not ok(z, a):
                    continue
                P["qx"][rel.truth(z, a, "sure")].append((z, a))
    return P


def derivation(rel, z, a, t):
    """a minimal subset of the documented FDs (truth t, with sigma0) whose closure of Z contains A"""
    F = list(dict.fromkeys(rel.gold[t]))
    for f in list(F):
        G = [g for g in F if g != f]
        if K.closure(z, G) & a:
            F = G
    nm = lambda m: ",".join(rel.names[i] for i in K.members(m, rel.n))
    return "; ".join(f"{nm(l)} -> {nm(r)}" for l, r in F)


def record(rel, qid, typ, z, a):
    form, listed, rhs, aq, text = rel.show(z, a)
    nm = lambda m: [rel.names[i] for i in K.members(m, rel.n)]
    return {"id": qid, "type": typ, "lhs": nm(z), "rhs": rhs, "form": form, "listed": listed, "a_q": aq,
            "text": text, "truth_full": rel.truth(z, a, "full"), "truth_sure": rel.truth(z, a, "sure"),
            "truth_supp": rel.truth(z, a, "supp"),
            "minimal_on_data": rel.minimal(z, a)}


def build(ds):
    rel = K.Rel(ds)
    P = pools(rel)
    block, fill, short = [], [], {}
    for typ in ("cand", "max", "qx"):
        for tv in (True, False):
            pool = P[typ][tv]
            chosen, rest = spread(pool, rel, PER, (ds, typ, tv))
            extra, _ = spread(rest, rel, FILL, (ds, typ, tv, "filler"))
            if len(chosen) < PER or len(extra) < FILL:
                short[f"{typ}/{tv}"] = len(pool)
            block += [(typ, z, a) for z, a in chosen]
            fill += [(typ, z, a) for z, a in extra]
    out = {"dataset": ds, "attributes": rel.names, "generator": K.md5(os.path.abspath(__file__)),
           "data_md5": K.md5(os.path.join(os.path.dirname(K.SOURCE), "e3", "data", ds + ".json")),
           "supplement_md5": K.md5(os.path.join(K.BLOCKS, "supplement.json")), "supplement": rel.supplement,
           "pool_sizes": {f"{t}/{v}": len(P[t][v]) for t in P for v in P[t]}, "short": short,
           "questions": [record(rel, f"b{j + 1:02d}", t, z, a) for j, (t, z, a) in enumerate(block)],
           "fillers": [record(rel, f"f{j + 1:02d}", t, z, a) for j, (t, z, a) in enumerate(fill)]}
    with open(os.path.join(K.BLOCKS, f"block_{ds}.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    lines = [f"# Fixed block of {ds} (check by hand)", "",
             f"Attributes: {', '.join(rel.names)}", f"Pool sizes: {out['pool_sizes']}", ""]
    for part, qs in (("Block", out["questions"]), ("Fillers", out["fillers"])):
        lines += [f"## {part}", ""]
        for q in qs:
            z, a = rel.key(q["lhs"], q["rhs"])
            why = (f"true: {derivation(rel, z, a, 'sure')}" if q["truth_sure"] else
                   "false: closure of the left-hand side under the full truth is "
                   + ",".join(rel.names[i] for i in K.members(K.closure(z, rel.gold["full"]), rel.n)))
            lines += [f"- **{q['id']}** {q['type']}, {'TRUE' if q['truth_sure'] else 'FALSE'}, a(q) = {q['a_q']}, "
                      f"lhs = {{{', '.join(q['lhs'])}}} -> {q['rhs']}", f"  - shown: {q['text']}", f"  - {why}"]
        lines.append("")
    with open(os.path.join(K.BLOCKS, f"block_{ds}.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return out


def main():
    for ds in K.RELATIONS.values():
        o = build(ds)
        types = [(q["type"], q["truth_sure"], q["a_q"]) for q in o["questions"]]
        print(ds, "pools", o["pool_sizes"], "short", o["short"])
        print("  block", types)
        print("  fillers", len(o["fillers"]))


if __name__ == "__main__":
    main()
