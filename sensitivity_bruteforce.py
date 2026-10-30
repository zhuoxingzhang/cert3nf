"""
Brute-force check of single-error sensitivity of 3NF synthesis (paper 1, S1-S3').

Runs the synthesis engine of baselines.py (classical synthesis and iCONF share one elimination
skeleton over the atomic closure) on small random schemas,
injects one false positive (Sigma* + {X->A}) or one false negative (canonical cover minus one FD),
and measures every damage notion of the formalization note against the true Sigma*.

Usage:  python sensitivity_bruteforce.py [instances_per_n] [seed] [ns, e.g. 4,5,6 (default) or 7]
"""
import itertools, json, os, random, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import baselines as B  # noqa: E402

MODES = ["synthesis", "iconf"]


# ---------- FD basics on small schemas ----------

def fd(lhs, a):
    return (frozenset(lhs), frozenset({a}))


def implies(sigma, f):
    return f[1] <= B.closure(f[0], sigma)


def atomic_closure(R, sigma):
    # every X->A with A not in X, A in X+, and X minimal; canonical order (|X|, X, A)
    R = sorted(R)
    out = []
    for a in R:
        found = []
        rest = [b for b in R if b != a]
        for k in range(len(rest) + 1):
            for X in itertools.combinations(rest, k):
                X = frozenset(X)
                if any(Y <= X for Y in found):
                    continue
                if a in B.closure(X, sigma):
                    found.append(X)
        out += [fd(X, a) for X in found]
    return sorted(out, key=lambda f: (len(f[0]), sorted(f[0]), sorted(f[1])))


def canonical_cover(sigma_a):
    # the elimination skeleton in list order: what "synthesis" keeps
    work = list(sigma_a)
    for f in list(sigma_a):
        if B.is_redundant(f, work):
            work.remove(f)
    return work


def design(R, sigma_a, mode):
    keys = B.minimal_keys(frozenset(R), sigma_a)
    D = B.synthesize(R, sigma_a, keys, mode)
    return [S for S, _ in D]


# ---------- damage measures relative to the true Sigma* ----------

def lossless(R, schemas, sigma):
    # tableau chase with sigma; True iff some row becomes all-distinguished
    R = sorted(R)
    rows = [{a: (0, a) if a in S else (1, i, a) for a in R} for i, S in enumerate(schemas)]
    changed = True
    while changed:
        changed = False
        for lhs, rhs in sigma:
            (a,) = tuple(rhs)
            groups = collections.defaultdict(list)
            for r in rows:
                groups[tuple(r[x] for x in sorted(lhs))].append(r)
            for g in groups.values():
                vals = {r[a] for r in g}
                if len(vals) > 1:
                    target = min(vals)  # (0, a) distinguished sorts first
                    for r in rows:      # rename globally in column a
                        if r[a] in vals and r[a] != target:
                            r[a] = target
                            changed = True
    return any(all(r[a] == (0, a) for a in R) for r in rows)


def proj(sigma_a, S):
    return B.projection(sigma_a, frozenset(S))


def is_3nf(S, p):
    # every non-trivial atomic X->A of the projection has X superkey or A prime
    S = frozenset(S)
    ks = B.minimal_keys(S, p)
    prime = set().union(*ks) if ks else set()
    for lhs, rhs in p:
        if not rhs <= lhs and not any(k <= lhs for k in ks) and not rhs <= prime:
            return False
    return True


def metrics(R, schemas, sh_a, st_a):
    """sh_a: atomic closure of the estimate; st_a: atomic closure of the truth."""
    local_hat = [f for S in schemas for f in proj(sh_a, S)]
    local_true = [f for S in schemas for f in proj(st_a, S)]
    over = sum(1 for f in local_hat if not implies(st_a, f))            # unsound local constraints
    u_loc = sum(1 for S in schemas for f in proj(st_a, S)
                if not implies(proj(sh_a, S), f))                       # true FD inside a schema, not declared
    u_str = sum(1 for f in st_a if not implies(local_true, f))         # true FD not preserved at all
    ll = lossless(R, schemas, st_a)
    nf3 = all(is_3nf(S, proj(st_a, S)) for S in schemas)
    return {"lossless": ll, "over": over, "u_loc": u_loc, "u_str": u_str, "nf3": nf3,
            "valid": ll and u_str == 0 and nf3}


def suff_lossless(R, schemas, st_a):
    # sufficient condition: some schema contains a key of (R, Sigma*) and the schemas embed a cover
    keys = B.minimal_keys(frozenset(R), st_a)
    has_key = any(any(k <= frozenset(S) for k in keys) for S in schemas)
    emb = [f for f in st_a if any(f[0] | f[1] <= frozenset(S) for S in schemas)]
    return has_key and all(implies(emb, f) for f in st_a)


