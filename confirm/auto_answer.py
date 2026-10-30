"""
Answer models of the automated pipeline (design notes, component selection): how much a recorded answer of the model
says about the truth of a candidate.  Every model gives, for an answered candidate p, the log likelihood ratio
log LR_p = log L(A_p | p true, x_p) - log L(A_p | p false, x_p), which the posterior of auto_noisy adds to the
(recalibrated) prior log-odds.  By Bayes' rule

    log LR(A; x) = logit P(true | A, x) - logit P(true | x),

and both terms are logistic regressions fitted on the same training relations, so their base rates cancel and the
ratio measures only what the answer adds to the data features x.  A model that regresses the truth on the answer with
the prior as offset would also absorb the miscalibration of the prior on the training relations, which the
recalibration of Confirm then corrects a second time (observed on synthetic answers: every candidate ends up true).

  none    log LR = 0: the prior alone, the reference of the log-loss table
  const   the answer only (yes, no, none): constant error rates, assumes the answer independent of x given the truth
  conf    plus the confidence of the answer, logit P(YES) at the answer token (auto_llm.answer_prob), with an indicator
          for an answer whose confidence is missing.  A binary answer discards how sure the model was.
  feat    plus the data features times the answer, so that the error rates may depend on x, and logit P(true | x) on
          the same features: if the model says yes mostly where the statistics already point to true, the ratio
          shrinks instead of counting that evidence twice (design note, section 3)
  hier    the answer only, with error rates of the relation's own: alpha_r = P(yes | false) and beta_r = P(no | true)
          vary across relations (from 0.003 to 0.76 for Qwen3.5-9B), so a pooled rate makes the posterior overconfident
          where the model errs most.  Their distributions across the training relations are beta distributions fitted
          by maximum marginal likelihood (beta-binomial, every relation one observation); a held-out relation's
          posterior integrates over alpha_r and beta_r on a grid (auto_noisy.Noisy, err), so its own answers, and the
          contradictions that the closure exposes, inform its error rates.  There is no single likelihood ratio.
  pair    two models as two experts: the answer is the pair (first model, second model), one of nine categories
          (yes, no or none each), and the ratio of every category is learned like const.  The two models' errors are
          correlated (both Qwen), so multiplying their ratios would count shared evidence twice; the categories carry
          the dependence.  Only when a second model's answers are given (auto_confirm.py --second).
  hpair   hier for the first model and pair for the second: L(y1, y2 | t, r) = L(y1 | t, alpha_r, beta_r) L(y2 | y1, t).
          The first model's error rates are the relation's own as in hier; the second answer's ratio given the first,
          L(y2 | y1, true) / L(y2 | y1, false) = odds(true | y1, y2) / odds(true | y1), is the ratio of the pair
          regression to the const regression on the first answer, both pooled over the training relations, so it
          keeps the dependence of the two models' errors without error rates of every relation for the second model.

Training is leave one relation out.  Every training relation weighs the same (its rows weigh 1 / its candidates), as
in the selection: each relation is one use of the pipeline, and pooled rows would let the 36,883 candidates of
lineitem decide alone.  Features of feat are standardized, so that one ridge penalty fits all.
Selection, fixed before the answers are seen: the smallest held-out log-loss, averaged over the relations, of the
per-candidate posterior that Confirm computes once every candidate is answered: the prior recalibrated by the grid
posterior on (a, b) given the answers (no labels), times LR, closure aside.  The per-FD classifier (variant clf)
thresholds logit P(true | A, x) of feat.
"""
import math
import numpy as np
import drd

CLIP = 9.21     # a logit of a confidence is cut at logit(1 - 1e-4): vLLM's top-5 log-probabilities cannot resolve less
L2 = 1e-2       # the ridge penalty of bench.fit_logistic, so that the prior and the answer models are fit alike
MODELS = ("none", "const", "conf", "feat", "hier")
ERR_GRID = [1 / (1 + math.exp(-z)) for z in (-6.0, -5.0, -4.0, -3.0, -2.0, -1.0, 0.0, 1.0, 2.0)]   # alpha, beta
BINARY = ("const",)


