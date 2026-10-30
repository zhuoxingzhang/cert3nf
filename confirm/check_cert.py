"""An independent checker of a certificate of Cert3NF (design note item 32, output field "certificate" of v5.py).

A certificate is a set of FDs answered yes and a set of FDs answered no.  With H = Sigma0 + yes, it proves
H+ = Sigma*+ when every maximal set M of H for an attribute A that holds on the data (Thm. price (a): M contains the
left-hand side of a candidate X -> A, a minimal FD mined on the data that Sigma0 does not imply) is refuted by a no
answer Z -> B, which refutes M -> A when M lies within the closure of Z under H and H + M -> A would imply Z -> B
(Thm. certificate).  Then the 3NF synthesis of H is good for the true FDs.  The weaker condition that every candidate
is implied by H or refuted (the "no open candidate" shortcut of the first draft) is reported as well but does not
certify: a true FD that is not minimal on the data can hide behind a refuted candidate (design note item 32).
The checker uses closures and maximal sets only; it does not run the pipeline.  With --truth it also checks every
premise against the ground truth of CONFIRM_TRUTH: a certificate whose premises are right is right.

Usage (in confirm):  CONFIRM_TRUTH=full python check_cert.py --results v5_full.jsonl [--variant v5] [--truth]
"""
import argparse, json, os, sys
from collections import defaultdict

import auto_common as AC
from price import closure, maxsets


def check(b, cert, truth=False):
    names = b["names"]
    n = len(names)
    full = (1 << n) - 1
    idx = {a: i for i, a in enumerate(names)}
    mask = lambda xs: sum(1 << idx[a] for a in xs)             # attribute names (the certificate)
    im = lambda xs: sum(1 << i for i in xs)                    # attribute indices (the relation)
    S0 = [(im(l), im(r)) for l, r in b["sigma0"]]
    H = S0 + [(mask(l), 1 << idx[a]) for l, a in cert["yes"]]
    NEG = [(mask(l), 1 << idx[a]) for l, a in cert["no"]]
    cl = {z: closure(z, H) for z, _ in NEG}
    refuted = lambda x, a: any(x & ~cl[z] == 0 and closure(cl[z] | a, H) & bz for z, bz in NEG)
    by_a, open_ = defaultdict(list), []
    for l, r in b["P"]:
        x, a = im(l), im(r)
        by_a[a].append(x)
        if closure(x, H) & a or refuted(x, a):
            continue
        open_.append(([names[i] for i in sorted(l)], names[next(iter(r))]))
    nmax, unref = 0, []
    for a, xs in by_a.items():
        for M in maxsets(H, a, full):
            if not any(x & ~M == 0 for x in xs):            # M -> A fails on the data: outside the certificate
                continue
            nmax += 1
            if not refuted(M, a):
                unref.append(([names[i] for i in range(n) if M >> i & 1], names[a.bit_length() - 1]))
    out = {"candidates": len(b["P"]), "yes": len(cert["yes"]), "no": len(cert["no"]), "open": len(open_),
           "maxsets": nmax, "unrefuted": len(unref), "certified": not unref,
           "open_examples": open_[:5], "unrefuted_examples": unref[:5]}
    if truth:
        reach = [(im(l), im(r)) for l, r in AC.oracle(b)]       # what the designer answered from (CONFIRM_ORACLE)
        out["yes_wrong"] = sum(1 for z, a in H[len(S0):] if not closure(z, reach) & a)
        out["no_wrong"] = sum(1 for z, a in NEG if closure(z, reach) & a)
        out["sound"] = out["yes_wrong"] == 0 and out["no_wrong"] == 0
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--variant", default=None)
    ap.add_argument("--truth", action="store_true")
    a = ap.parse_args()
    bad = 0
    for x in open(a.results, encoding="utf-8"):
        if not x.strip():
            continue
        r = json.loads(x)
        if a.variant and r["variant"] != a.variant or "certificate" not in r:
            continue
        if r["truth"] != AC.truth_mode():
            print(f"skip {r['variant']} {r['dataset']}: truth {r['truth']} is not CONFIRM_TRUTH={AC.truth_mode()}")
            continue
        b = AC.load(r["dataset"])
        c = check(b, r["certificate"], a.truth)
        agree = c["certified"] == r["certified"]
        bad += not agree or (a.truth and not c.get("sound", True))
        print(f"{r['variant']:4s} {r['dataset']:28s} run says certified {r['certified']!s:5s}; checker: maximal sets"
              f" {c['maxsets']:5d} unrefuted {c['unrefuted']:5d}, candidates open {c['open']:5d} of {c['candidates']:6d}"
              f" (yes {c['yes']}, no {c['no']}) -> certified {c['certified']!s:5s}"
              + (f", premises wrong yes {c['yes_wrong']} no {c['no_wrong']}" if a.truth else "")
              + ("" if agree else "   DISAGREES"), flush=True)
    print("disagreements or unsound:", bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
