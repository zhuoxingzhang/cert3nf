"""
Design note item 75: a designer who errs at the rates of the practitioners in the study, eps 0.10 and 0.15, counted as
paper_tables_v6f.py counts the rows of Tab. tol (certificates issued within 100 answers, and the wrong ones among them).
  (a) the rows of Tab. tol for eps 0.10 and 0.15, trusting and careful, development (23 + 12 relations) and confirmatory
      (23), each truth, three seeds; budget 1000 in the comment
  (b) pooled over all relations and both truths: certificates, wrong ones and correct ones, per eps and mode, with the
      rows of 0.02 and 0.05 of the paper for comparison
  (c) the three relations of the study (fec-cand, syn-claims, tpcc-customer) in the careful mode: certified within 100
      answers and wrong, of nine runs per truth, against the practitioners of Tab. human
Usage (in confirm/): python scripts/err75_report.py
"""
import contextlib, io, os, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
with contextlib.redirect_stdout(io.StringIO()):
    import paper_tables_v6f as P          # the paper's loaders and the rows of Tab. tol for 0.02 and 0.05

C, MAIN, TRUTHS = P.C, P.MAIN, P.TRUTHS
PARTS = {"dev": (P.DEV, f"v6f_runs/err75_{C}_dev_{{}}.jsonl"), "b2": (P.B2, f"v6f_runs/err75_{C}_b2_{{}}.jsonl"),
         "b3": (P.B3, "v6f_fresh3_extra/err75/err_b3_{}.jsonl")}
HUMAN = ["fresh3_fec_candidate", "fresh3_synthea_claims", "fresh3_tpcc_customer"]
assert all(d in P.B3 for d in HUMAN)

E = {}
for part, (ds, path) in PARTS.items():
    for T in TRUTHS:
        rs = [r for r in P.rows(path.format(T)) if r["variant"] == MAIN]
        key = Counter((r["dataset"], r["designer_err"], bool(r.get("careful")), r["seed"]) for r in rs)
        dup = [k for k, n in key.items() if n > 1]
        want = {(d, e, c, s) for d in ds for e in (0.10, 0.15) for c in (False, True) for s in (0, 1, 2)}
        print(f"% {part} {T}: {len(rs)} rows, {len(dup)} duplicate keys, missing {len(want - set(key))}, extra {len(set(key) - want)}")
        E[part, T] = rs


def count(rs):
    c = [r for r in rs if r.get("certified")]
    c1 = [r for r in c if r["questions"] <= 100]
    return len(rs), len(c), sum(bool(r.get("wrong_cert")) for r in c), len(c1), sum(bool(r.get("wrong_cert")) for r in c1)


def sel(rs, eps, care, ds=None):
    return [r for r in rs if r["designer_err"] == eps and bool(r.get("careful")) == care and (ds is None or r["dataset"] in ds)]


print("%% (a) rows of Tab. tol: development (dev + b2) full, sure; confirmatory full, sure; within 100 answers")
pooled = {}
for eps in (0.10, 0.15):
    for care in (False, True):
        cells, note, tot = [], [], [0, 0, 0, 0, 0]
        for T in TRUTHS:
            n, c, w, c1, w1 = count(sel(E["dev", T] + E["b2", T], eps, care))
            cells.append(f"{c1} & {w1}")
            note.append(f"dev {T} {n} runs, budget 1000 {c} cert {w} wrong")
            tot = [a + b for a, b in zip(tot, (n, c, w, c1, w1))]
        for T in TRUTHS:
            n, c, w, c1, w1 = count(sel(E["b3", T], eps, care))
            cells.append(f"{c1} & {w1}")
            note.append(f"b3 {T} {n} runs, budget 1000 {c} cert {w} wrong")
            tot = [a + b for a, b in zip(tot, (n, c, w, c1, w1))]
        pooled[eps, care] = tot
        cells = [cells[0], cells[1], cells[2], cells[3]]
        print(f"{eps:.2f} & {'careful' if care else 'trusting'} & " + " & ".join(cells) + r"\\  % " + "; ".join(note))

print("%% (b) pooled over the 58 relations, both truths, three seeds: runs, within 100: certificates, wrong (share), correct; budget 1000: certificates, wrong (share)")
for eps in (0.02, 0.05):
    for care in (False, True):
        rs = []
        for T in TRUTHS:
            rs += P.D[T]["err3"] + P.D[T]["err1"]
        n, c, w, c1, w1 = count([r for r in sel(rs, eps, care) if r["variant"] == MAIN])
        pooled[eps, care] = [n, c, w, c1, w1]
for (eps, care), (n, c, w, c1, w1) in sorted(pooled.items()):
    print(f"% eps {eps:.2f} {'careful ' if care else 'trusting'}: {n} runs; within 100: {c1} cert, {w1} wrong ({w1 / max(c1, 1):.3f}), {c1 - w1} correct; "
          f"budget 1000: {c} cert, {w} wrong ({w / max(c, 1):.3f}), {c - w} correct")

print("%% (c) the three relations of the study, careful mode, within 100 answers, nine runs per truth (practitioners: P 6 of 9 certified, 1 wrong; U 4 of 9, 1 wrong)")
for eps in (0.10, 0.15):
    for T in TRUTHS:
        rs = sel(E["b3", T], eps, True, HUMAN)
        n, c, w, c1, w1 = count(rs)
        per = {P.name(d): sum(1 for r in rs if r["dataset"] == d and r.get("certified") and r["questions"] <= 100) for d in HUMAN}
        print(f"% eps {eps:.2f} {T}: {n} runs, certified within 100 {c1}, wrong {w1}, per relation {per}; budget 1000 {c} cert, {w} wrong")
    for T in TRUTHS:
        rs = sel(E["b3", T], eps, False, HUMAN)
        n, c, w, c1, w1 = count(rs)
        print(f"%   trusting {T}: {n} runs, certified within 100 {c1}, wrong {w1}")