def logit(v):
    v = min(max(v, 1e-12), 1 - 1e-12)
    return math.log(v / (1 - v))


def _z(x, mu, sd):
    return [(v - m) / d for v, m, d in zip(x[1:7], mu, sd)]


def phi_g(model, y, c, x, mu=None, sd=None):
    """features of logit P(true | A, x): the answer y (True, False or None), its confidence c (P(YES) or None) and,
    for feat, the data features x (columns 1 to 6 of bench.features, standardized) times the answer; for pair, y is
    the pair of answers"""
    if model == "pair":
        y1, y2 = y if isinstance(y, tuple) else (y, None)
        k = 3 * (0 if y1 is True else 1 if y1 is False else 2) + (0 if y2 is True else 1 if y2 is False else 2)
        return [1.0 if i == k else 0.0 for i in range(9)]
    a = [1.0 if y is True else 0.0, 1.0 if y is False else 0.0, 1.0 if y is None else 0.0]
    if model == "const":
        return a
    s = 0.0 if c is None else max(-CLIP, min(CLIP, logit(c)))
    f = a + [s, 1.0 if (y is not None and c is None) else 0.0]
    if model == "conf":
        return f
    z = _z(x, mu, sd)
    return f + [a[0] * v for v in z] + [a[1] * v for v in z] + [a[2] * v for v in z]


def phi_h(model, x, mu=None, sd=None):
    """features of logit P(true | x): the base rate, and for feat the data features"""
    return [1.0] + (_z(x, mu, sd) if model == "feat" else [])


def fit_logistic(Phi, ys, wt=None, l2=L2, iters=100):
    """ridge logistic regression with row weights (mean 1): Newton steps, halved until the penalized loss decreases"""
    X, y = np.array(Phi, dtype=float), np.array(ys, dtype=float)
    s = np.ones(len(y)) if wt is None else np.array(wt, dtype=float) * len(y) / float(np.sum(wt))

    def loss(w):
        z = X @ w
        return float((s * (np.logaddexp(0, z) - y * z)).sum() / len(y) + 0.5 * l2 * w @ w)

    w = np.zeros(X.shape[1])
    cur = loss(w)
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(X @ w)))
        g = X.T @ (s * (p - y)) / len(y) + l2 * w
        H = (X.T * (s * p * (1 - p))) @ X / len(y) + l2 * np.eye(X.shape[1])
        step, t = np.linalg.solve(H, g), 1.0
        while t > 1e-6 and loss(w - t * step) > cur:
            t /= 2
        w, prev = w - t * step, cur
        cur = loss(w)
        if prev - cur < 1e-12:
            break
    return w.tolist()


def _betabinom_fit(obs):
    """(mean, concentration) of the beta distribution that maximizes the beta-binomial likelihood of obs, a list of
    (k, n) per relation, on a grid of means (logit -7 to 3) and concentrations (0.5 to 2000)"""
    obs = [(k, n) for k, n in obs if n > 0]
    lb = lambda x, y: math.lgamma(x) + math.lgamma(y) - math.lgamma(x + y)
    best = None
    for z in np.arange(-7.0, 3.01, 0.1):
        mu = 1 / (1 + math.exp(-z))
        for lk in np.arange(math.log(0.5), math.log(2000.0) + 1e-9, 0.1):
            kap = math.exp(lk)
            a, c = mu * kap, (1 - mu) * kap
            ll = sum(lb(k + a, n - k + c) - lb(a, c) for k, n in obs)
            if best is None or ll > best[0]:
                best = (ll, mu, kap)
    return best[1], best[2]


def _grid_weights(mu, kap):
    """weights of ERR_GRID under beta(mu kap, (1 - mu) kap), as a density on the logit scale of the grid"""
    a, c = mu * kap, (1 - mu) * kap
    lw = [(a) * math.log(v) + (c) * math.log(1 - v) for v in ERR_GRID]     # beta pdf times v (1 - v)
    m = max(lw)
    w = [math.exp(x - m) for x in lw]
    return [x / sum(w) for x in w]


