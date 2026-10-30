"""
Experiment E2: accidental FDs mined from TPC-H, injected one at a time as false positives.

Sigma* of each TPC-H table is the set of FDs that the specification implies (tpch_truth.json).  The mined FDs are
the minimal FDs that HyFD discovered on the data (mined/<table>-fds.txt, Metanome format, mined in prior work).  A mined FD that Sigma* does not imply is accidental.  Each accidental FD sigma is injected alone,
Sigma_hat = Sigma* + {sigma}; the design is synthesized with classical 3NF synthesis and iCONF by the
engine of baselines.py and evaluated under Sigma* with the damage measures of
sensitivity_bruteforce.py and the mechanisms of Theorem 5.7 (o3_lossiness_check.py).

The brute-force atomic closure of sensitivity_bruteforce.py enumerates all subsets, which is too slow for the 16
columns of lineitem.  atomic_closure() below computes the minimal left-hand sides of A as the minimal keys other
than {A} of Sigma + {A -> R} (Lucchesi-Osborn); --check compares it with the brute force.

Usage:  python e2_tpch.py [--check] [--workers N]
"""
import collections, itertools, json, os, sys, time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import sensitivity_bruteforce as S  # noqa: E402
import o3_lossiness_check as O      # noqa: E402

B = S.B
MODES = S.MODES
TABLES = ["region", "nation", "supplier", "part", "partsupp", "customer", "orders", "lineitem"]


# ---------- input ----------

def load_truth():
    with open(os.path.join(HERE, "tpch_truth.json"), encoding="utf-8") as fh:
        return json.load(fh)["tables"]


