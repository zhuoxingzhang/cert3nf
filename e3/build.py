"""
E3 benchmarks: one JSON per dataset in data/, from the gold Sigma* in truth/<family>.json and the minimal FDs mined
from the instance; truth.json and features.csv collect all datasets for an estimator.

Stage "mine" (heavy, run on the experiment server for the large tables) builds the instance, drops constant
columns, mines all minimal FDs with fdmine (exact, the same output as HyFD), computes the data statistics of every
mined FD, and checks every FD of Sigma* on the instance.  It caches mined/<ds>-fds.txt (Metanome format) and
mined/<ds>-stats.json.  Stage "json" reads these caches and the truth files, decides implied_by_truth, synthesizes
the 3NF designs of Sigma* (classical synthesis and iCONF, as in E2) and writes data/<ds>.json.  Stage "export"
writes truth.json (all Sigma*, in the format of ../e2/tpch_truth.json) and features.csv (one row per mined FD).
The rwd and ctu families (rwd.py, ctu.py) are for training only, and stage "json" marks the mined FDs their ground
truth labels ("labeled"); the training reads only those.  RWD labels are complete on the judged unary pairs, so a
mined FD is labeled if it is unary and judged or implied by Sigma*: an implied FD with a larger left-hand side is
true, but labeling only those would make every labeled one true.  CTU labels an FD if Sigma* implies it or its
attributes come from more than one source table.

Features of a mined FD X -> A on n rows (X-classes: the groups of rows that agree on X):
  lhs_size; distinct_lhs (number of X-classes) and lhs_distinct_ratio = distinct_lhs / n; distinct_rhs and
  rhs_distinct_ratio = distinct_rhs / n; redundancy = sum over X-classes of (size - 1) = n - distinct_lhs;
  redundancy_wl, the Wei and Link count of value occurrences of A that X -> A makes redundant, i.e. the number of
  rows in X-classes of size >= 2; lhs_unique (X is a key of the instance); lhs_tokens and rhs_tokens, the
  lower-case word tokens of the column names (split at '_', spaces, digits and lower-upper case changes).

Usage:  python build.py <dir with the TPC-H SF 0.1 .tbl files> [--stage mine|json|export|all] [--only ds1,ds2]
"""
import csv, json, os, re, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fdmine      # noqa: E402

FAMILIES = {"tpch": ["tpch_orders_customer", "tpch_partsupp_part_supplier", "tpch_lineitem_orders"],
            "ssb": ["ssb_customer", "ssb_supplier", "ssb_part", "ssb_date", "ssb_lineorder"],
            "documented": ["hospital", "food", "pricepaid", "tpcds_core"],
            "screened": ["abalone", "adult", "breast", "bridges", "echo", "hepatitis", "letter", "ncvoter"],
            "rwd": ["rwd_adult", "rwd_claims", "rwd_dblp10k", "rwd_tax", "rwd_gathering_agent", "rwd_namedareas",
                    "rwd_gathering", "rwd_highertaxon", "rwd_identification"]}
if os.path.exists(os.path.join(HERE, "truth", "ctu.json")):    # the relations of ctu.py, chosen from the schemas
    with open(os.path.join(HERE, "truth", "ctu.json"), encoding="utf-8") as _fh:
        FAMILIES["ctu"] = list(json.load(_fh)["datasets"])
if os.path.exists(os.path.join(HERE, "truth", "fresh.json")):  # the confirmatory relations of fresh.py (item 28)
    with open(os.path.join(HERE, "truth", "fresh.json"), encoding="utf-8") as _fh:
        FAMILIES["fresh"] = list(json.load(_fh)["datasets"])
if os.path.exists(os.path.join(HERE, "truth", "fresh2.json")):  # the second confirmatory batch (item 33), same tooling
    with open(os.path.join(HERE, "truth", "fresh2.json"), encoding="utf-8") as _fh:
        FAMILIES["fresh2"] = list(json.load(_fh)["datasets"])
