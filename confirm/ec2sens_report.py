"""Item 72: EC^2 (ec2hyb) under other settings against the paper's K = 80, 5 questions per round, batch 3, budget 100.

Counts as paper_tables_v6f.py does: relations certified within 50 and 100 answers by at least two of three seeds,
good designs on the gold truth by the median seed, certified runs, wrong certificates (certified, not good, data satisfy the documented FDs).
Usage: python confirm/ec2sens_report.py [setting ...]; a setting file may be partial, then only its complete relations are compared.
"""
import json, os, statistics as st, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
B3 = ["fresh3_" + x for x in ("tpcc_order_line", "tpcc_stock", "tpcc_customer", "twitter_tweets", "synthea_encounters", "synthea_claims", "synthea_claims_transactions",
                              "companieshouse", "fec_candidate", "fec_committee", "fec_linkage", "gleif", "hgnc", "nppes_npidata", "onspd", "openpayments_general", "openpayments_profile",
                              "ourairports_airports", "ourairports_frequencies", "ourairports_navaids", "stackexchange_postlinks", "stackexchange_posts", "stackexchange_users")]
VIOL = {"full": {"fresh3_tpcc_order_line", "fresh3_hgnc", "fresh3_onspd", "fresh3_ourairports_airports", "fresh3_ourairports_frequencies"}, "sure": set()}


def rows(path, var):
    out = defaultdict(list)
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            if r["variant"] == var:
                out[r["dataset"]].append(r)
    return out


def within(r, b):
    return bool(r.get("certified")) and r["questions"] <= b


def summary(sd, T, rels):
    runs = [r for d in rels for r in sd[d]]
    return dict(
        w50=sum(sum(within(r, 50) for r in sd[d]) >= 2 for d in rels),
        w100=sum(sum(within(r, 100) for r in sd[d]) >= 2 for d in rels),
        good=sum(st.median(bool(r.get("gold_good")) for r in sd[d]) >= 0.5 for d in rels),
        cert=sum(bool(r.get("certified")) for r in runs),
        wrong=sum(bool(r.get("certified")) and not r.get("gold_good") and r["dataset"] not in VIOL[T] for r in runs),
        runs=len(runs), q=sum(r["questions"] for r in runs))


settings = sys.argv[1:] or ["k320_h5", "k80_h1"]
for T in ("full", "sure"):
    base = rows(os.path.join(HERE, f"v6f_fresh3_extra/ec2hyb_{T}.jsonl"), "ec2hyb")
    assert all(len(base[d]) == 3 for d in B3), T
    print(f"truth {T}: within 50, within 100 (relations, two of three seeds), good (median seed), certified runs, wrong certificates, answers")
    b = summary(base, T, B3)
    print(f"  K=80, h=5 (paper), 23 relations: {b['w50']}, {b['w100']}, good {b['good']}, certified {b['cert']}/{b['runs']}, wrong {b['wrong']}, answers {b['q']}")
    for s in settings:
        for fn in (f"{s}_{T}.jsonl", f"{s}_{T}_partial.jsonl"):
            p = os.path.join(HERE, "v6f_fresh3_extra/ec2sens", fn)
            if os.path.exists(p):
                break
        else:
            print(f"  {s}: no file")
            continue
        var = "ec2hyb_" + s
        sd = rows(p, var)
        rels = [d for d in B3 if len(sd[d]) == 3]
        x = summary(sd, T, rels)
        bb = summary(base, T, rels)
        tag = "" if len(rels) == 23 else f" (partial: only these {len(rels)} relations; the paper's setting on them: {bb['w50']}, {bb['w100']}, good {bb['good']}, certified {bb['cert']}/{bb['runs']}, wrong {bb['wrong']}, answers {bb['q']})"
        print(f"  {s}, {len(rels)} relations: {x['w50']}, {x['w100']}, good {x['good']}, certified {x['cert']}/{x['runs']}, wrong {x['wrong']}, answers {x['q']}{tag}")