def load_mined(table):
    # Metanome text format: "# COLUMN" maps table.column to an id, "# RESULTS" lists lhs ids -> rhs id
    names, fds, sec = {}, [], None
    with open(os.path.join(HERE, "mined", f"{table}-fds.txt"), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("#"):
                sec = line[1:].strip()
            elif line and sec == "COLUMN":
                col, i = line.split("\t")
                names[int(i)] = col.split(".", 1)[1]
            elif line and sec == "RESULTS":
                lhs, rhs = line.split("->")
                fds.append(([names[int(x)] for x in lhs.split(",") if x], names[int(rhs)]))
    return fds


# ---------- FD machinery ----------

def atomic_closure(R, sigma):
    # X -> A is atomic iff X is a minimal key other than {A} of (R, sigma + {A -> R}); same order as S.atomic_closure
    R = frozenset(R)
    out = []
    for a in sorted(R):
        ks = B.minimal_keys(R, list(sigma) + [(frozenset({a}), R)])
        out += [S.fd(k, a) for k in ks if a not in k]
    return sorted(out, key=lambda f: (len(f[0]), sorted(f[0]), sorted(f[1])))


def cl(Z, F):
    return frozenset(B.closure(frozenset(Z), F))


def split(sigma):
    return [S.fd(lhs, a) for lhs, rhs in sigma for a in sorted(rhs)]


# ---------- one table ----------

def setup(table, spec):
    attrs = spec["attributes"]
    idx = {a: i for i, a in enumerate(attrs)}
    R = list(range(len(attrs)))
    st = [(frozenset(idx[a] for a in f["lhs"]), frozenset(idx[a] for a in f["rhs"])) for f in spec["fds"]]
    st_a = atomic_closure(R, st)
    mined = [(frozenset(idx[a] for a in lhs), idx[rhs]) for lhs, rhs in load_mined(table)]
    return attrs, R, st, st_a, mined


def evaluate(job):
    """One accidental FD sigma = X -> a on one table: damage, mechanism and keys, for both algorithms."""
    R, st, st_a, truth, obj_true, X, a = job
    Rs = frozenset(R)
    sigma = S.fd(X, a)
    sh_a = atomic_closure(R, st + [sigma])
    keys_t = B.minimal_keys(Rs, st_a)
    keys_h = B.minimal_keys(Rs, sh_a)
    prime = set().union(*keys_t)
    rec = {"lhs": sorted(X), "rhs": a, "rhs_prime": a in prime,
           "keys_true": len(keys_t), "keys_hat": len(keys_h),
           "new_keys": sum(1 for k in keys_h if cl(k, st_a) != Rs),
           "contaminated": sum(1 for f in sh_a if not S.implies(st_a, f))}
    G = split(st)
    bad = collections.Counter()
    for m in MODES:
        D = [frozenset(s) for s in S.design(R, sh_a, m)]
        mt = S.metrics(R, D, sh_a, st_a)
        star = [cl(s, st_a) for s in D]
        hat = [cl(s, sh_a) for s in D]
        E = [g for s in D for g in S.proj(st_a, s)]
        superkey = any(c == Rs for c in star)
        e_superkey = any(cl(s, E) == Rs for s in D)
        lossless = mt["lossless"]
        if not superkey:
            mech = "key loss"
        elif not lossless:
            mech = "path loss"
        elif not e_superkey:
            mech = "lossless in gap"
        else:
            mech = "lossless"
        ob = S.objective(D, st_a)
        rec[m] = {"over": mt["over"] > 0, "u_loc": mt["u_loc"] > 0, "lossy": not lossless,
                  "not_dp": mt["u_str"] > 0, "not_3nf": not mt["nf3"], "invalid": not mt["valid"],
                  "changed": set(D) != set(truth[m]), "mechanism": mech,
                  "regret": ob["fmax"] - obj_true[m]["fmax"] if mt["valid"] else None,
                  "design": [sorted(s) for s in D]}
        # Theorem 5.7 (o3_lossiness_check.theorem14), checked on every design
        W = O.chase_W(Rs, D, G)
        bad["chase disagrees with metrics"] += any(w == Rs for w in W) != lossless
        for w, c in zip(W, star):
            if not X <= c:
                bad["(a) X-free row misses S*"] += w != c
        for h, c in zip(hat, star):
            if h == Rs:
                bad["(c) hat-superkey: S*=R iff a in S*"] += (c == Rs) != (a in c)
        bad["(c) key-loss criterion"] += (not superkey) != all(a not in c for h, c in zip(hat, star) if h == Rs)
        bad["(c) key loss without new key"] += (not superkey) and rec["new_keys"] == 0
        bad["(c) key loss but lossless"] += (not superkey) and lossless
        bad["(b) E*-superkey but lossy"] += e_superkey and not lossless
        bad["(d) path loss but preserving"] += mech == "path loss" and mt["u_str"] == 0
        for g in st_a:
            if not S.implies(E, g):
                bad["(d) lost FD with X not in Y*"] += not X <= cl(g[0], st_a)
    rec["violations"] = {k: v for k, v in bad.items() if v}
    return rec


def run_table(table, spec, pool):
    attrs, R, st, st_a, mined = setup(table, spec)
    Rs = frozenset(R)
    truth = {m: [frozenset(s) for s in S.design(R, st_a, m)] for m in MODES}
    obj_true = {m: S.objective(truth[m], st_a) for m in MODES}
    implied = [(X, a) for X, a in mined if a in cl(X, st)]
    accidental = [(X, a) for X, a in mined if a not in cl(X, st)]
    # does the mined set (the complete set of minimal FDs of the data) imply every FD of Sigma*?
    data_violates = [f for f in split(st) if not S.implies([S.fd(X, a) for X, a in mined], f)]
    jobs = [(R, st, st_a, truth, obj_true, X, a) for X, a in accidental]
    recs = pool.map(evaluate, jobs, chunksize=8) if pool else list(map(evaluate, jobs))
    # right-hand sides of true non-key FDs (a second true path besides the primary key), and the primary key
    second_path = set().union(*[rhs for lhs, rhs in st if cl(lhs, st) != Rs])
    pk = sorted(st[0][0])
    name = lambda xs: [attrs[x] for x in sorted(xs)]
    for r, (X, a) in zip(recs, accidental):
        r["rhs_second_path"] = a in second_path
        sh = st + [S.fd(X, a)]
        r["pk_proper_subsets_closed"] = all(cl(Y, sh) == frozenset(Y) for k in range(len(pk))
                                            for Y in itertools.combinations(pk, k))
        r["lhs"], r["rhs"] = name(r["lhs"]), attrs[r["rhs"]]
        # compact designs: one string per design, schemata separated by "|"; iCONF only where it differs
        designs = {m: " | ".join(sorted(",".join(name(s)) for s in r[m]["design"])) for m in MODES}
        for m in MODES:
            r[m]["design"] = designs[m] if m == MODES[0] or designs[m] != designs[MODES[0]] else "same"
    return {"attributes": attrs, "n": len(attrs), "primary_key": name(pk),
            "rhs_of_true_nonkey_fds": name(second_path),
            "true_keys": [name(k) for k in B.minimal_keys(Rs, st_a)],
            "true_atomic_closure": len(st_a),
            "true_design": {m: [name(s) for s in truth[m]] for m in MODES},
            "mined": len(mined), "mined_implied_by_truth": len(implied), "accidental": len(accidental),
            "truth_fds_violated_by_mined_data": [f"{','.join(name(f[0]))} -> {name(f[1])[0]}" for f in data_violates],
            "records": recs}


# ---------- summary ----------

def summarize(recs):
    n = len(recs)
    s = {"accidental": n,
         "new_keys": sum(r["new_keys"] > 0 for r in recs),
         "rhs_prime": sum(r["rhs_prime"] for r in recs),
         "new_keys_iff_rhs_prime": all((r["new_keys"] > 0) == r["rhs_prime"] for r in recs),
         "max_keys_hat": max((r["keys_hat"] for r in recs), default=0),
         "rhs_second_path": sum(r["rhs_second_path"] for r in recs),
         "pk_proper_subsets_closed": sum(r["pk_proper_subsets_closed"] for r in recs),
         "iconf_design_differs": sum(r["iconf"]["design"] != "same" for r in recs),
         "lhs_size": dict(sorted(collections.Counter(len(r["lhs"]) for r in recs).items()))}
    for m in MODES:
        c = collections.Counter()
        for r in recs:
            d = r[m]
            for k in ("over", "u_loc", "lossy", "not_dp", "not_3nf", "invalid", "changed"):
                c[k] += d[k]
            c["mech:" + d["mechanism"]] += 1
            c["changed_but_valid"] += d["changed"] and not d["invalid"]
            c["lossy_and_new_key"] += d["lossy"] and r["new_keys"] > 0
            c["lossy_rhs_prime"] += d["lossy"] and r["rhs_prime"]
            c["lossy_rhs_nonprime"] += d["lossy"] and not r["rhs_prime"]
            c["key_loss_rhs_nonprime"] += d["mechanism"] == "key loss" and not r["rhs_prime"]
            c["lossless_rhs_second_path"] += not d["lossy"] and r["rhs_second_path"]
            c["valid_rhs_second_path"] += not d["invalid"] and r["rhs_second_path"]
            c["valid_rhs_other"] += not d["invalid"] and not r["rhs_second_path"]
            if d["regret"] is not None:
                c[f"valid_regret={d['regret']:+d}"] += 1
        s[m] = dict(sorted(c.items()))
        s[m + "_pct"] = {k: round(100 * v / n, 1) for k, v in sorted(c.items())} if n else {}
    return s


def check(truth_spec):
    # fast atomic closure == brute force, on every table except lineitem with every accidental FD,
    # on lineitem for Sigma* and the first 25 accidental FDs, and on 3,000 random schemata
    import random
    bad = total = 0
    for t in TABLES:
        attrs, R, st, st_a, mined = setup(t, truth_spec[t])
        acc = [(X, a) for X, a in mined if a not in cl(X, st)]
        sets = [st] + [st + [S.fd(X, a)] for X, a in (acc[:25] if t == "lineitem" else acc)]
        for sg in sets:
            total += 1
            bad += atomic_closure(R, sg) != S.atomic_closure(R, sg)
        print(f"{t}: {len(sets)} checked")
    rnd = random.Random(1)
    for _ in range(3000):
        R = list(range(rnd.choice([4, 5, 6, 7])))
        sg = S.random_sigma(R, rnd)
        total += 1
        bad += atomic_closure(R, sg) != S.atomic_closure(R, sg)
    print(f"atomic closure check: {bad} mismatches in {total}")
    return bad


if __name__ == "__main__":
    truth_spec = load_truth()
    if "--check" in sys.argv:
        sys.exit(1 if check(truth_spec) else 0)
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else os.cpu_count()
    out = {"tables": {}, "summary": {}}
    t0 = time.time()
    with Pool(workers) as pool:
        for t in TABLES:
            res = run_table(t, truth_spec[t], pool)
            out["tables"][t] = res
            out["summary"][t] = summarize(res["records"])
            print(f"{t}: n={res['n']} mined={res['mined']} accidental={res['accidental']} "
                  f"({time.time() - t0:.0f} s)", flush=True)
    allrecs = [r for t in TABLES for r in out["tables"][t]["records"]]
    out["summary"]["all"] = summarize(allrecs)
    out["summary"]["all_but_lineitem"] = summarize([r for t in TABLES if t != "lineitem"
                                                    for r in out["tables"][t]["records"]])
    viol = collections.Counter()
    for r in allrecs:
        viol.update(r["violations"])
    out["violations_of_theorem"] = dict(viol)
    path = os.path.join(HERE, "results.json")
    recs = {t: out["tables"][t].pop("records") for t in TABLES}
    text = json.dumps(out, ensure_ascii=False, indent=1)
    with open(path, "w", encoding="utf-8") as fh:              # one line per record
        fh.write(text[:-2] + ',\n "records": {\n' + ",\n".join(
            f'  "{t}": [\n' + ",\n".join("   " + json.dumps(r, ensure_ascii=False) for r in recs[t]) + "\n  ]"
            for t in TABLES) + "\n }\n}\n")
    for k in ["all", "all_but_lineitem"] + TABLES:
        print(k, json.dumps(out["summary"][k]["synthesis_pct"]), json.dumps(out["summary"][k]["iconf_pct"]))
    print("violations of Theorem 5.7:", dict(viol))
    print("saved", path)