def robust_design(R, C, P):
    # schemas XA for a cover of C and for every candidate in P, maximal ones, plus a key of (R, C)
    Ca = atomic_closure(R, C)
    fds = canonical_cover(Ca) + list(P)
    S = {f[0] | f[1] for f in fds}
    S = [x for x in S if not any(x < y for y in S)]
    keys = B.minimal_keys(frozenset(R), Ca)
    if not any(any(k <= x for k in keys) for x in S):
        S.append(min(keys, key=len))
    return S


def check_robust(R, rnd, trials):
    # Proposition (robust design): lossless and DP for every Sigma in the box C <= Sigma <= C u P
    bad = collections.Counter()
    for _ in range(trials):
        C = random_sigma(R, rnd)[:rnd.randint(1, 3)]
        Ca = atomic_closure(R, C)
        P = [f for f in random_sigma(R, rnd) if not implies(Ca, f)][:3]
        D = robust_design(R, C, P)
        for k in range(len(P) + 1):
            for sub in itertools.combinations(P, k):
                Sa = atomic_closure(R, C + list(sub))
                local = [f for S in D for f in proj(Sa, S)]
                bad["boxes"] += 1
                bad["lossy"] += not lossless(R, D, Sa)
                bad["not_dp"] += not all(implies(local, f) for f in Sa)
                bad["not_3nf"] += not all(is_3nf(S, proj(Sa, S)) for S in D)
    return bad


def objective(schemas, st_a):
    # iCONF / CONF objectives evaluated under the truth
    fmax = kmax = crit = 0
    for S in schemas:
        S = frozenset(S)
        p = proj(st_a, S)
        ks = B.minimal_keys(S, p)
        nk = B.mixed_nonkey_fds(S, p, ks)
        fmax, kmax = max(fmax, len(nk)), max(kmax, len(ks))
        crit += bool(nk)
    return {"fmax": fmax, "kmax": kmax, "crit": crit}


def refines(D1, D2):
    return all(any(set(a) <= set(b) for b in D2) for a in D1)


# ---------- experiment ----------

def random_sigma(R, rnd):
    m = rnd.randint(2, len(R) + 1)
    out = []
    for _ in range(m):
        a = rnd.choice(R)
        lhs = rnd.sample([b for b in R if b != a], rnd.choice([1, 1, 2, 2, 3]) if len(R) > 3 else 1)
        out.append(fd(lhs, a))
    return out


