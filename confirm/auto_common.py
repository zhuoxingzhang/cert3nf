"""
Shared parts of the automated pipeline (design notes): the twelve relations with independent ground
truth, their declared keys, and the candidates.

Declared keys (design note, section 2): what a database or the publisher of the data declares, never the ground truth.
  TPC-H, SSB, TPC-DS  the primary key of the DDL; for a join along foreign keys, the key of the referencing table,
                      since each of its rows meets at most one row of every referenced table
  food                Inspection ID, the identifier of an inspection in the City of Chicago data   (verify)
  pricepaid           Transaction unique identifier of HM Land Registry                             (verify)
  hospital            none declared
For every relation but hospital this is the key that bench.load took from the ground truth (checked 2026-10-17).
The declared key is an optional input.  With the environment variable CONFIRM_NO_KEY=1 no relation declares one
(ablation K, design note, component selection): sigma0 is empty, the minimal FDs that the key implies become candidates, and the
prompts say "none declared".  The variable is read at every load, so worker processes inherit the mode.

Candidates: all minimal FDs mined on the whole instance that the declared key does not imply (design note, section 1).
The size of a left-hand side decides nothing about the truth of an FD, so the candidates are not limited by it
(max_lhs=None); the parameter remains for the earlier runs with max_lhs=3.  Only the relations whose ground truth comes from a specification or from
documented rules are used; the ground truth of the eight UCI sets was screened with a language model (section 7).

Training pool.  TRAIN holds relations with independent ground truth that are never evaluated (the rwd and ctu
families of E3, e3/rwd.py and e3/ctu.py); their candidates are the mined FDs that their ground truth labels.  The environment variable CONFIRM_POOL
says on which relations the prior and the answer models of a held-out relation are trained:
  loo       the other evaluation relations (the default, as before)
  both      the other evaluation relations and TRAIN
  external  TRAIN only, so that no evaluation relation trains anything
The relation itself is never in its training set.

Ground truth.  The environment variable CONFIRM_TRUTH chooses the version of Sigma* (design note, component selection item 17), for
training and evaluation alike:
  full      Sigma* as built, with the items marked sure=false (the default, as before)
  sure      the items marked sure only
  audited   the sure items without those that the documentation-only audit contradicts, plus the sure=false items and
            the candidates that it supports (e3/truth/audit/audit_result.json, for food, hospital and pricepaid)
The labels of the mined FDs (implied_by_truth) are recomputed for the chosen version.
"""
import json, os
import bench
import estimators as EST

S = bench.S
DATASETS = ["food", "hospital", "pricepaid", "ssb_customer", "ssb_date", "ssb_lineorder", "ssb_part", "ssb_supplier",
            "tpcds_core", "tpch_lineitem_orders", "tpch_orders_customer", "tpch_partsupp_part_supplier"]
DECLARED = {
    "food": ["InspectionID"],
    "hospital": None,
    "pricepaid": ["TransactionID"],
    "ssb_customer": ["c_custkey"],
    "ssb_date": ["d_datekey"],
    "ssb_lineorder": ["lo_orderkey", "lo_linenumber"],
    "ssb_part": ["p_partkey"],
    "ssb_supplier": ["s_suppkey"],
    "tpcds_core": ["i_item_sk", "ss_ticket_number"],
    "tpch_lineitem_orders": ["l_orderkey", "l_linenumber"],
    "tpch_orders_customer": ["o_orderkey"],
    "tpch_partsupp_part_supplier": ["ps_partkey", "ps_suppkey"],
    "rwd_adult": None,
    "rwd_claims": ["Claim Number"],
    "rwd_dblp10k": None,
    "rwd_tax": None,
    "rwd_gathering_agent": ["_gatheringagentguid"],
    "rwd_namedareas": ["_namedareasguid"],
    "rwd_gathering": ["_unitguid"],
    "rwd_highertaxon": None,
    "rwd_identification": ["_identificationguid"],
}
TRAIN = ["rwd_adult", "rwd_claims", "rwd_dblp10k", "rwd_tax", "rwd_gathering_agent", "rwd_namedareas", "rwd_gathering",
         "rwd_highertaxon", "rwd_identification"]
