"""
Estimators for the E3 benchmarks, and the certificate cost that judges them.

Features of a candidate X -> A (columns of bench.load's X):
  0-6   data statistics: intercept, |X|, redundancy share, X unique, log distinct counts of X and A and their difference
  7-11  column names: X holds an identifier-like name, A does, A shares its table prefix with an attribute of X,
        A's prefix differs from all prefixes of X, Jaccard overlap of the remaining name tokens of X and A

Estimators (trained on the other data sets, every data set weighted equally):
  learned  logistic regression on the statistics (the earlier baseline)
  names    logistic regression on statistics and names
  cert     the same model trained for the certificate: it minimizes a smooth count of the accidental candidates that a
           certificate would still have to ask about, plus a heavy penalty on true candidates whose probability falls
           below the per-candidate risk budget, plus a small log loss that keeps the probabilities calibrated

Certificate cost (Theorem 18 without implications): ask the candidates in decreasing probability until the unasked
ones carry total weight sum -ln(1 - rho) <= -ln(1 - delta).  The cost is the number asked; the certificate is unsafe
when a true candidate stays unasked.  Probabilities are floored at rho_min, which caps the unasked candidates at
-ln(1 - delta) / -ln(1 - rho_min).
"""
import math
import numpy as np

IDT = {"id", "key", "sk", "num", "number", "no", "nr", "code", "identif", "ident"}


def _idlike(tokens):
    return any(t in IDT or (len(t) > 3 and (t.endswith("key") or t.endswith("id"))) for t in tokens)


def _prefix(tokens):
    return tokens[0] if len(tokens) >= 2 and len(tokens[0]) <= 2 else None


def name_features(f):
    lhs = f.get("lhs_tokens") or []
    rhs = f.get("rhs_tokens") or []
    lhs_id = 1.0 if any(_idlike(t) for t in lhs) else 0.0
    rhs_id = 1.0 if _idlike(rhs) else 0.0
    rp = _prefix(rhs)
    lps = [_prefix(t) for t in lhs]
    same = 1.0 if rp is not None and rp in lps else 0.0
    diff = 1.0 if rp is not None and lps and all(p is not None and p != rp for p in lps) else 0.0
    core = lambda ts: {t for t in ts if t != _prefix(ts)}
    a, b = set().union(*[core(t) for t in lhs]) if lhs else set(), core(rhs)
    overlap = len(a & b) / len(a | b) if a | b else 0.0
    return [lhs_id, rhs_id, same, diff, overlap]


# ---------------- training ----------------
def _design(train, cols):
    X, y, w = [], [], []
    for b in train:
        truth = set(b["truth"])
        n = max(len(b["P"]), 1)
        for p in b["P"]:
            X.append([b["X"][p][c] for c in cols])
            y.append(1.0 if p in truth else 0.0)
            w.append(1.0 / n)
    return np.array(X), np.array(y), np.array(w)


def fit_weighted_lr(X, y, w, l2=1e-2, iters=100):
    th = np.zeros(X.shape[1])
    W = w / w.sum()
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(X @ th, -30, 30)))
        g = X.T @ (W * (p - y)) + l2 * th
        H = (X.T * (W * p * (1 - p))) @ X + l2 * np.eye(X.shape[1])
        th -= np.linalg.solve(H, g)
    return th


def fit_cert(train, cols, delta=0.1, lam_true=10.0, mu=0.1, kappa=1.0, l2=1e-2, steps=3000, lr=0.05, init=None):
    """decision-focused training: smooth certificate cost per data set, normalized by its number of candidates"""
    blocks = []
    for b in train:
        if not b["P"]:
            continue
        truth = set(b["truth"])
        Xd = np.array([[b["X"][p][c] for c in cols] for p in b["P"]])
        yd = np.array([1.0 if p in truth else 0.0 for p in b["P"]])
        tau = -math.log(1 - delta) / len(b["P"])           # per-candidate share of the risk budget
        blocks.append((Xd, yd, math.log(tau / (1 - tau)), len(b["P"])))
    th = np.array(init, dtype=float) if init is not None else np.zeros(len(cols))
    m, v = np.zeros_like(th), np.zeros_like(th)
    sig = lambda z: 1 / (1 + np.exp(-np.clip(z, -30, 30)))
    for t in range(1, steps + 1):
        g = l2 * th
        for Xd, yd, td, n in blocks:
            z = Xd @ th
            s = sig(kappa * (z - td))                       # accidental candidate still above the budget share
            u = sig(kappa * (td - z))                       # true candidate pushed below it
            p = sig(z)
            dz = (1 - yd) * kappa * s * (1 - s) - lam_true * yd * kappa * u * (1 - u) + mu * (p - yd)
            g = g + Xd.T @ dz / n
        m = 0.9 * m + 0.1 * g
        v = 0.999 * v + 0.001 * g * g
        th -= lr * (m / (1 - 0.9 ** t)) / (np.sqrt(v / (1 - 0.999 ** t)) + 1e-8)
    return th


