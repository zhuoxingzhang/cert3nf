"""
Experiments of the automated pipeline (design notes, sections 5 to 8 and component selection) on the twelve relations
of auto_common.py, from the answers that auto_llm.py recorded (one JSONL file per model).

Variants (each changes one thing against "ours"; table VARIANTS):
  ours        statistics prior (learned on the other eleven relations, recalibrated), the model as expert, its answers
              weighed by the answer model selected by "rates" (auto_answer.py); runs until every candidate is asked and
              records the first certificate (the reported point) and the end (ablation A8: ask everything)
  trust       ours with the answers taken as true: the same prior, rounds (5% of the open candidates), policy and
              records, with the posterior given the answers sampled exactly (drd) instead of weighed by an answer
              model, so the ablation isolates the answer model; the certificate holds relative to the answers.  (One
              question per round, as drd.run asks, would take about 53 hours on tpch_lineitem_orders, where wrong
              answers never certify and all 36,486 candidates are asked: extrapolated from 7,750 questions in 3.8 h.)
  const       ours with the answer model const (constant error rates, the binary answer only): does the confidence
              of an answer, or the dependence of the errors on the data, help?
  unc         ours with uncertainty sampling instead of the greedy policy
  clf         no Confirm: the model answers every candidate, each FD is accepted if P(true | answer, confidence,
              statistics) >= 1/2 (logistic regression, the numerator of the answer model feat), and the design is
              synthesized from the closure: the per-FD classifier that stacks the statistics and the model
  L1          the model designs directly (kind design, three runs)
  L3          the model normalizes as a team of agents after MARS (auto_mars.py, DIR/mars_<model>.jsonl, three runs):
              its last schema, and the reliable FDs of its last evidence as the FDs it concludes; not in the default
              variants, since it needs its own GPU run
  L2          the model answers every candidate; the design is synthesized from the closure of its yes answers
  A2          no expert: the design whose region holds most of the prior sample
  A3          constant prior (the base rate of the other relations)
  A4          the model as expert without the sample rows (kind expert_names): an accuracy comparison on a random
              sample of at most 200 candidates per relation, reported by "rates", not a pipeline run
  A5          prior from the same model's stated rules (kind rules, llm_rules.score_relation, three elicitations)
  A6          prior from the other model's stated rules
  A7          the learned prior without the size of the left-hand side as a feature
  A9          ours without recalibration of the prior
  upper       the ground truth as expert, through drd.run (one question per round)
  hyfd        every candidate taken as true
  K           (--no-key, its own answers directory) every variant with no declared key: the prompts say "none
              declared" and the minimal FDs that the key implies are candidates (auto_common.py)
The answer model does not depend on the prior (auto_answer.py), so the prior ablations keep it.  A missing or
unparsable answer counts as no for trust and L2, and as its own category for the answer models.

Metrics: judge() of baseline_direct under the reachable truth (declared key plus the true candidates) and under the
whole ground truth; precision, recall and F1 of the FDs the method concludes, by closure over the candidates (an FD
the method states outside the candidates counts as a false positive unless the ground truth implies it).  A method
concludes: with trusted answers, what the declared key and its yes answers imply; with a posterior, the closure of the
candidates of posterior probability at least 1/2 (the Bayes decision per FD); L1, the FDs it states.  The runs in the
rounds of ours (posterior variants and trust) also record a trace per round: questions, certified, share, ess (for
trust the number of exact samples), F1 and whether the current design is good.
The metrics with the suffix _mined count over all mined minimal FDs, the ones the declared key implies included as
concluded and true, so that runs with and without a declared key (K) compare.

Usage:  python auto_confirm.py rates --answers DIR [--models qwen]
        python auto_confirm.py run --answers DIR --models qwen,r1 --variants ours,trust,... [--seeds 3] [--workers 8]
                                   [--datasets ...] [--cap risk --max-cand 250] [--out F.jsonl]
        either with --no-key and the answers of the no-key prompts (ablation K)
"""
import argparse, hashlib, inspect, json, math, os, random, statistics, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
import bench, drd
import auto_common as AC
import auto_answer as AA
import auto_noisy as AN
import baseline_direct as BD
import llm_rules as LR

S = bench.S
SHORT = {"qwen": "Qwen/Qwen3-30B-A3B-Thinking-2507", "r1": "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
         "q35": "Qwen/Qwen3.5-9B", "gptoss": "openai/gpt-oss-20b"}
