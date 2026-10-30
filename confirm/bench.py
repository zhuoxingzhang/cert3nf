"""
Confirmation on the E3 benchmarks (denormalized TPC-H and SSB, gold Sigma* from the specifications, mined FDs with
data features; built by ../e3/build.py) with estimators learned from data.

Instance: sigma0 = the primary-key FDs of the table, candidates = the mined minimal FDs that sigma0 does not imply,
oracle = the gold Sigma*.  Estimators (probabilities for the candidates of one data set, trained on the others):
  const      the base rate of true candidates on the training sets
  redundancy logistic regression on the share of rows that X -> A makes redundant (after Wei and Link)
  learned    logistic regression on all features (lhs size, redundancy share, lhs unique, distinct ratios)
Pruning with a risk budget (Theorem 18): the candidates of smallest probability are treated as false as long as
their total weight sum -ln(1 - rho) stays within -ln(1 - delta_prune); the policy then runs with delta - delta_prune.
A cap on the candidates (--max-cand) is pruning too (--cap risk, prune_risk): the candidates beyond it are dropped
while their weight fits a share of the risk, which is charged to delta_left, and the policy runs with
delta - delta_left.  --cap force drops them outside the guarantee (the setting of tab:bench, --max-cand 250).
Every run reports delta_cert, delta_left, risk_forced and the resulting guarantee.
Final designs are judged under the gold Sigma* (not only under the candidates that were kept).

Usage:  python bench.py [--datasets ...] [--estimators const,redundancy,learned] [--policies drd,marg,pi]
                        [--delta 0.1] [--prune 0.05] [--seeds 3] [--workers 8] [--max-cand 0] [--cap risk]
"""
import argparse, glob, json, math, os, statistics, sys, time, zlib
from multiprocessing import Pool
import numpy as np
import drd
import estimators as EST
S, E2 = drd.S, drd.E2
E3 = os.path.join(drd.HERE, "..", "e3", "data")


def datasets():
    return sorted(os.path.basename(f)[:-5] for f in glob.glob(os.path.join(E3, "*.json")))


def features(f, rows):
    lg = lambda v: math.log(max(v, 1)) / math.log(max(rows, 2))
    return [1.0, f["lhs_size"], f["redundancy"] / rows, 1.0 if f["lhs_unique"] else 0.0,
            lg(f["distinct_lhs"]), lg(f["distinct_rhs"]), lg(f["distinct_lhs"]) - lg(f["distinct_rhs"])]


def load(ds, max_lhs=None):
    with open(os.path.join(E3, ds + ".json"), encoding="utf-8") as fh:
        d = json.load(fh)
    names = d["attributes"]
    idx = {a: i for i, a in enumerate(names)}
    R = list(range(len(names)))
    gold = [S.fd([idx[a] for a in t["lhs"]], idx[r]) for t in d["truth"] for r in t["rhs"] if idx[r] not in [idx[a] for a in t["lhs"]]]
    # sigma0: the declared key, the first gold left-hand side that is a superkey under the gold FDs; none for keyless sets
    pk = next(([idx[a] for a in t["lhs"]] for t in d["truth"]
               if S.B.closure(frozenset(idx[a] for a in t["lhs"]), gold) >= frozenset(R)), None)
    sigma0 = [S.fd(pk, x) for x in R if x not in pk] if pk else []
    rows = d["instance"]["rows"]
    cands, X, truth = [], {}, []
    for f in d["fds"]:
        p = S.fd([idx[a] for a in f["lhs"]], idx[f["rhs"]])
        if max_lhs is not None and len(f["lhs"]) > max_lhs:     # candidate scope: small left-hand sides
            continue
        if p in X or S.implies(sigma0, p):
            continue
        cands.append(p)
        X[p] = features(f, rows) + EST.name_features(f)    # columns 7-11: column names (estimators.py)
        if f["implied_by_truth"]:
            truth.append(p)
    out_scope = sum(1 for f in d["fds"] if f["implied_by_truth"] and max_lhs is not None and len(f["lhs"]) > max_lhs)
    return {"name": ds, "R": R, "names": names, "sigma0": sigma0, "gold": gold, "P": cands, "X": X, "truth": truth,
            "true_out_of_scope": out_scope}


def fit_logistic(Xs, ys, l2=1e-2, iters=200):
    X, y = np.array(Xs, dtype=float), np.array(ys, dtype=float)
    w = np.zeros(X.shape[1])
    for _ in range(iters):           # Newton steps
        p = 1 / (1 + np.exp(-X @ w))
        g = X.T @ (p - y) / len(y) + l2 * w
        H = (X.T * (p * (1 - p))) @ X / len(y) + l2 * np.eye(X.shape[1])
        w -= np.linalg.solve(H, g)
    return w