POOLS = ("loo", "both", "external")
_CTU = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "e3", "truth", "ctu.json")
if os.path.exists(_CTU):     # the relations of e3/ctu.py; each declares the row identifier of its root
    with open(_CTU, encoding="utf-8") as _fh:
        _ctu = json.load(_fh)["datasets"]
    DECLARED.update({ds: spec["key"] for ds, spec in _ctu.items()})
    TRAIN += [ds for ds in _ctu if os.path.exists(os.path.join(bench.E3, ds + ".json"))]
FRESH = []
for _name in ("fresh.json", "fresh2.json"):   # the confirmatory relations of e3/fresh.py (design note items 28 and 33):
    _FRESH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "e3", "truth", _name)   # evaluated, never in a pool
    if os.path.exists(_FRESH):
        with open(_FRESH, encoding="utf-8") as _fh:
            _fresh = json.load(_fh)["datasets"]
        DECLARED.update({ds: spec.get("key") for ds, spec in _fresh.items()})
        FRESH += [ds for ds in _fresh if os.path.exists(os.path.join(bench.E3, ds + ".json"))]
if os.environ.get("CONFIRM_BATCH") == "2":    # item 33: the 24 development relations (the 12 above and the 12 of item
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "e3", "truth", "fresh2.json"),
              encoding="utf-8") as _fh:    # 28) are the pool; the second batch is evaluated and trains nothing
        _batch2 = list(json.load(_fh)["datasets"])
    DATASETS += [ds for ds in FRESH if ds not in _batch2]
    FRESH = [ds for ds in FRESH if ds in _batch2]
SAMPLES =os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "e3", "samples")


TRUTHS = ("full", "sure", "audited")
_TRUTH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "e3", "truth")


def truth_mode():
    m = os.environ.get("CONFIRM_TRUTH", "full")
    if m not in TRUTHS:
        raise ValueError(f"CONFIRM_TRUTH={m}, not one of {TRUTHS}")
    return m


ORACLES = ("reach", "gold")


def oracle_mode():
    """what the simulated designer knows (design note item 32): "reach", the declared key and the true candidates
    (the first draft: a true FD that is not minimal on the data was then answered no), or "gold", the documented
    truth Sigma* itself"""
    m = os.environ.get("CONFIRM_ORACLE", "reach")
    if m not in ORACLES:
        raise ValueError(f"CONFIRM_ORACLE={m}, not one of {ORACLES}")
    return m


def oracle(b):
    """the FDs the simulated designer answers from, as (lhs, rhs) pairs of attribute indices"""
    return b["sigma0"] + (b["gold"] if oracle_mode() == "gold" else b["truth"])


def _audit(ds):
    """(items of the documented truth that the audit contradicts, items it supports, candidates it supports) of ds,
    the candidates as (lhs list, rhs) pairs; empty for a relation outside the audit"""
    with open(os.path.join(_TRUTH, "audit", "audit_result.json"), encoding="utf-8") as fh:
        rel = json.load(fh)["relations"].get(ds)
    if rel is None:
        return [], [], []
    with open(os.path.join(_TRUTH, "documented.json"), encoding="utf-8") as fh:
        items = json.load(fh)["datasets"][ds]["truth"]
    verdict = {it["id"]: it["verdict"] for it in rel["sigma_items"]}
    contra = [t for i, t in enumerate(items) if verdict.get(f"{ds}#{i}") == "FALSE_DOC"]
    support = [t for i, t in enumerate(items) if verdict.get(f"{ds}#{i}") == "TRUE"]
    cands = [(c["lhs"], c["rhs"]) for c in rel["candidates"] if c["verdict"] == "TRUE"]
    return contra, support, cands