OTHER = {"qwen": "r1", "r1": "qwen", "q35": "qwen", "gptoss": "q35"}
RHO_MIN, EPS, DELTA = 1e-4, 0, 0.1
PRIOR_KINDS = ("learned", "rules", "mix")     # the kinds of prior that the nested selection chooses from
VARIANTS = {    # prior, inference and options; inference post: posterior with an answer model, trust: the answers
    # taken as true in the rounds of ours (auto_noisy.run), drd: the answers taken as true through drd.run
    "ours":   dict(prior="selected", infer="post", am="selected", until="all"),
    "oursL":  dict(prior="learned", infer="post", am="selected", until="all"),   # ours before the prior was chosen
    "hier":   dict(prior="learned", infer="post", am="hier", until="all"),     # the hier answer model, forced
    "hpair":  dict(prior="learned", infer="post", am="hpair", until="all"),    # two experts, forced (needs --second)
    "trust":  dict(prior="learned", infer="trust", until="all"),
    "const":  dict(prior="learned", infer="post", am="const"),
    "unc":    dict(prior="learned", infer="post", am="selected", policy="unc", until="all"),
    "A3":     dict(prior="const", infer="post", am="selected"),
    "A5":     dict(prior="rules", infer="post", am="selected"),
    "A6":     dict(prior="rules_other", infer="post", am="selected"),
    "A7":     dict(prior="learned_nolhs", infer="post", am="selected"),
    "A9":     dict(prior="learned", infer="post", am="selected", recal=False),
    "upper":  dict(prior="learned", infer="drd", truth=True),
    # the designer in the loop (design note, component selection item 20): the model's answers on every candidate, then at most 100
    # questions to the designer (simulated by the ground truth), five a round; hyb0 without the model's answers
    "hyb":    dict(prior="selected", infer="hybrid", am="selected", budget=100, hbatch=5),
    "hyb0":   dict(prior="learned", infer="hybrid", am="none", budget=100, hbatch=5),
    # the second version (item 21): the designer's yes answers alone must justify the certified design, and the
    # certificate needs an effective sample size of K / 4
    "vhyb":   dict(prior="selected", infer="hybrid", am="selected", budget=100, hbatch=5, sound=True),
    "vhyb0":  dict(prior="learned", infer="hybrid", am="none", budget=100, hbatch=5, sound=True),
    # the third version (item 23): the second, with the candidates implied by the designer's yes answers set, not drawn
    "rbhyb":  dict(prior="selected", infer="hybrid", am="selected", budget=100, hbatch=5, sound=True, rb=True),
    "rbhyb0": dict(prior="learned", infer="hybrid", am="none", budget=100, hbatch=5, sound=True, rb=True),
    # the fourth version (item 25): the third, with completeness checked without the model's evidence against
    "oshyb":  dict(prior="selected", infer="hybrid", am="selected", budget=100, hbatch=5, sound=True, rb=True,
                   onesided=True),
    "oshyb0": dict(prior="learned", infer="hybrid", am="none", budget=100, hbatch=5, sound=True, rb=True,
                   onesided=True),
    # a designer who answers wrongly with probability 0.02 or 0.05 (item 24), the method unchanged
    **{f"{v}_e{k}": dict(sp, designer_err=k / 100) for k in (2, 5) for v, sp in (
        ("rbhyb", dict(prior="selected", infer="hybrid", am="selected", budget=100, hbatch=5, sound=True, rb=True)),
        ("rbhyb0", dict(prior="learned", infer="hybrid", am="none", budget=100, hbatch=5, sound=True, rb=True)))},
}
# the fifth version (item 26): the third, with a designer modelled to err with probability 0.05 and asked again where
# the answers leave the posterior unsure (at most three answers a candidate); simulated designers who err with
# probability 0, 0.02 or 0.05 independently on every answer (e), or who repeat their first error (p, "persistent")
VARIANTS.update({f"et{v[2:]}_{m}{k}": dict(VARIANTS[v], designer_eps=0.05, reask=3, designer_err=k / 100,
                                           persistent=m == "p")
                 for v in ("rbhyb", "rbhyb0") for m, k in (("e", 0), ("e", 2), ("e", 5), ("p", 5))})
# the tolerance as the method's parameter (item 27): a designer declared to err with probability 0.02
VARIANTS.update({f"et2{v[2:]}_e{k}": dict(VARIANTS[v], designer_eps=0.02, reask=3, designer_err=k / 100)
                 for v in ("rbhyb", "rbhyb0") for k in (0, 2, 5)})
NO_MODEL = ("upper", "hyfd", "A2")
_B, _ANS, _PRI, _AM, _SA = {}, {}, {}, {}, {}


def benches():
    """the evaluation relations (with the confirmatory ones, which no pool contains) and, unless the pool is loo, the
    training relations"""
    if not _B:
        for ds in AC.DATASETS + AC.FRESH + (AC.TRAIN if AC.pool_mode() != "loo" else []):
            _B[ds] = AC.load(ds)
    return _B


