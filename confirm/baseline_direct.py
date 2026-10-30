"""
Zero-question baselines on the E3 benchmarks: what if no designer is asked?

  threshold  trust an estimator: the candidates with rho >= 0.5 are taken as true and the 3NF design is synthesized from
             them with Confirm's synthesis (drd.Instance.threshold, the policy "nothing" of bench.py)
  llm        a language model designs the schema directly: one blind prompt per relation with the information of
             llm_rules.py (rows, attribute names with distinct counts, declared key), answered three times
  published  reference: the published design of e3/data (gold_design), where there is one

Both are judged as in bench.py, under the reachable truth (sigma0 plus the true candidates in scope, reach_good) and
under the gold Sigma* (gold_good); a design is good when it is lossless, dependency-preserving and in 3NF for that
truth and has no more tables than the synthesized design of that truth (eps = 0).  The setting is that of tab:bench:
candidates with |X| <= 3, rho_min = 1e-4, no pruning; the threshold uses all candidates in scope (no cap).

Usage:  python baseline_direct.py prompts             writes llm/prompts_design/dNN.txt and llm/design_batches.json
        python baseline_direct.py run [--out F]       threshold baseline, plus the LLM designs in llm/answers_design
"""
import argparse, json, os, sys
import bench, drd
import estimators as EST
from llm_rules import SCREENED

S, E2 = drd.S, drd.E2
HERE = os.path.dirname(os.path.abspath(__file__))
KINDS = ["const", "learned", "cert", "llm:rules", "llmc:rules"]
MAX_LHS, RHO_MIN, EPS = 3, 1e-4, 0

TEMPLATE = """You know how real-world data is structured. A relation has {rows} sample rows. Its attributes, with the number of distinct values in the sample:
{attrs}

Declared key, known to hold: {key}

Task: design a relational schema for this data in third normal form (3NF). Base the design on the functional dependencies (FDs) you believe are genuine rules of this relation's domain. A genuine rule holds in every valid instance because of what the attributes mean, not by coincidence in one sample.

The decomposition must be lossless and preserve every FD you believe is genuine, and it should use as few tables as that allows. Every attribute must appear in some table. Use the exact attribute names above.

Answer with one JSON object and nothing else, of the form
{{"tables": [{{"attributes": ["A1", "A2", "B"], "key": ["A1"]}}], "fds": [{{"lhs": ["A1"], "rhs": "B"}}]}}
where "fds" lists the genuine FDs your design is based on.
"""


def prompts():
    outdir = os.path.join(HERE, "llm", "prompts_design")
    os.makedirs(outdir, exist_ok=True)
    index = {}
    for ds, b in sorted(bench.benches(MAX_LHS).items()):
        if ds in SCREENED or not b["P"]:
            continue
        d = json.load(open(os.path.join(bench.E3, ds + ".json"), encoding="utf-8"))
        names, dv, rows = b["names"], d["distinct_values"], d["instance"]["rows"]
        attrs = "\n".join(f"- {a} ({dv.get(a, '?')} distinct)" for a in names)
        key = ", ".join(sorted({names[x] for f in b["sigma0"] for x in f[0]})) if b["sigma0"] else "none"
        name = f"d{len(index) + 1:02d}"
        with open(os.path.join(outdir, name + ".txt"), "w", encoding="utf-8") as fh:
            fh.write(TEMPLATE.format(rows=rows, attrs=attrs, key=key))
        index[name] = ds
    json.dump(index, open(os.path.join(HERE, "llm", "design_batches.json"), "w", encoding="utf-8"), indent=0)
    with open(os.path.join(HERE, "llm", "design_template.txt"), "w", encoding="utf-8") as fh:
        fh.write(TEMPLATE)
    print(len(index), "relations")


def judge(b, D):
    """metrics of design D (list of attribute-index sets) under the reachable truth and under the gold Sigma*"""
    out = {"tables": len(D), "covers": set().union(*D) == set(b["R"]) if D else False}
    for tag, F in (("reach", b["sigma0"] + b["truth"]), ("gold", b["gold"])):
        sa = E2.atomic_closure(b["R"], F)
        opt = S.design(b["R"], sa, "synthesis")
        m = S.metrics(b["R"], [list(s) for s in D], sa, sa)
        out.update({f"{tag}_lossless": m["lossless"], f"{tag}_preserving": m["u_str"] == 0, f"{tag}_nf3": m["nf3"],
                    f"{tag}_unpreserved": m["u_str"], f"{tag}_opt_tables": len(opt),
                    f"{tag}_good": out["covers"] and m["valid"] and len(D) <= len(opt) + EPS})
        if tag == "reach":
            out["reach_why"] = why(b, D, sa)
    return out