def first(y):
    """the first model's answer of an answer or of a pair of answers"""
    return y[0] if isinstance(y, tuple) else y


def fit_hier(bs, answers, held, exclude=()):
    obs_a, obs_b = [], []
    for ds, b in bs.items():
        if ds == held or ds in exclude or ds not in answers:
            continue
        T, truth = {p: first(v) for p, v in answers[ds].items()}, set(b["truth"])
        ys = [(T.get(p), p in truth) for p in b["P"] if T.get(p) is not None]
        obs_a.append((sum(1 for y, t in ys if y and not t), sum(1 for _, t in ys if not t)))
        obs_b.append((sum(1 for y, t in ys if not y and t), sum(1 for _, t in ys if t)))
    (ma, ka), (mb, kb) = _betabinom_fit(obs_a), _betabinom_fit(obs_b)
    return {"alpha_fit": [ma, ka], "beta_fit": [mb, kb], "grid": ERR_GRID,
            "wa": _grid_weights(ma, ka), "wb": _grid_weights(mb, kb)}


def err_grid(params):
    """[(alpha, beta, weight)] of the hier model, the product of its two grids"""
    g = params["grid"]
    return [(a, c, wa * wb) for a, wa in zip(g, params["wa"]) for c, wb in zip(g, params["wb"])]


def fit(model, bs, answers, conf, held, exclude=()):
    """the parameters of model for the held-out relation held, trained on the other relations that have answers, except
    those in exclude (the relation whose answer model the nested selection chooses)"""
    if model == "none":
        return None
    if model == "hier":
        return fit_hier(bs, answers, held, exclude)
    if model == "hpair":
        out = fit_hier(bs, answers, held, exclude)
        rows = [(answers[ds].get(p), p in set(b["truth"]), 1.0 / len(b["P"])) for ds, b in bs.items()
                if ds != held and ds not in exclude and ds in answers for p in b["P"]]
        ys, wt = [r[1] for r in rows], [r[2] for r in rows]
        out["g2"] = fit_logistic([phi_g("pair", y, None, None) for y, _, _ in rows], ys, wt)
        out["h2"] = fit_logistic([phi_g("const", first(y), None, None) for y, _, _ in rows], ys, wt)
        return out
    rows = []
    for ds, b in bs.items():
        if ds == held or ds in exclude or ds not in answers:
            continue
        T, C, truth = answers[ds], conf.get(ds, {}), set(b["truth"])
        rows += [(T.get(p), C.get(p), b["X"][p], p in truth, 1.0 / len(b["P"])) for p in b["P"]]
    mu = sd = None
    if model == "feat":
        Xd, wt = np.array([r[2][1:7] for r in rows], dtype=float), np.array([r[4] for r in rows])
        mu = (wt[:, None] * Xd).sum(0) / wt.sum()
        sd = np.sqrt((wt[:, None] * (Xd - mu) ** 2).sum(0) / wt.sum())
        mu, sd = mu.tolist(), [float(v) if v > 1e-9 else 1.0 for v in sd]
    ys, wt = [r[3] for r in rows], [r[4] for r in rows]
    g = fit_logistic([phi_g(model, y, c, x, mu, sd) for y, c, x, _, _ in rows], ys, wt)
    h = fit_logistic([phi_h(model, x, mu, sd) for _, _, x, _, _ in rows], ys, wt)
    return {"g": g, "h": h, "mu": mu, "sd": sd}


def log_post(model, params, y, c, x):
    """logit P(true | A, x) of the model (the per-FD classifier)"""
    return float(np.dot(params["g"], phi_g(model, y, c, x, params["mu"], params["sd"])))


def log_lr(model, params, y, c, x):
    if model == "none":
        return 0.0
    return log_post(model, params, y, c, x) - float(np.dot(params["h"], phi_h(model, x, params["mu"], params["sd"])))