def estimate(target, train, kind):
    if kind in ("names", "cert") or ":" in kind:
        return EST.estimate(target, train, kind)
    ys = [p in set(b["truth"]) for b in train for p in b["P"]]
    if kind == "const":
        rate = sum(ys) / len(ys)
        return {p: rate for p in target["P"]}
    cols = [0, 2] if kind == "redundancy" else list(range(7))
    Xs = [[b["X"][p][c] for c in cols] for b in train for p in b["P"]]
    w = fit_logistic(Xs, ys)
    return {p: float(1 / (1 + np.exp(-np.dot(w, [target["X"][p][c] for c in cols])))) for p in target["P"]}


def clip(pi, lo=0.005, hi=0.98):
    """the floor lo caps the candidates a certificate can leave unasked at -ln(1 - delta) / -ln(1 - lo) (Theorem 18)"""
    return {p: min(hi, max(lo, v)) for p, v in pi.items()}


def tiekey(p):
    """a fixed order among equally likely candidates, independent of the order of the mined file: smaller left-hand
    side first, then a hash (the mined file lists attributes in schema order, which correlates with keys)"""
    return (len(p[0]), zlib.crc32(repr((sorted(p[0]), sorted(p[1]))).encode()))


def prune(pi, delta_prune, max_cand):
    """keep the candidates of largest probability; drop the rest while their weight fits the risk budget
    (ties broken by tiekey, not by the order of the mined file)"""
    order = sorted(pi, key=lambda p: (pi[p], [-k for k in tiekey(p)]))
    budget, dropped = -math.log(1 - delta_prune) if delta_prune > 0 else 0.0, set()
    for p in order:
        w = -math.log(1 - pi[p])
        if w > budget:
            break
        budget -= w
        dropped.add(p)
    kept = [p for p in pi if p not in dropped]
    forced = []
    if 0 < max_cand < len(kept):  # over the cap: drop more, outside the guarantee (reported; --cap force)
        kept = sorted(kept, key=lambda p: (-pi[p], tiekey(p)))[:max_cand]
        forced = [p for p in pi if p not in dropped and p not in kept]
    return kept, dropped, forced


def prune_risk(pi, delta_prune, max_cand, delta, share=0.5):
    """prune as above, then treat a cap on the candidates (max_cand > 0) as more pruning: beyond the cap, the candidates
    of smallest probability are dropped as long as the total dropped weight W stays within -ln(1 - delta_cap), with
    delta_cap = delta_prune + share * (delta - delta_prune); those that do not fit are kept above the cap.  By the
    union bound of pruning, a dropped candidate holds with probability at most delta_left = max(delta_prune,
    1 - exp(-W)), and Confirm certifies with delta - delta_left, so the guarantee stays delta.  Returns kept, dropped,
    delta_left and the number of candidates kept above the cap."""
    kept, dropped, _ = prune(pi, delta_prune, 0)
    w = sum(-math.log(1 - pi[p]) for p in dropped)
    left, over = delta_prune, 0
    if 0 < max_cand < len(kept):
        limit = -math.log(1 - (delta_prune + share * (delta - delta_prune)))
        rest = sorted(kept, key=lambda p: (-pi[p], tiekey(p)))
        n = len(rest)
        while n > max_cand:
            x = -math.log(1 - pi[rest[n - 1]])
            if w + x > limit:
                break
            w += x
            dropped.add(rest[n - 1])
            n -= 1
        kept = [p for p in pi if p not in dropped]
        left, over = max(delta_prune, 1 - math.exp(-w)), n - max_cand
    return kept, dropped, left, over


def mem_mb():
    """resident and peak memory of this process in MB (Linux, Windows), else None"""
    try:
        with open("/proc/self/status") as fh:
            st = dict(line.split(":", 1) for line in fh)
        return round(int(st["VmRSS"].split()[0]) / 1024), round(int(st["VmHWM"].split()[0]) / 1024)
    except (OSError, KeyError, ValueError):
        pass
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (f, ctypes.c_size_t) for f in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                               "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                               "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
        c = PMC()
        c.cb = ctypes.sizeof(c)
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb)
        return round(c.WorkingSetSize / 2 ** 20), round(c.PeakWorkingSetSize / 2 ** 20)
    except (AttributeError, OSError):
        return None, None