FAMILY = {ds: fam for fam, dss in FAMILIES.items() for ds in dss}
CTU_CAP = 2000     # labeled false FDs kept per ctu relation (stage json)
INSTANCE = {
    "tpch": {"generator": "TPC-H dbgen 3.0.1", "scale_factor": 0.1,
             "command": "dbgen -s 0.1 (default seed); gen_tpch.py joins the tables"},
    "ssb": {"generator": "derived from TPC-H dbgen 3.0.1 output (SF 0.1) by gen_ssb.py, following the SSB "
                         "specification; not ssb-dbgen", "scale_factor": 0.1},
    "documented": {"generator": "real data of prior work (src/documented.py), prepared by real.py"},
    "screened": {"generator": "data sets of the HPI repeatability page, prepared by real.py"},
    "rwd": {"generator": "the RWD benchmark of Parciak et al. (rwd_raw/), prepared by rwd.py"},
    "ctu": {"generator": "databases of the CTU repository as converted by ReDeLEx, joined by ctu.py"},
    "fresh": {"generator": "public data fixed before download for the confirmatory evaluation, joined by fresh.py"},
    "fresh2": {"generator": "public data fixed before download for the second confirmatory evaluation (item 33), "
                            "converted by unpack_fresh2.py and joined by fresh.py"},
}


