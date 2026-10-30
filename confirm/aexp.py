"""
Attribute exploration as a baseline (design note item 44): the input of aexp.c for every relation, its run within a
time limit, and one JSON line per relation; --max asks aexp.c for the largest counterexamples (exploratory).  The
minimal FDs of r are the candidates and the FDs that Sigma0 implies (as v5.run's minfd), Sigma* is what the simulated
designer answers from (auto_common.oracle, CONFIRM_ORACLE=gold).

Usage (in confirm, after gcc -O2 -o aexp aexp.c):
  CONFIRM_ORACLE=gold CONFIRM_BATCH=2 CONFIRM_TRUTH=full python aexp.py --out F [--datasets ...] [--seconds 7200]
"""
import argparse, json, os, subprocess, time
import auto_common as AC


def mask(s):
    return sum(1 << i for i in s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", default=",".join(AC.FRESH))
    ap.add_argument("--seconds", type=float, default=7200)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max", action="store_true")
    a = ap.parse_args()
    done = set()
    if os.path.exists(a.out):
        done = {json.loads(x)["dataset"] for x in open(a.out, encoding="utf-8") if x.strip()}
    exe = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aexp")
    with open(a.out, "a", encoding="utf-8") as fo:
        for ds in a.datasets.split(","):
            if ds in done:
                continue
            b = AC.load(ds)
            fds = lambda F: [f"{mask(l)} {mask(r)}" for l, r in F]
            lines = [f"{len(b['R'])} {a.seconds}"]
            for F in (b["sigma0"], b["P"] + b["implied0"], AC.oracle(b)):
                lines += [str(len(F))] + fds(F)
            t0 = time.time()
            p = subprocess.run([exe] + (["max"] if a.max else []), input="\n".join(lines) + "\n", capture_output=True,
                               text=True, check=True)
            r = {"dataset": ds, "truth": AC.truth_mode(), "oracle": AC.oracle_mode(), "attributes": len(b["R"]),
                 "counterexample": "max" if a.max else "min",
                 "data_fds": len(b["P"]) + len(b["implied0"]), **json.loads(p.stdout), "wall": round(time.time() - t0, 1)}
            fo.write(json.dumps(r) + "\n")
            fo.flush()
            print(f"{ds:22s} {r['truth']} finished {r['finished']} yes {r['yes']} no {r['no']} unit {r['unit']} "
                  f"visited {r['visited']} equivalent {r['equivalent']} {r['secs']}s", flush=True)


if __name__ == "__main__":
    main()
