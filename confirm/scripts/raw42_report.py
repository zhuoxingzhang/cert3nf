"""
Design note item 42 (a): the v5 family on the four relations rebuilt without the repair (v5_raw/) against the same
relations repaired (v5_fresh2/, v5_unb/), per truth.  Per run: certified, answers, good for the documented truth
(gold_good), and for a certificate whether its design misses a documented FD; the counts per variant at the end.
Usage (in confirm, on a copy whose e3/data was built with FRESH_NO_REPAIR=1):  python scripts/raw42_report.py
"""
import json, os, sys

DS = ["fresh_chembl", "fresh_fhrs", "fresh_ghcn", "fresh_simplewiki"]


def rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def table(new, old, title):
    print(f"-- {title}")
    print(f"{'relation':18s} {'variant':5s} {'repaired':>22s} {'unrepaired':>22s}")
    cnt = {}
    for ds in DS:
        for v in ("v5", "v5s", "v5n", "v5u"):
            a = [r for r in old if r["dataset"] == ds and r["variant"] == v]
            b = [r for r in new if r["dataset"] == ds and r["variant"] == v]
            if not b:
                continue
            f = lambda r: (f"{'cert' if r['certified'] else '----'} q{r['questions']:4d} "
                           f"{'good' if r.get('gold_good') else 'BAD '}") if r else "-"
            print(f"{ds:18s} {v:5s} {f(a[0] if a else None):>22s} {f(b[0]):>22s}")
            c = cnt.setdefault(v, {"cert": 0, "wrong": 0, "cert_old": 0, "wrong_old": 0})
            c["cert"] += b[0]["certified"]
            c["wrong"] += b[0]["certified"] and not b[0].get("gold_good")
            if a:
                c["cert_old"] += a[0]["certified"]
                c["wrong_old"] += a[0]["certified"] and not a[0].get("gold_good")
    for v, c in cnt.items():
        print(f"   {v:5s} certified {c['cert_old']} -> {c['cert']}, of which not good for the documented truth "
              f"{c['wrong_old']} -> {c['wrong']}")


def main():
    for ds in DS:
        p = os.path.join("..", "e3", "data", ds + ".json")
        d = json.load(open(p, encoding="utf-8"))
        c = d["instance"].get("cleaning", {})
        print(f"{ds:18s} rows {d['instance']['rows']} repaired_for {c.get('repaired_for')} "
              f"candidates mined {d['mined']['count']} truth {d['truth_counts']}")
    for T in ("full", "sure"):
        print(f"== truth {T}")
        table(rows(f"v5_raw/v5_{T}.jsonl"), rows(f"v5_fresh2/v5_{T}.jsonl"), "budget 100")
        table(rows(f"v5_raw/v5_unb_{T}.jsonl"), rows(f"v5_unb/v5_{T}.jsonl"), "budget 1000")
        for f in ("v5", "v5_unb"):
            p = f"v5_raw/check_{f}_{T}.txt"
            if os.path.exists(p):
                print(f"   check_cert {f}: {open(p, encoding='utf-8').read().strip().splitlines()[-1]}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