def truth_spec(ds):
    with open(os.path.join(HERE, "truth", FAMILY[ds] + ".json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    return doc, doc["datasets"][ds]


def effective(spec, dropped):
    """Attributes and Sigma* without the constant columns dropped from the instance."""
    names = [a for a in spec["attributes"] if a not in dropped]
    truth = []
    for f in spec["truth"]:
        lhs = [x for x in f["lhs"] if x not in dropped]
        rhs = [a for a in f["rhs"] if a not in dropped and a not in lhs]
        if rhs:
            truth.append({**f, "lhs": lhs, "rhs": rhs})
    return names, truth


def fdstr(lhs, rhs):
    return ",".join(lhs) + " -> " + rhs


def tokens(name):
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    return [t.lower() for t in re.split(r"[_\s\d#()+\-.]+", s) if t]


# ---------- stage mine ----------

def instances(tbl_dir, wanted):
    out = {}
    gen = [d for d in wanted if FAMILY[d] in ("tpch", "ssb")]
    if gen:
        import gen_tpch, gen_ssb
        T = gen_tpch.load(tbl_dir)
        if any(FAMILY[d] == "tpch" for d in gen):
            out.update(gen_tpch.wide_tables(T))
        if any(FAMILY[d] == "ssb" for d in gen):
            out.update(gen_ssb.ssb_tables(T))
    real = [d for d in wanted if FAMILY[d] in ("documented", "screened")]
    if real:
        import real as RL
        out.update(RL.instances(real))
    for d in wanted:
        if FAMILY[d] == "rwd":
            import rwd
            out[d] = rwd.instance(d, truth_spec(d)[1]["truth"])
        elif FAMILY[d] == "ctu":
            import ctu
            out[d] = ctu.instance(d, truth_spec(d)[1])
        elif FAMILY[d] in ("fresh", "fresh2"):
            import fresh
            out[d] = fresh.instance(d, truth_spec(d)[1])
    return {d: out[d] for d in wanted}


def matrix(cols):
    return fdmine.encode([c.codes for c in cols])


def miner_for(M):
    return fdmine.Miner(M, [int(M[:, j].max()) + 1 for j in range(M.shape[1])])


def statistics(M, fds, names):
    miner = miner_for(M)
    distinct = [int(M[:, j].max()) + 1 for j in range(M.shape[1])]
    bylhs = {}
    for X, a in fds:
        bylhs.setdefault(X, []).append(a)
    out = {}
    for X, rhs in bylhs.items():
        _, counts = np.unique(miner.labels(fdmine.bits(X)), return_counts=True)
        red = int(counts[counts >= 2].sum())
        for a in rhs:
            out[(X, a)] = {"lhs": [names[b] for b in fdmine.bits(X)], "rhs": names[a],
                           "distinct_lhs": int(len(counts)), "distinct_rhs": distinct[a], "redundancy_wl": red}
    return [out[f] for f in fds]


def holds(M, names, lhs, rhs):
    k = miner_for(M).labels([names.index(x) for x in lhs])
    order = np.argsort(k, kind="stable")
    same = k[order][1:] == k[order][:-1]
    out = {}
    for a in rhs:
        col = M[order, names.index(a)]
        bad = same & (col[1:] != col[:-1])
        # g3: the fraction of rows to delete so that lhs -> a holds
        g3 = 0.0
        if bad.any():
            base = int(col.max()) + 1
            grp = np.concatenate([[0], np.cumsum(~same)]).astype(np.int64)     # X-class of every sorted row
            pairs, counts = np.unique(grp * base + col, return_counts=True)
            best = np.zeros(int(grp.max()) + 1, dtype=np.int64)
            np.maximum.at(best, pairs // base, counts)                        # most frequent A-value per X-class
            g3 = round(1 - int(best.sum()) / len(col), 6)
        out[a] = {"holds": not bad.any(), "g3": g3}
    return out


def check_truth(M, names, truth):
    """Every FD of Sigma* (split to single right-hand sides): does it hold on the instance, and its g3 error."""
    out = []
    for f in truth:
        h = holds(M, names, f["lhs"], f["rhs"])
        out += [{"fd": fdstr(f["lhs"], a), "sure": f["sure"], **h[a]} for a in f["rhs"]]
    return out


def calendar_check(truth, names):
    """ssb_date: does Sigma* hold on a full 400-year Gregorian cycle and imply every minimal FD that holds there?"""
    import gen_ssb
    M, _ = matrix(gen_ssb.calendar(1601, 2000))
    fds = fdmine.mine([M[:, j] for j in range(M.shape[1])])
    sig = [(frozenset(names.index(x) for x in f["lhs"]), frozenset(names.index(a) for a in f["rhs"])) for f in truth]
    not_implied = [fdstr([names[b] for b in fdmine.bits(X)], names[a]) for X, a in fds
                   if a not in closure(frozenset(fdmine.bits(X)), sig)]
    failing = [c["fd"] for c in check_truth(M, names, truth) if not c["holds"]]
    return {"years": "1601-2000", "rows": int(M.shape[0]), "minimal_fds": len(fds),
            "truth_fds_failing": failing, "minimal_fds_not_implied_by_truth": not_implied}


def stage_mine(tbl_dir, wanted):
    for ds, inst in instances(tbl_dir, wanted).items():
        cols, all_names = inst["cols"], inst["attributes"]
        const = [a for a, c in zip(all_names, cols) if len(np.unique(c.codes)) <= 1]
        keep = [j for j, a in enumerate(all_names) if a not in const]
        names = [all_names[j] for j in keep]
        M, _ = matrix([cols[j] for j in keep])
        t0 = time.time()
        fds = fdmine.Miner(M, [int(M[:, j].max()) + 1 for j in range(M.shape[1])], verbose=True).run()
        secs = time.time() - t0
        fdmine.write_metanome(os.path.join(HERE, "mined", ds + "-fds.txt"), ds, names, fds)
        _, spec = truth_spec(ds)
        assert spec["attributes"] == all_names, (ds, spec["attributes"], all_names)
        _, truth = effective(spec, const)
        stats = {"dataset": ds, "rows": int(M.shape[0]), "attributes": names, "dropped_constant_columns": const,
                 "distinct": [int(M[:, j].max()) + 1 for j in range(M.shape[1])],
                 "mining_seconds": round(secs, 1), "truth_on_instance": check_truth(M, names, truth),
                 "features": statistics(M, fds, names)}
        if "cleaning" in inst:
            stats["cleaning"] = inst["cleaning"]
        if ds == "ssb_date":
            stats["calendar_check"] = calendar_check(truth, names)
        if FAMILY[ds] == "screened":
            import real as RL
            ref, path = RL.metanome(ds, names)
            mine = {(frozenset(names[b] for b in fdmine.bits(X)), names[a]) for X, a in fds}
            stats["metanome_check"] = {"file": path, "metanome": len(ref), "fdmine": len(mine),
                                       "identical": ref == mine,
                                       "only_fdmine": sorted(fdstr(sorted(l), r) for l, r in mine - ref)[:50],
                                       "only_metanome": sorted(fdstr(sorted(l), r) for l, r in ref - mine)[:50]}
        with open(os.path.join(HERE, "mined", ds + "-stats.json"), "w", encoding="utf-8") as fh:
            json.dump(stats, fh)
        print(f"{ds}: {M.shape[0]} rows, {len(names)} columns, {len(fds)} minimal FDs, {secs:.1f}s", flush=True)


# ---------- stage json ----------

def closure(Z, sigma):
    Z, changed = set(Z), True
    while changed:
        changed = False
        for lhs, rhs in sigma:
            if lhs <= Z and not rhs <= Z:
                Z |= rhs
                changed = True
    return Z


def designs(names, truth):
    """3NF designs of Sigma* by classical synthesis and iCONF (the engine of E2)."""
    sys.path.insert(0, os.path.join(HERE, "..", "e2"))
    import e2_tpch as E
    idx = {a: i for i, a in enumerate(names)}
    R = list(range(len(names)))
    st = [(frozenset(idx[x] for x in f["lhs"]), frozenset(idx[a] for a in f["rhs"])) for f in truth]
    st_a = E.atomic_closure(R, st)
    keys = E.B.minimal_keys(frozenset(R), st_a)
    out = {"keys": [sorted(names[i] for i in k) for k in keys], "atomic_closure": len(st_a)}
    for m in E.MODES:
        out[m] = sorted(sorted(names[i] for i in s) for s in E.S.design(R, st_a, m))
    return out


def construction(ds, spec):
    if spec.get("join") or spec.get("construction"):
        return spec.get("join") or spec.get("construction")
    import gen_ssb
    return gen_ssb.CHOICES[ds.split("_", 1)[1]]


def stage_json(wanted):
    for ds in wanted:
        doc, spec = truth_spec(ds)
        with open(os.path.join(HERE, "mined", ds + "-stats.json"), encoding="utf-8") as fh:
            st = json.load(fh)
        const = st.get("dropped_constant_columns", [])
        names, truth = effective(spec, const)
        assert st["attributes"] == names
        n = st["rows"]
        idx = {a: i for i, a in enumerate(names)}
        pairs = {tuple(p) for p in spec.get("judged_pairs", [])}
        judged = lambda f: (f["lhs"][0], f["rhs"]) in pairs
        home = spec.get("home", {})
        sig = lambda fs: [(frozenset(idx[x] for x in f["lhs"]), frozenset(idx[a] for a in f["rhs"])) for f in fs]
        s_all, s_sure = sig(truth), sig([f for f in truth if f["sure"]])
        fds = []
        for f in st["features"]:
            X, a = frozenset(idx[x] for x in f["lhs"]), idx[f["rhs"]]
            red = f.get("redundancy_wl", f.get("redundancy"))
            fds.append({"lhs": f["lhs"], "rhs": f["rhs"], "implied_by_truth": a in closure(X, s_all),
                        "implied_by_sure_truth": a in closure(X, s_sure), "lhs_size": len(f["lhs"]),
                        "distinct_lhs": f["distinct_lhs"], "distinct_rhs": f["distinct_rhs"],
                        "lhs_distinct_ratio": round(f["distinct_lhs"] / n, 6),
                        "rhs_distinct_ratio": round(f["distinct_rhs"] / n, 6),
                        "redundancy": n - f["distinct_lhs"], "redundancy_wl": red,
                        "lhs_unique": f["distinct_lhs"] == n,
                        "lhs_tokens": [tokens(x) for x in f["lhs"]], "rhs_tokens": tokens(f["rhs"])})
            if FAMILY[ds] == "rwd":      # the annotation of RWD judged unary pairs only (rwd.py)
                fds[-1]["labeled"] = len(f["lhs"]) == 1 and (judged(f) or fds[-1]["implied_by_truth"])
            elif FAMILY[ds] == "ctu":    # FDs within one source table may be undeclared (ctu.py)
                fds[-1]["labeled"] = fds[-1]["implied_by_truth"] or len({home[x] for x in f["lhs"] + [f["rhs"]]}) > 1
        # the mined set is the complete set of minimal FDs of the instance: it implies every FD that holds there
        mined_sig = [(frozenset(idx[x] for x in f["lhs"]), frozenset([idx[f["rhs"]]])) for f in fds]
        for c in st["truth_on_instance"]:
            lhs, a = c["fd"].split(" -> ")
            X = frozenset(idx[x] for x in lhs.split(",") if x)
            assert (idx[a] in closure(X, mined_sig)) == c["holds"], (ds, c)
        violated = [{k: c[k] for k in ("fd", "sure", "g3") if k in c} for c in st["truth_on_instance"] if not c["holds"]]
        n_truth = sum(len(f["rhs"]) for f in truth)
        labeled = [f for f in fds if f.get("labeled", True)]
        out = {
            "dataset": ds,
            "family": FAMILY[ds],
            "truth_kind": doc.get("truth_kind", "specification"),
            "source": doc["source"],
            "rule": doc["rule"],
            "instance": {**INSTANCE[FAMILY[ds]], "rows": n, "construction": construction(ds, spec),
                         **({"cleaning": st["cleaning"]} if "cleaning" in st else {})},
            "attributes": names,
            "dropped_constant_columns": const,
            "distinct_values": dict(zip(names, st["distinct"])),
            "truth": truth,
            "truth_counts": {"fds": len(truth), "single_rhs": n_truth,
                             "sure_single_rhs": sum(len(f["rhs"]) for f in truth if f["sure"])},
            "random_columns": spec.get("random_columns"),
            "truth_fds_violated_by_data": violated,
            "gold_design": spec.get("gold_design"),
            "gold_design_note": spec.get("gold_design_note"),
            "truth_design": designs(names, truth),
            "mined": {"algorithm": "fdmine.py: exact discovery of all minimal FDs in the style of HyFD (no HyFD binary "
                                   "was available); the complete set of minimal FDs is unique, so it equals HyFD's output",
                      "file": f"mined/{ds}-fds.txt", "seconds": st["mining_seconds"], "count": len(fds),
                      "implied_by_truth": sum(f["implied_by_truth"] for f in fds),
                      "accidental": sum(not f["implied_by_truth"] for f in fds),
                      "implied_by_sure_truth": sum(f["implied_by_sure_truth"] for f in fds),
                      **({"labeled": len(labeled), "labeled_true": sum(f["implied_by_truth"] for f in labeled)}
                         if FAMILY[ds] in ("rwd", "ctu") else {})},
            "fds": fds,
        }
        for k in ("calendar_check", "metanome_check"):
            if k in st:
                out[k] = st[k]
        if any(not f["sure"] for f in truth):
            out["truth_design_sure_only"] = designs(names, [f for f in truth if f["sure"]])
        if FAMILY[ds] == "ctu":
            # a training relation keeps every labeled true FD and at most CTU_CAP labeled false ones, drawn uniformly
            # with a fixed seed, so that a few wide relations with 10^5 minimal FDs do not dominate; "weight" is the
            # inverse sampling fraction, which restores the labeled population (the counts above are complete).
            # Sampling on the label only moves the intercepts of the answer models' logistic regressions, so their
            # likelihood ratios are unaffected (case-control sampling).
            import random
            neg = [f for f in labeled if not f["implied_by_truth"]]
            pick = set(map(id, random.Random(0).sample(neg, min(len(neg), CTU_CAP))))
            w = len(neg) / max(len(pick), 1)
            fds = [dict(f, weight=1.0 if f["implied_by_truth"] else round(w, 6)) for f in labeled
                   if f["implied_by_truth"] or id(f) in pick]
            out["mined"]["kept_for_training"] = len(fds)
        with open(os.path.join(HERE, "data", ds + ".json"), "w", encoding="utf-8") as fh:
            body = json.dumps({k: v for k, v in out.items() if k != "fds"}, indent=1, ensure_ascii=False)
            fh.write(body[:-2] + ',\n "fds": [\n' + ",\n".join("  " + json.dumps(f) for f in fds) + "\n ]\n}\n")
        m = out["mined"]
        print(f"{ds}: |R| = {len(names)}, |Sigma*| = {len(truth)} FDs ({n_truth} single-rhs), "
              f"mined {m['count']}, implied {m['implied_by_truth']}, accidental {m['accidental']}, "
              f"violated {len(violated)}")


# ---------- stage export ----------

def stage_export():
    tables, rows = {}, []
    for fam, dss in FAMILIES.items():
        for ds in dss:
            p = os.path.join(HERE, "data", ds + ".json")
            if not os.path.exists(p):
                continue
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
            tables[ds] = {"family": fam, "truth_kind": d["truth_kind"], "rows": d["instance"]["rows"],
                          "attributes": d["attributes"], "fds": d["truth"],
                          "justification": d["rule"], "source": d["source"]}
            for f in d["fds"]:
                rows.append({"dataset": ds, "family": fam, "truth_kind": d["truth_kind"], "n": d["instance"]["rows"],
                             "lhs": ",".join(f["lhs"]), "rhs": f["rhs"],
                             "implied_by_truth": int(f["implied_by_truth"]),
                             "implied_by_sure_truth": int(f["implied_by_sure_truth"]),
                             **{k: f[k] for k in ("lhs_size", "distinct_lhs", "distinct_rhs", "lhs_distinct_ratio",
                                                  "rhs_distinct_ratio", "redundancy", "redundancy_wl")},
                             "lhs_unique": int(f["lhs_unique"]),
                             "lhs_tokens": "|".join(" ".join(t) for t in f["lhs_tokens"]),
                             "rhs_tokens": " ".join(f["rhs_tokens"])})
    with open(os.path.join(HERE, "truth.json"), "w", encoding="utf-8") as fh:
        json.dump({"source": "E3 benchmarks; per dataset the specification or documentation cited in data/<ds>.json",
                   "rule": "Sigma* per dataset with one justification and clause per FD; \"sure\": false marks FDs "
                           "that hold on every instance of the construction (or are doubtful variants) but are not "
                           "forced by the specification",
                   "tables": tables}, fh, indent=1, ensure_ascii=False)
    with open(os.path.join(HERE, "features.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"truth.json: {len(tables)} datasets; features.csv: {len(rows)} mined FDs")
    print("| dataset | rows | \\|R\\| | \\|Σ\\*\\| FDs (single RHS) | of which unsure | mined | implied by Σ\\* | accidental |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for ds in tables:
        with open(os.path.join(HERE, "data", ds + ".json"), encoding="utf-8") as fh:
            d = json.load(fh)
        c, m = d["truth_counts"], d["mined"]
        print(f"| `{ds}` | {d['instance']['rows']:,} | {len(d['attributes'])} | {c['fds']} ({c['single_rhs']}) | "
              f"{c['single_rhs'] - c['sure_single_rhs']} | {m['count']:,} | {m['implied_by_truth']:,} | {m['accidental']:,} |")


if __name__ == "__main__":
    args = sys.argv[1:]
    stage = args[args.index("--stage") + 1] if "--stage" in args else "all"
    wanted = args[args.index("--only") + 1].split(",") if "--only" in args else list(FAMILY)
    if stage in ("mine", "all"):
        stage_mine(args[0], wanted)
    if stage in ("json", "all"):
        stage_json(wanted)
    if stage in ("export", "all"):
        stage_export()