def why(b, D, sa, top=6):
    """readable reasons: true FDs that no table preserves, and 3NF violations inside a table"""
    nm = lambda f: ",".join(sorted(b["names"][x] for x in f[0])) + "->" + b["names"][next(iter(f[1]))]
    local = [f for s in D for f in S.proj(sa, s)]
    unpres = [nm(f) for f in sa if not S.implies(local, f)]
    viol = []
    for s in D:
        p = S.proj(sa, s)
        ks = S.B.minimal_keys(frozenset(s), p)
        prime = set().union(*ks) if ks else set()
        viol += [nm(f) for f in p if not any(k <= f[0] for k in ks) and not f[1] <= prime]
    return {"unpreserved": unpres[:top], "n_unpreserved": len(unpres), "nf3_violations": viol[:top],
            "n_nf3_violations": len(viol)}


def threshold_runs(all_b):
    res = []
    for ds, b in sorted(all_b.items()):
        if not b["P"]:
            continue
        train = [v for k, v in all_b.items() if k != ds]
        truth = set(b["truth"])
        for kind in KINDS:
            if ":" in kind and ds in SCREENED:
                continue
            pi = bench.clip(bench.estimate(b, train, kind), lo=RHO_MIN)
            inst = drd.Instance(b["R"], b["sigma0"], b["P"], pi, list(truth), name=ds)
            D = inst.threshold({}, 0.5)
            acc = {p for p in b["P"] if pi[p] >= 0.5}
            h = inst.close(acc)                             # what the accepted candidates imply
            r = {"dataset": ds, "baseline": "threshold", "estimator": kind, "candidates": len(b["P"]),
                 "true": len(truth), "accepted": len(acc), "accepted_true": len(acc & truth),
                 "implied_false": len(h - truth), "missed_true": len(truth - h), "auc": bench.auc(pi, truth)}
            r.update(judge(b, [set(s) for s in D]))
            res.append(r)
            print(f"{ds:28s} threshold {kind:11s} acc={r['accepted']:4d} fp={r['implied_false']:4d} "
                  f"fn={r['missed_true']:3d} reach_good={r['reach_good']} gold_good={r['gold_good']}", flush=True)
    return res


def llm_runs(all_b, adir):
    index = json.load(open(os.path.join(HERE, "llm", "design_batches.json"), encoding="utf-8"))
    res = []
    for name, ds in sorted(index.items()):
        b = all_b[ds]
        idx = {a: i for i, a in enumerate(b["names"])}
        truth = set(b["truth"])
        for f in sorted(x for x in os.listdir(adir) if x.startswith(name + "_") and x.endswith(".json")):
            ans = json.load(open(os.path.join(adir, f), encoding="utf-8"))
            raw, unknown = [], set()
            for t in ans.get("tables", []):
                attrs = t["attributes"] if isinstance(t, dict) else t
                unknown |= {a for a in attrs if a not in idx}
                raw.append(frozenset(idx[a] for a in attrs if a in idx))
            # canonical clean-up as in synthesis: drop duplicate schemata and those contained in another
            D = [s for s in dict.fromkeys(raw) if s and not any(s < t for t in raw)]
            fds = []
            for g in ans.get("fds", []):
                try:
                    fds.append(S.fd([idx[a] for a in g["lhs"]], idx[g["rhs"]]))
                except (KeyError, TypeError):
                    pass
            stated = {p for p in b["P"] if S.implies(b["sigma0"] + fds, p)}
            reach = b["sigma0"] + b["truth"]
            nm = lambda g: ",".join(sorted(b["names"][x] for x in g[0])) + "->" + b["names"][next(iter(g[1]))]
            pub = published(b)
            r = {"dataset": ds, "baseline": "llm", "estimator": "llm-design", "run": f[:-5], "candidates": len(b["P"]),
                 "true": len(truth), "raw_tables": len(raw), "unknown_attrs": sorted(unknown), "stated_fds": len(fds),
                 "stated_false": [nm(g) for g in fds if not S.implies(reach, g)],   # incl. FDs the data violate
                 "implied_false": len(stated - truth), "missed_true": len(truth - stated),
                 "same_as_published": pub is not None and set(D) == set(pub)}
            r.update(judge(b, D))
            res.append(r)
            print(f"{ds:28s} llm {f:10s} tables={r['tables']} (opt {r['reach_opt_tables']}) "
                  f"lossless={r['reach_lossless']} preserving={r['reach_preserving']} nf3={r['reach_nf3']} "
                  f"reach_good={r['reach_good']} gold_good={r['gold_good']}", flush=True)
    return res