def gold_eval(b, D, eps):
    sa = E2.atomic_closure(b["R"], b["gold"])
    opt = S.design(b["R"], sa, "synthesis")
    m = S.metrics(b["R"], [list(s) for s in D], sa, sa)
    return {"gold_valid": m["valid"], "gold_lossless": m["lossless"], "gold_nf3": m["nf3"], "gold_preserving": m["u_str"] == 0,
            "gold_extra": len(D) - len(opt), "gold_good": m["valid"] and len(D) <= len(opt) + eps}


def reach_eval(b, D, eps):
    """good under the reachable truth: sigma0 plus every true candidate in scope (also those pruned), which is what
    the certificate speaks about; the gold Sigma* may contain FDs that no candidate expresses"""
    sa = E2.atomic_closure(b["R"], b["sigma0"] + b["truth"])
    opt = S.design(b["R"], sa, "synthesis")
    m = S.metrics(b["R"], [list(s) for s in D], sa, sa)
    return m["valid"] and len(D) <= len(opt) + eps


def auc(pi, truth):
    pos = [pi[p] for p in pi if p in truth]
    neg = [pi[p] for p in pi if p not in truth]
    if not pos or not neg:
        return None
    neg_sorted = sorted(neg)
    import bisect
    wins = sum(bisect.bisect_left(neg_sorted, x) + 0.5 * (bisect.bisect_right(neg_sorted, x) - bisect.bisect_left(neg_sorted, x)) for x in pos)
    return wins / (len(pos) * len(neg))


_CACHE = {}
PROBE = 0
AUDIT = 10       # audit questions for the policies with the suffix +a


def benches(max_lhs=None):
    # loaded once per worker process and scope
    if max_lhs not in _CACHE:
        _CACHE[max_lhs] = {}
        for d in datasets():
            try:
                _CACHE[max_lhs][d] = load(d, max_lhs)
            except (IndexError, KeyError, ValueError):   # a data set that ../e3/build.py is still writing
                pass
    return _CACHE[max_lhs]


