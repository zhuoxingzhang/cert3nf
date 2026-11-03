"""
Design note item 57: the careful mode of v5tol.py (mechanism c, eps_m = 0.02, a designer who never errs) without a
budget (1000 answers, a guard only), as item 39 did for the trusting v5 family.  v5tol.py (frozen by item 46,
f3ec39c04c59) is not changed: it has no --budget option and stops in put() at its module name BUDGET (from v5 import
BUDGET), so every worker of this driver sets v5tol.BUDGET (and v5.BUDGET) before it calls v5tol.one.  One row per
(variant, relation): the fields of v5tol.one plus budget and true, the fields that v5_unb_report.py and load_unb of
paper_tables_v5.py read; a rerun resumes.  Variants: v5t, v5st (careful), v5, v5s (eps_m = 0, the implementation
check against v5_unb).
Usage (in confirm, like v5tol.py):
  CONFIRM_ORACLE=gold CONFIRM_TRUTH=full python scripts/run_v5tol_unb.py --answers llm_fresh_full_q35_ms \
      --datasets a,b --out v5tol_unb/v5tol_full.jsonl [--budget 1000] [--variants v5t,v5st,v5,v5s] [--workers 6]
"""
import argparse, json, os, sys
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # confirm
sys.path.insert(0, HERE)
import auto_common as AC
import v5
import v5tol


def one(args):
    budget, job = args
    v5.BUDGET = v5tol.BUDGET = budget            # v5tol.put() raises Budget at st["q"] >= BUDGET
    r = v5tol.one(job)
    r["budget"] = budget
    r["true"] = len(AC.load(job[1])["truth"])
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", required=True)
    ap.add_argument("--model", default="q35")
    ap.add_argument("--datasets", required=True)
    ap.add_argument("--variants", default="v5t,v5st,v5,v5s")
    ap.add_argument("--budget", type=int, default=1000)
    ap.add_argument("--mech", default="c", choices=sorted(v5tol.MECHS))
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    assert AC.oracle_mode() == "gold", "item 57 runs with CONFIRM_ORACLE=gold"
    assert v5tol.BUDGET == v5.BUDGET == 100, "v5tol.py or v5.py is not the frozen file (BUDGET 100)"
    done = set()
    if os.path.exists(a.out):
        with open(a.out, encoding="utf-8") as fh:
            done = {(r["variant"], r["dataset"]) for r in map(json.loads, filter(str.strip, fh))}
    big = {"fresh_tpcds_customer", "tpch_lineitem_orders", "fresh_scorecard_fos", "ssb_lineorder", "fresh_pums_ca"}
    dss = sorted(a.datasets.split(","), key=lambda d: (d not in big, d))
    jobs = [(a.budget, (v, ds, a.answers, a.model, 0.0, 0, False, a.mech, 0.0))
            for ds in dss for v in a.variants.split(",")
            if (v, ds) not in done and not (ds in v5tol.NO_LLM and v5tol.VARIANTS[v][0])]
    print(f"{len(jobs)} runs to do, {len(done)} done, budget {a.budget}, mech {a.mech}", flush=True)
    with ProcessPoolExecutor(max(1, a.workers)) as ex, open(a.out, "a", encoding="utf-8") as fo:
        for f in as_completed([ex.submit(one, j) for j in jobs]):
            r = f.result()
            fo.write(json.dumps(r) + "\n")
            fo.flush()
            print(f"{r['variant']:4s} {r['dataset']:28s} cert {r['certified']!s:5s} exact {r['cert_exact']!s:5s} "
                  f"good {r['gold_good']!s:5s} q {r['questions']:4d} reask {r['reask_questions']} "
                  f"confirm {r['confirm_questions']} {r['secs']}s", flush=True)


if __name__ == "__main__":
    main()