def run(per_n=300, seed=1, ns=(4, 5, 6), fp_per=12):
    rnd = random.Random(seed)
    stats = collections.Counter()
    worst = {}
    examples = collections.defaultdict(list)
    keyratio = [1.0, 1.0]
    for n in ns:
        R = list(range(n))
        for _ in range(per_n):
            st_a = atomic_closure(R, random_sigma(R, rnd))
            if not st_a:
                continue
            true_keys = len(B.minimal_keys(frozenset(R), st_a))
            truth = {m: design(R, st_a, m) for m in MODES}
            obj_true = {m: objective(truth[m], st_a) for m in MODES}
            # --- errors ---
            fps = [fd(X, a) for a in R for k in (1, 2) for X in itertools.combinations([b for b in R if b != a], k)
                   if not implies(st_a, fd(X, a))]
            rnd.shuffle(fps)
            G = canonical_cover(st_a)
            errors = [("FP", f, st_a + [f]) for f in fps[:fp_per]] + \
                     [("FN", g, [h for h in G if h != g]) for g in G]
            for kind, f, sh in errors:
                sh_a = atomic_closure(R, sh)
                kr = len(B.minimal_keys(frozenset(R), sh_a)) / true_keys
                if kr > keyratio[1] or kr < keyratio[0]:
                    examples["key_ratio_extreme"].append({"R": n, "truth": show(G), "error": kind + " " + show([f])[0],
                                                          "ratio": kr, "keys_true": true_keys})
                keyratio = [min(keyratio[0], kr), max(keyratio[1], kr)]
                for m in MODES:
                    D = design(R, sh_a, m)
                    mt = metrics(R, D, sh_a, st_a)
                    ob = objective(D, st_a)
                    same = set(map(frozenset, D)) == set(map(frozenset, truth[m]))
                    tag = f"{kind}/{m}"
                    stats[tag + "/total"] += 1
                    stats[tag + "/lossy"] += not mt["lossless"]
                    stats[tag + "/over>0"] += mt["over"] > 0
                    stats[tag + "/uloc>0"] += mt["u_loc"] > 0
                    stats[tag + "/ustr>0"] += mt["u_str"] > 0
                    stats[tag + "/struct_changed"] += not same
                    stats[tag + "/invalid_wrt_truth"] += not mt["valid"]
                    stats[tag + "/not3nf_wrt_truth"] += not mt["nf3"]
                    stats[tag + "/changed_but_valid"] += (not same) and mt["valid"]
                    if kind == "FP":
                        sl = suff_lossless(R, D, st_a)
                        stats[tag + "/suff_cond_holds"] += sl
                        stats[tag + "/lossless_without_suff"] += mt["lossless"] and not sl
                        if sl and not mt["lossless"]:
                            examples["suff_cond_but_lossy(should_not_exist)"].append({"error": show([f])})
                    if mt["valid"]:
                        regv = ob["fmax"] - obj_true[m]["fmax"]
                        stats[tag + f"/valid_fmax_regret={regv:+d}"] += 1
                        if regv > 0 and len(examples[f"{kind}_valid_regret/{m}"]) < 3:
                            examples[f"{kind}_valid_regret/{m}"].append(
                                {"truth": show(G), "error": show([f]), "D_true": [sorted(S) for S in truth[m]],
                                 "D_est": [sorted(S) for S in D], "regret": regv})
                    stats[tag + "/truth_refines_est"] += refines(truth[m], D)
                    stats[tag + "/est_refines_truth"] += refines(D, truth[m])
                    reg = ob["fmax"] - obj_true[m]["fmax"]
                    stats[tag + f"/fmax_regret={reg:+d}"] += 1
                    stats[tag + "/kmax_regret>0"] += ob["kmax"] > obj_true[m]["kmax"]
                    worst[tag] = max(worst.get(tag, -99), reg)
                    # record small counterexamples for the note
                    rec = {"R": n, "truth": show(G), "error": show([f]),
                           "D_true": [sorted(S) for S in truth[m]], "D_est": [sorted(S) for S in D], **mt}
                    if kind == "FN" and not mt["lossless"]:
                        examples["FN_lossy(should_not_exist)"].append(rec)
                    if kind == "FP" and mt["over"] == 0:
                        examples["FP_no_over(should_not_exist)"].append(rec)
                    if kind == "FN" and mt["over"] > 0:
                        examples["FN_over(should_not_exist)"].append(rec)
                    if kind == "FP" and not mt["lossless"] and len(examples[f"FP_lossy/{m}"]) < 3:
                        examples[f"FP_lossy/{m}"].append(rec)
                    if kind == "FN" and not refines(truth[m], D) and len(examples[f"FN_truth_not_refines/{m}"]) < 3:
                        examples[f"FN_truth_not_refines/{m}"].append(rec)
                    if kind == "FP" and not refines(D, truth[m]) and len(examples[f"FP_est_not_refines/{m}"]) < 3:
                        examples[f"FP_est_not_refines/{m}"].append(rec)
                    if kind == "FN" and mt["u_str"] == 0 and len(examples[f"FN_local_only/{m}"]) < 3:
                        examples[f"FN_local_only/{m}"].append(rec)
                    if reg > 0 and len(examples[f"{kind}_fmax_regret/{m}"]) < 3:
                        examples[f"{kind}_fmax_regret/{m}"].append({**rec, "regret": reg})
    return stats, worst, examples, keyratio


def show(fds):
    letters = "ABCDEFGH"
    return [("".join(letters[x] for x in sorted(l)) or "∅") + "->" + letters[next(iter(r))] for l, r in fds]


if __name__ == "__main__":
    per_n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    ns = tuple(int(x) for x in sys.argv[3].split(",")) if len(sys.argv) > 3 else (4, 5, 6)
    stats, worst, examples, keyratio = run(per_n, seed, ns)
    rob = check_robust(list(range(5)), random.Random(seed), per_n) if ns == (4, 5, 6) else {}
    print("robust design check (n=5):", dict(rob))
    examples["key_ratio_extreme"] = examples["key_ratio_extreme"][-4:]
    out = {"stats": dict(sorted(stats.items())), "robust_check": dict(rob), "worst_fmax_regret": worst,
           "key_count_ratio_range": keyratio,
           "examples": {k: v[:3] for k, v in examples.items()},
           "violations_of_proved_props": {k: len(v) for k, v in examples.items() if "should_not_exist" in k}}
    suffix = "" if ns == (4, 5, 6) else "_n" + "-".join(map(str, ns))
    path = os.path.join(HERE, f"bruteforce_results{suffix}_seed{seed}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    for k, v in sorted(stats.items()):
        print(f"{k:45s} {v}")
    print("worst fmax regret:", worst, "key ratio range:", keyratio)
    print("violations of proved props:", out["violations_of_proved_props"])
    print("saved", path)