def second_lr(params, y):
    """the hpair ratio of the second answer given the first, L(y2 | y1, true) / L(y2 | y1, false)"""
    z = (float(np.dot(params["g2"], phi_g("pair", y, None, None)))
         - float(np.dot(params["h2"], phi_g("const", first(y), None, None))))
    return math.exp(max(min(z, 40), -40))


def lr_table(model, params, b, T, C):
    """candidate -> likelihood ratio of its recorded answer, for auto_noisy"""
    return {p: math.exp(max(min(log_lr(model, params, T.get(p), C.get(p), b["X"][p]), 40), -40)) for p in b["P"]}


def recal_posterior(pis, lrs):
    """per-candidate P(true | all answers) under Confirm's recalibrated prior, closure aside: the grid posterior of
    drd on (a, b) given the answers' marginal likelihoods, then each candidate's local posterior averaged over it"""
    lg = np.array([logit(v) for v in pis])
    r = np.array(lrs, dtype=float)
    L1, L0 = r / (1 + r), 1 / (1 + r)
    A = np.array([a for a, _ in drd.GRID])[:, None]
    B = np.array([b for _, b in drd.GRID])[:, None]
    rho = 1 / (1 + np.exp(-(A * lg[None, :] + B)))
    m = rho * L1 + (1 - rho) * L0
    lw = np.log(np.array(drd.GRID_PRIOR)) + np.log(m).sum(axis=1)
    w = np.exp(lw - lw.max())
    w /= w.sum()
    return (w[:, None] * (rho * L1 / m)).sum(axis=0)


def recal_posterior_err(pis, ys, err, extra=None):
    """recal_posterior with the error rates of the hier model integrated over its grid: ys holds the answers (True,
    False or None) and err the (alpha, beta, weight) of err_grid; extra, the ratios of hpair's second answers"""
    lg = np.array([logit(v) for v in pis])
    r2 = np.ones(len(pis)) if extra is None else np.array(extra, dtype=float)
    x1, x0 = r2 / (1 + r2), 1 / (1 + r2)
    A = np.array([a for a, _ in drd.GRID])[:, None]
    B = np.array([b for _, b in drd.GRID])[:, None]
    rho = 1 / (1 + np.exp(-(A * lg[None, :] + B)))
    yes = np.array([y is True for y in ys])
    no = np.array([y is False for y in ys])
    lws, locs = [], []
    for al, be, w in err:
        L1 = np.where(yes, 1 - be, np.where(no, be, 1.0)) * x1
        L0 = np.where(yes, al, np.where(no, 1 - al, 1.0)) * x0
        m = rho * L1 + (1 - rho) * L0
        lws.append(np.log(np.array(drd.GRID_PRIOR)) + math.log(w) + np.log(m).sum(axis=1))
        locs.append(rho * L1 / m)
    lw = np.stack(lws)                                   # [E, G]
    wt = np.exp(lw - lw.max())
    wt /= wt.sum()
    return sum((wt[e][:, None] * locs[e]).sum(axis=0) for e in range(len(err)))


def logloss(model, params, b, pi, T, C):
    """held-out log-loss of recal_posterior over the candidates of b"""
    if model in ("hier", "hpair"):
        q = recal_posterior_err([pi[p] for p in b["P"]], [first(T.get(p)) for p in b["P"]], err_grid(params),
                                [second_lr(params, T.get(p)) for p in b["P"]] if model == "hpair" else None)
        truth = set(b["truth"])
        return float(-np.mean([math.log(max(v, 1e-12) if p in truth else max(1 - v, 1e-12)) for p, v in zip(b["P"], q)]))
    lrs = list(lr_table(model, params, b, T, C).values()) if model != "none" else [1.0] * len(b["P"])
    q = recal_posterior([pi[p] for p in b["P"]], lrs)
    truth = set(b["truth"])
    return float(-np.mean([math.log(max(v, 1e-12) if p in truth else max(1 - v, 1e-12)) for p, v in zip(b["P"], q)]))