def published(b):
    """the published design of e3/data (the original TPC-H / TPC-DS tables, the SSB snowflakes), None if there is none"""
    d = json.load(open(os.path.join(bench.E3, b["name"] + ".json"), encoding="utf-8"))
    if not d.get("gold_design"):
        return None
    idx = {a: i for i, a in enumerate(b["names"])}
    return [frozenset(idx[a] for a in t["attributes"] if a in idx) for t in d["gold_design"]]


def published_runs(all_b):
    """reference: the published design, judged by the same criterion"""
    res = []
    for ds, b in sorted(all_b.items()):
        D = published(b) if b["P"] else None
        if D is None:
            continue
        r = {"dataset": ds, "baseline": "published", "estimator": "published", "candidates": len(b["P"]),
             "true": len(b["truth"])}
        r.update(judge(b, D))
        res.append(r)
        print(f"{ds:28s} published tables={r['tables']} reach_good={r['reach_good']} gold_good={r['gold_good']}")
    return res


def audit(tdir):
    """check the subagent transcripts: one Read of the prompt, one Write of the answer, nothing else"""
    import glob
    out, ok = {}, True
    for meta in sorted(glob.glob(os.path.join(tdir, "agent-*.meta.json"))):
        desc = json.load(open(meta, encoding="utf-8")).get("description", "")
        if not desc.startswith("Design d"):
            continue
        name, run = desc.split()[1], desc.split()[-1]
        calls, models = [], set()
        for line in open(meta.replace(".meta.json", ".jsonl"), encoding="utf-8"):
            m = json.loads(line).get("message", {})
            if isinstance(m, dict) and isinstance(m.get("content"), list):
                if m.get("model"):
                    models.add(m["model"])
                calls += [(c["name"], os.path.basename(c["input"].get("file_path", ""))) for c in m["content"]
                          if c.get("type") == "tool_use" and c["name"] != "SubagentHandback"]
        clean = calls == [("Read", name + ".txt"), ("Write", f"{name}_{run}.json")]
        ok &= clean
        out[f"{name}_{run}"] = {"calls": calls, "models": sorted(models), "clean": clean}
    json.dump(out, open(os.path.join(HERE, "llm", "design_audit.json"), "w", encoding="utf-8"), indent=1)
    print(f"{len(out)} transcripts, all clean: {ok}; models: {sorted({m for v in out.values() for m in v['models']})}")
    for k, v in sorted(out.items()):
        if not v["clean"]:
            print("  not clean:", k, v["calls"])


def table(res):
    cols = [("threshold", k) for k in KINDS] + [("llm", "llm-design"), ("published", "published")]
    cell = {}
    for r in res:
        cell.setdefault((r["dataset"], r["baseline"], r["estimator"]), []).append(r)
    print("\nreach_good (gold_good) per data set; llm-design: good runs / runs")
    print(f"{'data set':28s} " + " ".join(f"{k:>11s}" for _, k in cols))
    tot = {c: [0, 0] for c in cols}
    for ds in sorted({r["dataset"] for r in res}):
        row = []
        for c in cols:
            rs = cell.get((ds,) + c, [])
            if not rs:
                row.append("-")
                continue
            g, gg = sum(r["reach_good"] for r in rs), sum(r["gold_good"] for r in rs)
            tot[c][0] += g
            tot[c][1] += len(rs)
            row.append(("yes" if g else "no") + ("" if g == gg else "*") if len(rs) == 1 else f"{g}/{len(rs)}"
                       + ("" if g == gg else f"({gg})"))
        print(f"{ds:28s} " + " ".join(f"{x:>11s}" for x in row))
    print(f"{'good / judged':28s} " + " ".join(f"{f'{g}/{n}':>11s}" for g, n in tot.values()))
    print("* or (n): gold_good differs from reach_good")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prompts", "audit", "run"])
    ap.add_argument("--answers", default=os.path.join(HERE, "llm", "answers_design"))
    ap.add_argument("--transcripts", help="folder of elicitation transcripts to audit")
    ap.add_argument("--out", default=os.path.join(HERE, "baseline_direct.json"))
    a = ap.parse_args()
    if a.cmd == "prompts":
        return prompts()
    if a.cmd == "audit":
        return audit(a.transcripts)
    all_b = bench.benches(MAX_LHS)
    res = threshold_runs(all_b)
    if os.path.isdir(a.answers):
        res += llm_runs(all_b, a.answers)
    res += published_runs(all_b)
    json.dump({"setting": {"max_lhs": MAX_LHS, "rho_min": RHO_MIN, "eps": EPS, "threshold": 0.5, "prune": 0},
               "runs": res}, open(a.out, "w", encoding="utf-8"), indent=1)
    table(res)


if __name__ == "__main__":
    main()