def read_answers(adir, model):
    """{kind: {dataset: {candidate or run: answer}}} from DIR/answers_<model>.jsonl; the confidence P(YES) of an
    expert answer goes to the kind <kind>_conf"""
    key = (adir, model)
    if key in _ANS:
        return _ANS[key]
    bs = benches()
    by_id = {}
    for ds, b in bs.items():
        for p in b["P"]:
            lhs, rhs = b["fdnames"][p]
            by_id[AC.fd_id(ds, lhs, rhs)] = (ds, p)
    out = {}
    path = os.path.join(adir, f"answers_{model}.jsonl")
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            kind = r["kind"]
            if kind.startswith("expert"):
                fid = r["id"].split("|", 1)[1]
                if fid not in by_id:
                    raise KeyError(f"{path}: {fid} is no candidate with no_key={AC.no_key()} (answers of the other mode?)")
                ds, p = by_id[fid]
                out.setdefault(kind, {}).setdefault(ds, {})[p] = r["answer"]
                c = r.get("confidence")
                out.setdefault(kind + "_conf", {}).setdefault(ds, {})[p] = c.get("p_yes") if isinstance(c, dict) else None
            else:
                out.setdefault(kind, {}).setdefault(r["dataset"], {})[r["id"].rsplit("|", 1)[1]] = r["answer"]
    for ds, tab in out.get("expert", {}).items():   # with no key, the answers of the other mode lack the key's FDs
        miss = sum(1 for p in bs[ds]["P"] if p not in tab)
        if miss and AC.no_key():
            raise KeyError(f"{path}: {miss} candidates of {ds} unanswered with no_key=True (answers of the other mode?)")
        if miss:
            print(f"warning: {path}: {miss} candidates of {ds} unanswered", file=sys.stderr)
    _ANS[key] = out
    return out


def read_mars(adir, model):
    """{(dataset, run): record} of the multi-agent normalizer (auto_mars.py) from DIR/mars_<model>.jsonl; a missing
    file raises, so that L3 is never judged on runs that did not happen"""
    key = ("mars", adir, model)
    if key not in _ANS:
        with open(os.path.join(adir, f"mars_{model}.jsonl"), encoding="utf-8") as fh:
            _ANS[key] = {(r["dataset"], r["run"]): r for r in map(json.loads, fh) if r.get("kind") == "mars"}
    return _ANS[key]


# ---------------- error rates ----------------
def counts(table, b):
    truth = set(b["truth"])
    c = {"tp": 0, "fn": 0, "fp": 0, "tn": 0, "none": 0}
    for p in b["P"]:
        y = table.get(p)
        c["none"] += y is None
        if p in truth:
            c["tp" if y is True else "fn"] += 1
        else:
            c["fp" if y is True else "tn"] += 1
    return c


def rates(tables, exclude):
    """alpha = P(yes | false), beta = P(no | true) on the relations other than exclude, Laplace-smoothed"""
    fp = nf = fn = nt = 0
    for ds, b in benches().items():
        if ds == exclude or ds not in tables or ds not in AC.pool():
            continue
        c = counts(tables[ds], b)
        fp, nf, fn, nt = fp + c["fp"], nf + c["fp"] + c["tn"], fn + c["fn"], nt + c["tp"] + c["fn"]
    return (fp + 1) / (nf + 2), (fn + 1) / (nt + 2)


def inconsistent(b, table):
    """candidates answered no although the declared key and the yes answers imply them"""
    yes = [p for p in b["P"] if table.get(p) is True]
    return sum(1 for p in concluded(b, yes) if table.get(p) is not True)


def report_rates(adir, models):
    bs = benches()
    tabs = {m: read_answers(adir, m) for m in models}
    out = {}
    for m in models:
        T = tabs[m].get("expert")
        if T:
            C = tabs[m].get("expert_conf", {})
            for ds, b in bs.items():
                if ds not in T:
                    continue
                c = counts(T[ds], b)
                a, be = rates(T, ds)
                c.update(alpha_loo=round(a, 4), beta_loo=round(be, 4), inconsistent=inconsistent(b, T[ds]),
                         no_conf=sum(1 for p in b["P"] if T[ds].get(p) is not None and C.get(ds, {}).get(p) is None))
                out.setdefault(m, {}).setdefault("expert", {})[ds] = c
                print(f"{m:5s} expert {ds:28s} {c}")
        # A4: the same sampled candidates answered with and without the sample rows
        N = tabs[m].get("expert_names")
        if T and N:
            for ds, b in bs.items():
                sub = [p for p in b["P"] if p in N.get(ds, {})]
                if not sub:
                    continue
                truth = set(b["truth"])
                acc = lambda tab: sum((tab.get(p) is True) == (p in truth) for p in sub) / len(sub)
                out.setdefault(m, {}).setdefault("A4", {})[ds] = {"n": len(sub), "true": len(truth & set(sub)),
                                                                   "acc_rows": acc(T[ds]), "acc_names": acc(N[ds])}
                print(f"{m:5s} A4 {ds:28s} {out[m]['A4'][ds]}")
        if T:
            am = fit_answer_models(adir, m)
            with open(os.path.join(adir, f"answer_models_{m}.json"), "w", encoding="utf-8") as fh:
                json.dump(am, fh)
            out.setdefault(m, {})["answer_models"] = {"selected": am["selected"], "noconf": am["noconf"],
                                                      "selected_for": am["selected_for"], "logloss": am["logloss"]}
            print(f"{m:5s} answer models (held-out log-loss, macro):",
                  {k: round(v["macro"], 4) for k, v in am["logloss"].items()}, "selected", am["selected"],
                  "nested, per relation:", {r: f"{am['prior_for'][r]}|{m}" for r, m in am["selected_for"].items()})
    # dependence of the errors of the two models given the truth (design note, section 3: variant A6)
    if len(models) == 2 and all("expert" in tabs[m] for m in models):
        m1, m2 = models
        for lab in (True, False):
            n = e1 = e2 = both = 0
            for ds, b in bs.items():
                truth = set(b["truth"])
                for p in b["P"]:
                    if (p in truth) != lab:
                        continue
                    w1 = (tabs[m1]["expert"][ds].get(p) is True) != lab
                    w2 = (tabs[m2]["expert"][ds].get(p) is True) != lab
                    n, e1, e2, both = n + 1, e1 + w1, e2 + w2, both + (w1 and w2)
            if n:
                out.setdefault("dependence", {})["true" if lab else "false"] = {
                    "n": n, "err_" + m1: e1 / n, "err_" + m2: e2 / n, "both": both / n,
                    "both_if_independent": (e1 / n) * (e2 / n)}
        print(json.dumps(out.get("dependence"), indent=1))
    return out