def raw(ds):
    with open(os.path.join(bench.E3, ds + ".json"), encoding="utf-8") as fh:
        d = json.load(fh)
    m = truth_mode()
    if m == "full" or "truth" not in d:
        return d
    if m == "sure":
        d["truth"] = [t for t in d["truth"] if t.get("sure", True)]
    else:
        contra, support, cands = _audit(ds)
        # an item is matched on its attributes in the data file, which drops the constant columns
        key = lambda t: (frozenset(t["lhs"]), frozenset(set(t["rhs"]) & set(d["attributes"])))
        contra, support = {key(t) for t in contra}, {key(t) for t in support}
        found = {key(t) for t in d["truth"]}
        assert contra <= found and support <= found, (ds, "audited items not in the truth of the data file")
        d["truth"] = [t for t in d["truth"] if key(t) not in contra and (t.get("sure", True) or key(t) in support)]
        d["truth"] += [{"lhs": l, "rhs": [r], "sure": True, "clause": "documentation-only audit"} for l, r in cands]
    idx = {a: i for i, a in enumerate(d["attributes"])}
    gold = [S.fd([idx[a] for a in t["lhs"]], idx[r]) for t in d["truth"] for r in t["rhs"] if r not in t["lhs"]]
    for f in d["fds"]:
        f["implied_by_truth"] = S.implies(gold, S.fd([idx[a] for a in f["lhs"]], idx[f["rhs"]]))
    return d


def no_key():
    return os.environ.get("CONFIRM_NO_KEY") == "1"


def pool_mode():
    m = os.environ.get("CONFIRM_POOL", "loo")
    if m not in POOLS:
        raise ValueError(f"CONFIRM_POOL={m}, not one of {POOLS}")
    return m


def pool():
    """the relations that may train the prior and the answer models (each relation still leaves itself out)"""
    m = pool_mode()
    return (DATASETS if m != "external" else []) + (TRAIN if m != "loo" else [])


def load(ds, max_lhs=None):
    """the instance of bench.load with the declared key as sigma0; adds the names of every candidate.
    implied0 holds the mined minimal FDs that sigma0 implies: they are concluded without a question, and the metrics
    over all mined FDs (auto_confirm.prf_mined) count them, so that runs with and without a declared key compare."""
    d = raw(ds)
    names = d["attributes"]
    idx = {a: i for i, a in enumerate(names)}
    R = list(range(len(names)))
    gold = [S.fd([idx[a] for a in t["lhs"]], idx[r]) for t in d["truth"] for r in t["rhs"]
            if idx[r] not in [idx[a] for a in t["lhs"]]]
    key = None if no_key() else DECLARED[ds]
    km = [idx[a] for a in key] if key else []
    sigma0 = [S.fd(km, x) for x in R if x not in km] if key else []
    rows = d["instance"]["rows"]
    cands, X, truth, fdn, implied0 = [], {}, [], {}, []
    for f in d["fds"]:
        if max_lhs is not None and len(f["lhs"]) > max_lhs or not f.get("labeled", True):
            continue
        p = S.fd([idx[a] for a in f["lhs"]], idx[f["rhs"]])
        if p in X or p in implied0:
            continue
        if sigma0 and S.implies(sigma0, p):
            assert f["implied_by_truth"], (ds, f)       # the declared key is a key of the ground truth
            implied0.append(p)
            continue
        cands.append(p)
        X[p] = bench.features(f, rows) + EST.name_features(f)
        fdn[p] = (sorted(f["lhs"], key=idx.get), f["rhs"])
        if f["implied_by_truth"]:
            truth.append(p)
    out_scope = sum(1 for f in d["fds"] if f["implied_by_truth"] and max_lhs is not None and len(f["lhs"]) > max_lhs)
    return {"name": ds, "R": R, "names": names, "sigma0": sigma0, "key": key, "gold": gold, "P": cands, "X": X,
            "truth": truth, "true_out_of_scope": out_scope, "rows": rows, "fdnames": fdn, "implied0": implied0}


def fd_id(ds, lhs, rhs):
    """a stable identifier of a candidate, independent of the order of the mined file"""
    return f"{ds}|{','.join(sorted(lhs))}|{rhs}"


if __name__ == "__main__":
    tot = 0
    for ds in DATASETS:
        b = load(ds)
        tot += len(b["P"])
        print(f"{ds:28s} key={b['key']} candidates={len(b['P']):5d} true={len(b['truth']):4d} "
              f"implied by the key={len(b['implied0'])} true out of scope={b['true_out_of_scope']}")
    print("total candidates", tot)