_LLM = {}


def llm_pi(b, tag):
    """the LLM's probabilities for the candidates of b (llm/scores_TAG.json), None if it has none for b"""
    if tag not in _LLM:
        import json, os
        f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm", f"scores_{tag}.json")
        _LLM[tag] = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {}
    rows = _LLM[tag].get(b["name"])
    if rows is None:
        return None
    idx = {(tuple(sorted(l)), r): p for l, r, p in rows}
    names = b["names"]
    return {p: idx.get((tuple(sorted(names[x] for x in p[0])), names[next(iter(p[1]))]), 0.5) for p in b["P"]}


def _logit(v, lo=1e-4):
    v = min(max(v, lo), 1 - lo)
    return math.log(v / (1 - v))


def estimate_llm(target, train, kind, delta=0.1):
    """llm:TAG the LLM's probabilities as they are; llmc:TAG the logit of the LLM's probability as one more feature of
    the cert model, trained on the other data sets the LLM scored"""
    base, tag = kind.split(":")
    L = llm_pi(target, tag)
    if L is None:
        raise ValueError(f"no LLM scores {tag} for {target['name']}")
    if base == "llm":
        return dict(L)
    aug = lambda b, Lb: dict(b, X={p: b["X"][p] + [_logit(Lb[p])] for p in b["P"]})
    tr = [aug(b, Lb) for b in train for Lb in [llm_pi(b, tag)] if Lb is not None]
    cols = list(range(13))
    X, y, w = _design(tr, cols)
    th = fit_weighted_lr(X, y, w)
    th = fit_cert(tr, cols, delta=delta, init=th)
    t = aug(target, L)
    z = lambda p: float(np.dot(th, [t["X"][p][c] for c in cols]))
    return {p: 1 / (1 + math.exp(-max(min(z(p), 30), -30))) for p in target["P"]}


def estimate(target, train, kind, delta=0.1):
    if ":" in kind:
        return estimate_llm(target, train, kind, delta)
    truth_rate = sum(len(b["truth"]) for b in train) / max(1, sum(len(b["P"]) for b in train))
    if kind == "const":
        return {p: truth_rate for p in target["P"]}
    cols = list(range(7)) if kind == "learned" else list(range(12))
    X, y, w = _design(train, cols)
    if kind == "learned":
        w = np.ones_like(w)                                 # the earlier baseline: every candidate weighted equally
    th = fit_weighted_lr(X, y, w)
    if kind == "cert":
        th = fit_cert(train, cols, delta=delta, init=th)
    z = lambda p: float(np.dot(th, [target["X"][p][c] for c in cols]))
    return {p: 1 / (1 + math.exp(-max(min(z(p), 30), -30))) for p in target["P"]}


# ---------------- judging ----------------
def cert_cost(pi, truth, delta=0.1, rho_min=0.0, rho_max=1.0):
    """questions until the unasked candidates fit the risk budget, asking in decreasing probability (no implications)"""
    budget = -math.log(1 - delta)
    rs = sorted(((min(max(v, rho_min), rho_max), p) for p, v in pi.items()), key=lambda t: t[0])
    unasked, used = [], 0.0
    for v, p in rs:                                         # the smallest probabilities stay unasked while they fit
        w = -math.log(1 - v) if v < 1 else float("inf")
        if used + w > budget:
            break
        used += w
        unasked.append(p)
    return len(pi) - len(unasked), any(p in truth for p in unasked)