def job(args):
    ds, kind, policy, delta, delta_prune, seed, max_cand, eps = args[:8]
    max_lhs = args[8] if len(args) > 8 else None
    rho_min = args[9] if len(args) > 9 else 0.005
    cap = args[10] if len(args) > 10 else "force"     # the cap of tab:bench
    share = args[11] if len(args) > 11 else 0.5
    all_b = benches(max_lhs)
    b = all_b[ds]
    pi = clip(estimate(b, [v for k, v in all_b.items() if k != ds], kind), lo=rho_min)
    truth = set(b["truth"])
    t = time.time()
    answers0 = {}
    if "+r" in policy and PROBE > 0:
        # probe (off by default): a few random candidates calibrate the estimator before it is trusted for pruning;
        # with rare true FDs the probe sees none, the recalibrated prior collapses, and pruning drops true FDs
        rnd = __import__("random").Random(1000 + seed)
        probe = rnd.sample(b["P"], min(PROBE, len(b["P"])))
        answers0 = {p: p in truth for p in probe}
        prior = drd.recalibrated(pi, answers0)
        kept, dropped, forced = prune({p: v for p, v in prior.items() if p not in answers0}, delta_prune, max_cand - len(probe))
        kept = list(probe) + kept
    elif cap == "risk":
        kept, dropped, delta_left, over = prune_risk(pi, delta_prune, max_cand, delta, share)
        forced = []
    else:
        kept, dropped, forced = prune(pi, delta_prune, max_cand)
    if cap != "risk":
        delta_left, over = delta_prune, 0
    kept = sorted(kept, key=tiekey)   # the policies break ties by this order
    label, flags = policy, policy.split("+")[1:]
    policy = policy.split("+")[0]
    if "a" in flags and kept:
        # audit: random questions among the candidates the estimator is most sure are false (the lower half by rho);
        # chosen at random, they test the estimator's tail without biasing the posterior of the recalibration
        rnd = __import__("random").Random(2000 + seed)
        low = sorted(kept, key=lambda p: (pi[p], tiekey(p)))[:max(1, len(kept) // 2)]
        audit = rnd.sample(low, min(AUDIT, max(1, len(kept) // 4), len(low)))
        answers0 = {p: p in truth for p in audit}
    inst = drd.Instance(b["R"], b["sigma0"], kept, {p: pi[p] for p in kept}, [p for p in kept if p in truth], name=ds,
                        recal="r" in flags)
    out = {"dataset": ds, "estimator": kind, "policy": label, "delta": delta, "prune": delta_prune, "seed": seed,
           "max_lhs": max_lhs, "rho_min": rho_min, "true_out_of_scope": b.get("true_out_of_scope"),
           "eps": eps, "candidates": len(b["P"]), "true": len(truth), "kept": len(kept), "dropped": len(dropped),
           "forced": len(forced), "true_dropped": len(truth & (dropped | set(forced))),
           "auc": auc(pi, truth), "f1": f1(pi, truth)}
    # risk accounting: Confirm certifies with delta_cert; a dropped candidate holds with probability at most
    # delta_left, and a forced one (--cap force) with risk_forced, so a certified design is good with probability at
    # least 1 - guarantee (union bound); with --cap risk, guarantee = delta
    risk_forced = 1 - math.exp(-sum(-math.log(1 - pi[p]) for p in forced))
    delta_cert = max(delta - delta_left, 0.0)
    out.update(cap=cap, max_cand=max_cand, over_cap=over, delta_left=delta_left, delta_cert=delta_cert,
               risk_forced=risk_forced, guarantee=min(1.0, delta_cert + delta_left + risk_forced))
    if policy == "nothing":
        D = inst.threshold({}, 0.5)
        out.update(questions=0, reach_good=reach_eval(b, D, eps), **gold_eval(b, D, eps))
    else:
        r = drd.run(inst, policy, eps, seed=seed, delta=delta_cert, return_design=True,
                    answers0={p: y for p, y in answers0.items() if p in inst.P})
        out.update(questions=r["questions"], cert_good=r["good"], reach_good=reach_eval(b, r["design"], eps),
                   **gold_eval(b, r["design"], eps))
    out["secs"] = round(time.time() - t, 1)
    out["secs_per_q"] = round(out["secs"] / max(out["questions"], 1), 2)
    out["mem_mb"], out["peak_mb"] = mem_mb()
    out["hyp_cached"] = len(inst._hc)
    return out


def f1(pi, truth):
    pred = {p for p in pi if pi[p] >= 0.5}
    tp = len(pred & truth)
    return 2 * tp / (len(pred) + len(truth)) if (pred or truth) else 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", default=",".join(datasets()))
    ap.add_argument("--estimators", default="const,redundancy,learned")
    ap.add_argument("--policies", default="nothing,drd,marg,pi")
    ap.add_argument("--delta", type=float, default=0.1)
    ap.add_argument("--prune", type=float, default=0.05)
    ap.add_argument("--eps", type=int, default=0)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--max-cand", type=int, default=0, help="cap on the candidates (0: none)")
    ap.add_argument("--cap", choices=("risk", "force"), default="risk",
                    help="risk: the cap prunes within the risk budget (prune_risk); force: drop beyond the cap, outside "
                         "the guarantee (tab:bench used --cap force --max-cand 250)")
    ap.add_argument("--cap-share", type=float, default=0.5, help="share of delta - prune the cap may spend (risk)")
    ap.add_argument("--max-lhs", type=int, default=None)
    ap.add_argument("--rho-min", type=float, default=0.005)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=os.path.join(drd.HERE, "bench.json"))
    a = ap.parse_args()
    jobs = [(ds, k, pol, a.delta, a.prune, s, a.max_cand, a.eps, a.max_lhs, a.rho_min, a.cap, a.cap_share)
            for ds in a.datasets.split(",") for k in a.estimators.split(",")
            for pol in a.policies.split(",") for s in (range(a.seeds) if pol not in ("nothing", "pi") else [0])]
    res = []
    with Pool(a.workers) as pool:
        for r in pool.imap_unordered(job, jobs):
            res.append(r)
            print(json.dumps(r), flush=True)
    json.dump(res, open(a.out, "w", encoding="utf-8"), indent=1)
    summarize(res)


def summarize(res):
    by = {}
    for r in res:
        by.setdefault((r["dataset"], r["estimator"], r["policy"]), []).append(r)
    for (ds, k, pol), rs in sorted(by.items()):
        r0 = rs[0]
        print(f"{ds:28s} {k:10s} {pol:8s} cand={r0['candidates']:5d} true={r0['true']:3d} kept={r0['kept']:4d} "
              f"true_dropped={r0['true_dropped']:2d} auc={r0['auc'] if r0['auc'] is None else round(r0['auc'], 2)} f1={r0['f1']:.2f} "
              f"q={statistics.mean(x['questions'] for x in rs):6.1f} gold_good={sum(x['gold_good'] for x in rs)}/{len(rs)} "
              f"valid={sum(x['gold_valid'] for x in rs)}/{len(rs)} extra={statistics.mean(x['gold_extra'] for x in rs):.1f}")


if __name__ == "__main__":
    main()