# ---------------- conclusions and metrics ----------------
def concluded(b, accepted):
    """the candidates that the declared key and the accepted FDs imply (one closure per left-hand side)"""
    F = b["sigma0"] + list(accepted)
    cl, out = {}, set()
    for p in b["P"]:
        X = p[0]
        if X not in cl:
            cl[X] = S.B.closure(X, F)
        if p[1] <= cl[X]:
            out.add(p)
    return out


def prf(b, pred, extra_false=0):
    truth = set(b["truth"])
    tp, fp, fn = len(pred & truth), len(pred - truth) + extra_false, len(truth - pred)
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    return {"precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0, "tp": tp, "fp": fp, "fn": fn}


def judge(b, D):
    """baseline_direct.judge without the readable reasons, with the closures of the truth computed once"""
    out = {"tables": len(D), "covers": set().union(*D) == set(b["R"]) if D else False}
    # the declared key is a premise of the pipeline (sigma0 within Sigma*), so both truths include it; without it the
    # sure truth of tpcds_core (whose key rests on an unsure clause) judged designs that use the key (item 32)
    for tag, F in (("reach", b["sigma0"] + b["truth"]), ("gold", b["sigma0"] + b["gold"])):
        key = (b["name"], tag)
        if key not in _SA:
            sa = BD.E2.atomic_closure(b["R"], F)
            _SA[key] = (sa, len(S.design(b["R"], sa, "synthesis")))
        sa, opt = _SA[key]
        m = S.metrics(b["R"], [list(s) for s in D], sa, sa)
        out.update({f"{tag}_lossless": m["lossless"], f"{tag}_preserving": m["u_str"] == 0, f"{tag}_nf3": m["nf3"],
                    f"{tag}_unpreserved": m["u_str"], f"{tag}_opt_tables": opt,
                    f"{tag}_good": out["covers"] and m["valid"] and len(D) <= opt + BD.EPS})
    return out


def prf_mined(b, pred, extra_false=0):
    """prf over all mined minimal FDs: those that the declared key implies count as concluded and true"""
    i0 = set(b["implied0"])
    return prf({"truth": b["truth"] + list(i0)}, set(pred) | i0, extra_false)


def evaluate(b, D, pred, extra_false=0):
    out = judge(b, [set(s) for s in D])
    out.update(prf(b, pred, extra_false))
    out.update({k + "_mined": v for k, v in prf_mined(b, pred, extra_false).items()})
    return out


# ---------------- priors and answer models ----------------
def prior(b, kind, adir=None, model=None, exclude=None):
    """the clipped prior of b, trained on the relations of the pool other than b and those in exclude"""
    bs = benches()
    ex = {b["name"]} | set(exclude or ()) | (set(bs) - set(AC.pool()))
    key = (b["name"], kind, model, frozenset(ex))
    if key in _PRI:
        return _PRI[key]
    train = [v for k, v in bs.items() if k not in ex]
    if kind in ("learned", "const"):
        pi = bench.clip(bench.estimate(b, train, kind), lo=RHO_MIN)
    elif kind == "learned_nolhs":               # A7: the learned prior without the size of the left-hand side
        cols = [0, 2, 3, 4, 5, 6]
        ys = [p in set(t["truth"]) for t in train for p in t["P"]]
        w = bench.fit_logistic([[t["X"][p][c] for c in cols] for t in train for p in t["P"]], ys)
        pi = bench.clip({p: float(1 / (1 + math.exp(-sum(wi * b["X"][p][c] for wi, c in zip(w, cols)))))
                         for p in b["P"]}, lo=RHO_MIN)
    elif kind == "mix":                         # the learned prior and the model's stated rules, logits averaged
        l, r = prior(b, "learned", exclude=exclude), prior(b, "rules", adir, model)
        pi = None if r is None else bench.clip({p: 1 / (1 + math.exp(-(AA.logit(l[p]) + AA.logit(r[p])) / 2))
                                                for p in b["P"]}, lo=RHO_MIN)
    else:                                       # the stated rules of a model (A5, A6), averaged over its elicitations
        try:
            runs = read_answers(adir, model).get("rules", {}).get(b["name"], {})
        except FileNotFoundError:
            runs = {}
        pis = [LR.score_relation(b, ans, seed=i)[0] for i, ans in enumerate(v for _, v in sorted(runs.items()))
               if isinstance(ans, dict)]
        pi = bench.clip({p: sum(q[p] for q in pis) / len(pis) for p in b["P"]}, lo=RHO_MIN) if pis else None
    _PRI[key] = pi
    return pi


def prior_for(b, pk, adir, model, exclude=None):
    """the prior kind of a variant: learned, const, learned_nolhs, rules (same model) or rules_other"""
    if pk in ("rules", "rules_other"):
        return prior(b, "rules", adir, model if pk == "rules" else OTHER[model])
    if pk == "mix":
        return prior(b, "mix", adir, model, exclude=exclude)
    return prior(b, pk, exclude=exclude)


def fit_answer_models(adir, model):
    """held-out log-loss of every answer model (auto_answer.logloss: Confirm's per-candidate posterior under the learned
    prior once everything is answered), the selection, and the parameters for every held-out relation"""
    bs = benches()
    A = read_answers(adir, model)
    T, C = A.get("expert", {}), A.get("expert_conf", {})
    held = [ds for ds in bs if ds in T]
    Tp = pair_table(adir, model)                 # None without a second model
    models = AA.MODELS[1:] + (("pair", "hpair") if Tp else ())
    tab = lambda m: Tp if m in ("pair", "hpair") else T
    off = tuple(set(bs) - set(AC.pool()))            # relations outside the pool train nothing
    res = {"model": model, "no_key": AC.no_key(), "pool": AC.pool_mode(), "truth": AC.truth_mode(), "logloss": {},
           "params": {}}
    for m in ("none",) + models:
        ll = res["logloss"].setdefault(m, {})
        for ds in held:
            w = res["params"].setdefault(m, {})[ds] = AA.fit(m, bs, tab(m), C, ds, exclude=off)
            ll[ds] = AA.logloss(m, w, bs[ds], prior(bs[ds], "learned"), tab(m)[ds], C.get(ds, {}))
        ll["macro"] = statistics.mean(ll[ds] for ds in held)
    macro = lambda m: res["logloss"][m]["macro"]
    res["second"] = second_model()
    res["selected"] = min(models, key=macro)            # reported only: its macro average includes every relation
    res["noconf"] = min(AA.BINARY, key=macro)
    # Nested selection, used by the runs: the answer model of relation r is chosen on the other relations only, with
    # every inner fit and prior trained without r too, so that the ground truth of r decides nothing about r
    # The kind of prior is chosen the same way, jointly with the answer model (design note, component selection item 17): learned,
    # rules (the model's stated rules for the relation, which need no training) or mix
    res["selected_for"], res["prior_for"], res["nested_logloss"] = {}, {}, {}
    for r in held:
        inner = [ds for ds in held if ds != r and ds not in off]
        fits = {(m, ds): AA.fit(m, bs, tab(m), C, ds, exclude=(r,) + off) for m in models for ds in inner}
        score = {}
        for pk in PRIOR_KINDS:
            pis = {ds: prior_for(bs[ds], pk, adir, model, exclude=[r]) for ds in inner + [r]}
            if any(v is None for v in pis.values()):
                continue                        # a kind that some relation lacks (no stated rules) is not a choice
            for m in models:
                score[f"{pk}|{m}"] = statistics.mean(AA.logloss(m, fits[(m, ds)], bs[ds], pis[ds], tab(m)[ds],
                                                                C.get(ds, {})) for ds in inner)
        res["nested_logloss"][r] = score
        pk, m = min(score, key=score.get).split("|")
        res["prior_for"][r], res["selected_for"][r] = pk, m
    return res


def answer_model(adir, model):
    key = (adir, model)
    if key not in _AM:
        with open(os.path.join(adir, f"answer_models_{model}.json"), encoding="utf-8") as fh:
            _AM[key] = json.load(fh)
        if _AM[key].get("no_key", False) != AC.no_key():
            raise RuntimeError(f"{adir}: answer models fitted with no_key={_AM[key].get('no_key', False)}, "
                               f"run with no_key={AC.no_key()}")
        if _AM[key].get("second") != second_model():
            raise RuntimeError(f"{adir}: answer models fitted with second={_AM[key].get('second')}, "
                               f"run with second={second_model()}")
        if _AM[key].get("truth", "full") != AC.truth_mode():
            raise RuntimeError(f"{adir}: answer models fitted with truth={_AM[key].get('truth', 'full')}, "
                               f"run with truth={AC.truth_mode()}")
        if _AM[key].get("pool", "loo") != AC.pool_mode():
            raise RuntimeError(f"{adir}: answer models fitted with pool={_AM[key].get('pool', 'loo')}, "
                               f"run with pool={AC.pool_mode()}")
    return _AM[key]


def second_model():
    """the short name of the second expert (environment CONFIRM_SECOND, set by --second), or None"""
    return os.environ.get("CONFIRM_SECOND") or None


def pair_table(adir, model):
    """{dataset: {candidate: (answer of model, answer of the second model)}}, or None without a second model"""
    sec = second_model()
    if not sec:
        return None
    T = read_answers(adir, model).get("expert", {})
    T2 = read_answers(adir, sec).get("expert", {})
    return {ds: {p: (T[ds].get(p), T2.get(ds, {}).get(p)) for p in b["P"]} for ds, b in benches().items() if ds in T}


# ---------------- one run ----------------
def designer_flip(ds, seed, p, eps, k=0):
    """whether the simulated designer answers candidate p wrongly the k-th time it is asked (items 24, 26): a uniform
    number from the SHA-256 of (relation, seed, candidate, eps) and k beyond the first, so that every variant meets the
    same errors"""
    h = hashlib.sha256(repr((ds, seed, sorted(p[0]), sorted(p[1]), eps) + ((k,) if k else ())).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2 ** 64 < eps


def job(args):
    variant, model, ds, seed, adir, cap, max_cand, prune_delta = args
    b = benches()[ds]
    truth = set(b["truth"])
    t0 = time.time()
    out = {"variant": variant, "model": model, "dataset": ds, "seed": seed, "candidates": len(b["P"]), "true": len(truth),
           "no_key": AC.no_key(), "pool": AC.pool_mode(), "truth": AC.truth_mode()}
    A = read_answers(adir, model) if model else {}
    if variant in ("L1", "L3"):
        if variant == "L1":
            ans = A.get("design", {}).get(ds, {}).get(seed)      # seed names the run a, b, c
        else:                                                    # the multi-agent normalizer: its last schema and
            rec = read_mars(adir, model)[(ds, seed)]             # the reliable FDs of its last evidence
            ans = {"tables": rec["tables"] or [], "fds": [g for g in rec["fds"] if g["label"] == "reliable"]} \
                if rec["tables"] is not None else None
            out.update(llm_calls=len(rec["calls"]), schemata=rec["schemata"], verified=rec["verified"])
        D, fds, unknown = [], [], set()
        if isinstance(ans, dict):
            idx = {a: i for i, a in enumerate(b["names"])}
            rawD = []
            for t in ans.get("tables", []):
                attrs = t.get("attributes", []) if isinstance(t, dict) else t
                unknown |= {a for a in attrs if a not in idx}
                rawD.append(frozenset(idx[a] for a in attrs if a in idx))
            D = [s for s in dict.fromkeys(rawD) if s and not any(s < u for u in rawD)]
            for g in ans.get("fds", []):
                try:
                    fds.append(S.fd([idx[a] for a in g["lhs"]], idx[g["rhs"]]))
                except (KeyError, TypeError):
                    pass
        reach = b["sigma0"] + b["truth"]
        outside_false = sum(1 for g in fds if g not in set(b["P"]) and not S.implies(reach, g))
        out.update(parsed=isinstance(ans, dict), unknown_attrs=sorted(unknown), questions=0)
        out.update(evaluate(b, D, concluded(b, [g for g in fds if g in set(b["P"])]), outside_false) if D
                   else {"reach_good": False, "gold_good": False, "f1": 0.0})
        return out
    full = lambda: drd.Instance(b["R"], b["sigma0"], b["P"], {p: 0.5 for p in b["P"]}, list(truth), name=ds)
    if variant == "hyfd":
        inst = full()
        out.update(questions=0, **evaluate(b, inst.alg(inst.close(list(b["P"]))), set(b["P"])))
        return out
    table = A.get("expert_names" if variant == "A4" else "expert", {}).get(ds, {}) if model else {}
    conf = A.get("expert_conf", {}).get(ds, {}) if model else {}
    if variant == "L2":
        yes = [p for p in b["P"] if table.get(p) is True]
        inst = full()
        out.update(questions=len(b["P"]), **evaluate(b, inst.alg(inst.close(yes)), concluded(b, yes)))
        return out
    if variant == "clf":                        # the per-FD classifier: logit P(true | answer, confidence, x) of feat
        AM = answer_model(adir, model)
        w = AM["params"]["feat"][ds]
        acc = [p for p in b["P"] if AA.log_post("feat", w, table.get(p), conf.get(p), b["X"][p]) >= 0]
        inst = full()
        out.update(questions=len(b["P"]), **evaluate(b, inst.alg(inst.close(acc)), concluded(b, acc)))
        return out
    if variant == "A4":
        out.update(error="A4 is an accuracy comparison on a sample of candidates (auto_confirm.py rates)")
        return out
    spec = VARIANTS[variant] if variant != "A2" else dict(prior="learned")
    pk = spec["prior"]
    if pk == "selected":                        # the kind of prior of the nested selection
        AMs = answer_model(adir, model)
        if "prior_for" not in AMs:
            raise RuntimeError(f"{adir}: answer models without the nested choice of prior; rerun auto_confirm.py rates")
        pk = AMs["prior_for"][ds]
        out["prior_kind"] = pk
    pi = prior_for(b, pk, adir, model)
    if pi is None:
        out.update(error="no prior")
        return out
    if cap == "risk":
        kept, dropped, delta_left, _ = bench.prune_risk(pi, prune_delta, max_cand, DELTA)
    else:
        kept, dropped, forced = bench.prune(pi, prune_delta, max_cand)
        delta_left = prune_delta
        dropped = set(dropped) | set(forced)
    kept = sorted(kept, key=bench.tiekey)
    out.update(kept=len(kept), dropped=len(dropped), true_dropped=len(truth & set(dropped)), auc=bench.auc(pi, truth))
    delta_cert = max(DELTA - delta_left, 0.0)
    inst = drd.Instance(b["R"], b["sigma0"], kept, {p: pi[p] for p in kept}, [p for p in kept if p in truth],
                        name=ds, recal=True)
    if variant == "A2":
        rnd = random.Random(seed)
        samples = inst.sample({}, rnd, 80)
        ds_ = drd.decisions(inst, {}, samples)
        G = drd.good_matrix(inst, ds_, samples, EPS)
        D = drd.covering(inst, ds_, samples, EPS, 1.0, G)
        marg = {p: sum(p in h for h in samples) / len(samples) for p in kept}
        out.update(questions=0, share=sum(G[D]) / len(samples),
                   **evaluate(b, D, concluded(b, [p for p in kept if marg[p] >= 0.5])))
    elif spec["infer"] in ("post", "trust", "hybrid"):
        if spec["infer"] in ("post", "hybrid"):
            AM = answer_model(adir, model)
            if "selected_for" not in AM:        # fitted before the nested selection: refit, never fall back
                raise RuntimeError(f"{adir}: answer models without the nested selection; rerun auto_confirm.py rates")
            am = {"selected": AM["selected_for"][ds], "noconf": AM["noconf"]}.get(spec["am"], spec["am"])
            if am in ("pair", "hpair"):         # the answers of both models as one categorical answer
                table = pair_table(adir, model)[ds]
            if am == "hier":                    # error rates of the relation's own, integrated over (auto_answer)
                err = ({p: table.get(p) for p in kept}, AA.err_grid(AM["params"][am][ds]))
                lr, answer = None, None
            elif am == "hpair":                 # hier for the first model, the second answer's ratio given the first
                w = AM["params"][am][ds]
                err = ({p: AA.first(table.get(p)) for p in kept}, AA.err_grid(w),
                       {p: AA.second_lr(w, table.get(p)) for p in kept})
                lr, answer = None, None
            else:
                lr = AA.lr_table(am, AM["params"][am][ds], b, table, conf)
                lr, answer, err = {p: lr[p] for p in kept}, None, None
            accepted = lambda st: [p for p, v in st["marg"].items() if v >= 0.5]
        else:                                   # trust: a missing or unparsable answer is no
            lr, answer, err = None, lambda p: table.get(p) is True, None
            accepted = lambda st: st["yes"]

        def summary(st):
            return evaluate(b, st["design"], concluded(b, accepted(st)))

        def tracer(st):
            e = summary(st)
            return {"q": st["questions"], "cert": st["certified"], "share": round(st["share"], 3),
                    "ess": round(st["ess"], 1), "f1": round(e["f1"], 4), "precision": round(e["precision"], 4),
                    "recall": round(e["recall"], 4), "reach_good": e["reach_good"], "gold_good": e["gold_good"],
                    **{k: st[k] for k in ("sound", "risk", "conflicts") if k in st}}

        if spec["infer"] == "hybrid":           # the designer answers from the ground truth
            e_d, stuck = spec.get("designer_err", 0.0), spec.get("persistent", False)
            flip = lambda p, k: e_d > 0 and designer_flip(ds, seed, p, e_d, 0 if stuck else k)
            r = AN.run_hybrid(inst, lr, lambda p, k: (p in truth) != flip(p, k), budget=spec["budget"],
                              hbatch=spec["hbatch"], eps=EPS, delta=delta_cert, seed=seed,
                              recal=spec.get("recal", True), policy=spec.get("policy", "marg"), on_round=tracer,
                              err=err, sound=spec.get("sound", False), rb=spec.get("rb", False),
                              onesided=spec.get("onesided", False), designer_eps=spec.get("designer_eps"),
                              reask=spec.get("reask", 1))
            nets = {p: AN.net_answer(v) for p, v in r["answers"].items()}
            out.update(budget=spec["budget"], hbatch=spec["hbatch"], sound_mode=spec.get("sound", False),
                       rb=spec.get("rb", False), onesided=spec.get("onesided", False), designer_err=e_d,
                       designer_eps=spec.get("designer_eps"), persistent=stuck,
                       designer_wrong=sum(a != (p in truth) for p, v in r["answers"].items() for a in v),
                       first_wrong=sum(v[0] != (p in truth) for p, v in r["answers"].items()),
                       net_wrong=sum(a is not None and a != (p in truth) for p, a in nets.items()),
                       net_tie=sum(a is None for a in nets.values()),
                       reasked=sum(len(v) - 1 for v in r["answers"].values()))
        else:
            r = AN.run(inst, lr, eps=EPS, delta=delta_cert, seed=seed, recal=spec.get("recal", True),
                       policy=spec.get("policy", "marg"), until=spec.get("until", "cert"), on_round=tracer,
                       answer=answer, err=err)
        st, en = r["stop"], r["end"]
        if answer is None:
            out.update(answer_model=am)
        out.update(questions=st["questions"], rounds=st["rounds"], certified=st["certified"], share=st["share"],
                   **summary(st))
        out.update({k: st[k] for k in ("sound", "bound", "bound_ess") if k in st})
        if answer is not None:
            out["yes"] = len(st["yes"])
        if spec.get("until") == "all":
            out["all"] = dict(questions=en["questions"], certified=en["certified"], share=en["share"], **summary(en))
            if answer is not None:
                out["all"]["yes"] = len(en["yes"])
        out["trace"] = r["trace"]
    else:                                       # upper: the answers taken as true through drd.run
        if "oracle" not in inspect.signature(drd.run).parameters:
            raise RuntimeError("drd.run has no oracle parameter yet")
        asked = {}

        def oracle(p):                          # records every answer Confirm reads (drd.run asks each once)
            y = (p in inst.truth) if spec.get("truth") else (table.get(p) is True)
            asked[p] = y
            return y

        r = drd.run(inst, "marg", EPS, seed=seed, delta=delta_cert, return_design=True, oracle=oracle)
        out.update(questions=r["questions"], certified=r.get("certified"), yes=sum(asked.values()),
                   **evaluate(b, r["design"], concluded(b, [p for p, y in asked.items() if y])))
    out["secs"] = round(time.time() - t0, 1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["rates", "run"])
    ap.add_argument("--answers", required=True)
    ap.add_argument("--models", default="qwen")
    ap.add_argument("--variants", default="ours,trust,const,unc,clf,L1,L2,A2,A3,A5,A7,A9,upper,hyfd")
    ap.add_argument("--datasets", default=",".join(AC.DATASETS))
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--cap", default="risk", choices=["risk", "force"])
    ap.add_argument("--max-cand", type=int, default=0)
    ap.add_argument("--prune", type=float, default=0.0)
    ap.add_argument("--out", default="auto_results.jsonl")
    ap.add_argument("--no-key", action="store_true", help="ablation K: no relation declares a key")
    ap.add_argument("--second", default="", help="short name of a second model whose answers (answers_<name>.jsonl in "
                    "the same directory) form the pair answer model with the first")
    a = ap.parse_args()
    if a.no_key:
        os.environ["CONFIRM_NO_KEY"] = "1"     # before any relation is loaded; worker processes inherit it
    if a.second:
        os.environ["CONFIRM_SECOND"] = a.second
    models = a.models.split(",")
    if a.cmd == "rates":
        res = report_rates(a.answers, models)
        with open(os.path.join(a.answers, "rates.json"), "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1, default=str)
        return
    jobs = []
    for v in a.variants.split(","):
        for ds in a.datasets.split(","):
            for m in ([None] if v in NO_MODEL else models):
                if v in ("L1", "L3"):
                    seeds = ["a", "b", "c"]
                elif v in ("hyfd", "L2", "clf"):
                    seeds = [0]
                else:
                    seeds = list(range(a.seeds))
                jobs += [(v, m, ds, s, a.answers, a.cap, a.max_cand, a.prune) for s in seeds]
    # a rerun resumes: the runs already in the output are skipped
    done = set()
    if os.path.exists(a.out):
        with open(a.out, encoding="utf-8") as fh:
            done = {(r["variant"], r["model"], r["dataset"], str(r["seed"])) for r in map(json.loads, fh)}
    todo = [j for j in jobs if (j[0], j[1], j[2], str(j[3])) not in done]
    print(len(jobs), "jobs", len(jobs) - len(todo), "already done", flush=True)
    # a worker killed by the system (out of memory) breaks the executor, which raises instead of waiting forever as
    # multiprocessing.Pool does; the caller reruns, and the rerun resumes
    with ProcessPoolExecutor(a.workers) as ex, open(a.out, "a", encoding="utf-8") as fh:
        for f in as_completed([ex.submit(job, j) for j in todo]):
            r = f.result()
            fh.write(json.dumps(r, default=str) + "\n")
            fh.flush()
            print(r["variant"], r["model"], r["dataset"], r["seed"], "good", r.get("reach_good"), "q", r.get("questions"),
                  "f1", round(r.get("f1", 0), 2), flush=True)


if __name__ == "__main__":
    main()
