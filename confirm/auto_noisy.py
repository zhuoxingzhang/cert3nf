"""
Confirm with an expert who errs (design notes, section 6 and component selection).  The answers come from a recorded
table: one answer per question, never repeated, since repeated answers of one model are not independent.  An answer
enters through its likelihood ratio LR_p = L(A_p | p true) / L(A_p | p false), given by an answer model of
auto_answer.py (constant error rates alpha = P(yes | false), beta = P(no | true) are the special case
LR = (1 - beta) / alpha for yes and beta / (1 - alpha) for no).

Posterior.  P(h | A) is proportional to P(h) prod_q L(A_q | q in h).  Only the ratio of the two likelihoods matters,
so L(A_q | true) = LR_q / (1 + LR_q) and L(A_q | false) = 1 / (1 + LR_q).  With recalibration, a candidate has prior
probability sigmoid(a logit rho + b) under the grid prior of drd on (a, b), and the answers update (a, b) through their
marginal likelihoods m_q = rho' L(A_q | true) + (1 - rho') L(A_q | false), which ignore implications; the weights below
correct for that.

Sampler (importance resampling).  Draw (a, b) from that grid posterior, then every unasked candidate with rho' and
every asked q with its local posterior r_q = rho' L(A_q | true) / m_q, and close the drawn set S.  Target over proposal
leaves the weight prod_q L(A_q | q in close(S)) / L(A_q | q in S): only the asked candidates that the closure adds
change it.  K hypotheses are resampled systematically from M proposals; M doubles while the effective sample size is
below K / 4.

Questions.  Looking up an answer costs nothing, so the cost of a run is its number of rounds.  A round asks the
ceil(BATCH * open) informative unasked candidates first in the order of the policy: "marg", largest posterior marginal
(the greedy policy of Theorem 7.7, which seeks the true FDs a design must preserve), or "unc", marginal closest to 1/2
(uncertainty sampling, which seeks the candidates whose truth the posterior knows least).  The certificate depends on
the answers only, not on their order.  With until="cert" a run stops when a design is certified on a fresh sample; with
until="all" it records the first certificate and then asks all remaining candidates in one round (ablation A8: the
quality of asking everything), which costs one more posterior instead of a round per 5% of the candidates.
Every round can be traced (on_round), which gives the anytime curves of FD quality and design validity.

The designer in the loop.  run_hybrid: the model's recorded answers enter for every candidate at once, and a designer
answers the questions that Confirm picks, a few per round, until a design is certified or the designer has answered
a budget of questions (design note, component selection item 20).  A designer's answer is exact: it multiplies the likelihood of
the value not given by EPS_H.  It enters the grid posterior like any answer, so the designer's answers also calibrate
the prior (a, b) and the model's error rates on this relation.

Trusted answers.  run(answer=...) is the same loop with the answers taken as true (variant trust of auto_confirm.py):
the posterior of drd given the answers, sampled exactly, in place of the answer model.  Asking in the same rounds
isolates the answer model in the ablation; drd.run, one question per round, would take about 53 hours for the 36,486
candidates of tpch_lineitem_orders when wrong answers never certify (7,750 questions in 3.8 h on the server).
"""
import math, random
import numpy as np
import drd

BATCH = 0.05
EPS_H = 1e-9    # the likelihood of the value that the designer did not answer


class Noisy:
    def __init__(self, inst, lr, recal=True, err=None):
        """lr: candidate -> likelihood ratio of its recorded answer.  err (the hier answer model): (answers, grid) with
        answers candidate -> True, False or None and grid [(alpha, beta, weight)]; the grid of (a, b) is then crossed
        with the error rates, which the answers update like (a, b).  Without err there is one error point of weight 1,
        and every number drawn is the same as before err existed.  A third element of err (the hpair answer model)
        maps a candidate to the ratio of its second answer, which multiplies the likelihoods at every error point."""
        self.inst, self.recal = inst, recal
        self.P = list(inst.P)
        self.ix = {p: i for i, p in enumerate(self.P)}
        self.lg = np.array([math.log(inst.pi[p] / (1 - inst.pi[p])) for p in self.P])
        if err is None:
            r = np.array([lr[p] for p in self.P], dtype=float)
            self.L1, self.L0, ew = (r / (1 + r))[None, :], (1 / (1 + r))[None, :], [1.0]
        else:
            ans, eg = err[:2]
            yes = np.array([ans.get(p) is True for p in self.P])
            no = np.array([ans.get(p) is False for p in self.P])
            self.L1 = np.stack([np.where(yes, 1 - be, np.where(no, be, 1.0)) for _, be, _ in eg])
            self.L0 = np.stack([np.where(yes, al, np.where(no, 1 - al, 1.0)) for al, _, _ in eg])
            if len(err) > 2:
                r = np.array([err[2][p] for p in self.P], dtype=float)
                self.L1, self.L0 = self.L1 * (r / (1 + r))[None, :], self.L0 * (1 / (1 + r))[None, :]
            ew = [w for _, _, w in eg]
        self.E = len(ew)
        self.H1, self.H0 = np.ones(len(self.P)), np.ones(len(self.P))     # the designer's answers (run_hybrid)
        self.fixed = np.zeros(len(self.P), dtype=bool)                    # set, not drawn (fix)
        grid = drd.GRID if recal else [(1.0, 0.0)]
        prior = drd.GRID_PRIOR if recal else [1.0]
        self.A = np.array([a for a, _ in grid])
        self.B = np.array([b for _, b in grid])
        # combined index g = i * E + e: (a, b) of grid point i and error point e
        self.lw0 = (np.log(np.array(prior))[:, None] + np.log(np.array(ew))[None, :]).ravel()

    def _rho(self, g):
        i = g // self.E
        return 1 / (1 + np.exp(-(self.A[i] * self.lg + self.B[i])))

    def grid_post(self, asked):
        lw = self.lw0.copy()
        if asked and len(lw) > 1:
            q = np.array([self.ix[p] for p in asked])
            r = 1 / (1 + np.exp(-(self.A[:, None] * self.lg[q][None, :] + self.B[:, None])))
            h1, h0 = self.H1[q][None, :], self.H0[q][None, :]
            fx = self.fixed[q][None, :]
            add = np.stack([np.log(np.where(fx, self.L1[e, q][None, :],
                                            r * self.L1[e, q][None, :] * h1 + (1 - r) * self.L0[e, q][None, :] * h0))
                            .sum(axis=1) for e in range(self.E)], axis=1)
            lw = lw + add.ravel()
        w = np.exp(lw - lw.max())
        return w / w.sum()

    def sample(self, asked, rnd, k, max_m=20000):
        inst, n = self.inst, len(self.P)
        post = self.grid_post(asked)
        mask = np.zeros(n, dtype=bool)
        for p in asked:
            mask[self.ix[p]] = True
        l1 = np.where(mask[None, :], self.L1 * self.H1[None, :], 1.0)
        l0 = np.where(mask[None, :], self.L0 * self.H0[None, :], 1.0)
        qs = [self.ix[p] for p in asked]
        qa = np.array(qs, dtype=np.int64)
        if self.E == 1:
            lq = [[math.log(l1[0, i] / l0[0, i]) for i in qs]]
        else:
            lq = np.log(l1[:, qa] / l0[:, qa]) if qs else np.zeros((self.E, 0))

        def prob(g):                                # the proposal of S given grid point g, cached (at most 400)
            pr = cache.get(g)
            if pr is None:
                e, rho = g % self.E, self._rho(g)
                if len(cache) >= 400:
                    cache.clear()
                pr = cache[g] = np.where(self.fixed, 1.0,
                                         np.where(mask, rho * l1[e] / (rho * l1[e] + (1 - rho) * l0[e]), rho))
            return pr
        rs = np.random.default_rng(rnd.getrandbits(63))
        cache = {}
        m = 4 * k
        # A proposal's weight needs only which asked candidates its closure adds, read off the closure's bitsets; the
        # hypothesis itself is built only for the proposals that resampling selects, from their uniforms drawn again
        # (PCG64.advance to the proposal's place in the stream).  Same numbers, same weights, same samples as building
        # every proposal's hypothesis.
        while True:
            lw = []
            gs = rs.choice(len(post), size=m, p=post)
            st0 = rs.bit_generator.state
            for g in gs.tolist():
                pr, e = prob(g), g % self.E
                s = rs.random(n) < pr
                l = 0.0
                if qs:                              # the closure may add an asked candidate that was not drawn
                    has = inst.has_of(np.flatnonzero(s).tolist())
                    for t in np.flatnonzero(inst.holds(has, qa) & ~s[qa]).tolist():
                        l += lq[e][t]
                lw.append(l)
            lw = np.array(lw)
            w = np.exp(lw - lw.max())
            w /= w.sum()
            ess = 1 / float((w * w).sum())
            if ess >= k / 4 or m >= max_m:
                break
            m *= 2
        u0 = rnd.random() / k
        c = np.cumsum(w)
        idx = np.searchsorted(c, u0 + np.arange(k) / k, side="left")
        made, out = {}, []
        for j in idx.tolist():
            j = min(int(j), m - 1)
            h = made.get(j)
            if h is None:
                bg = np.random.PCG64()
                bg.state = st0
                bg.advance(j * n)
                s = np.random.Generator(bg).random(n) < prob(int(gs[j]))
                h = made[j] = inst.close([self.P[i] for i in np.flatnonzero(s).tolist()])
            out.append(h)
        return out, ess


    def fix(self, hY):
        """Rao-Blackwellization (design note, item 23).  A candidate t of H_Y = close(sigma0 + the designer's yes
        answers) that the designer did not answer is true in every hypothesis drawn, since the yes answers are drawn
        with probability 1 - O(EPS_H); whether t itself is drawn changes no closure.  So t is set rather than drawn,
        and its answer enters the grid posterior through L(A_t | true) alone: it calibrates the model's error rates
        but, being implied, says nothing about the prior's (a, b).  Drawing t and correcting by the importance weight
        targets the same posterior, with a weight factor L1 / L0 for every t not drawn, which collapses the effective
        sample size once H_Y holds dozens of candidates."""
        self.fixed[:] = False
        for p in hY:
            i = self.ix.get(p)
            if i is not None and self.H1[i] == 1.0 and self.H0[i] == 1.0:
                self.fixed[i] = True

    def designer(self, p, a):
        """the designer's exact answer a on candidate p; None withdraws an answer (item 26: a tie or a conflict)"""
        i = self.ix[p]
        self.H1[i] = self.H0[i] = 1.0
        if a is True:
            self.H0[i] = EPS_H
        elif a is False:
            self.H1[i] = EPS_H

    def local_true(self, asked):
        """per candidate, P(true | prior, model's answer) averaged over the grid posterior, closure aside: the
        evidence on a candidate other than the designer's answers (item 26)"""
        w = self.grid_post(asked)
        out = np.zeros(len(self.P))
        for g in np.flatnonzero(w > 1e-12).tolist():
            e, rho = g % self.E, self._rho(g)
            out += w[g] * rho * self.L1[e] / (rho * self.L1[e] + (1 - rho) * self.L0[e])
        return out


def onesided_evidence(lr, err, recal):
    """(lr, recal, err) of Noisy with the model's evidence against a candidate left out (item 25): under hier and
    hpair a no counts as no answer, and a likelihood ratio below 1 counts as 1"""
    up = lambda m: {p: max(v, 1.0) for p, v in m.items()}
    if err is None:
        return up(lr), recal, None
    return None, recal, (({p: None if a is False else a for p, a in err[0].items()}, err[1])
                         + ((up(err[2]),) if len(err) > 2 else ()))


def net_answer(v):
    """the designer's net answer on a candidate from the answers v: the majority, None on a tie"""
    y, n = v.count(True), v.count(False)
    return None if y == n else y > n


def designer_risk(inst, nz, every, hum, nets, yes, conflict, d, em, eps, small=1e-3):
    """R and the answers d depends on, with their r_q (design note, item 26).  r_q is the local posterior probability
    that what d assumes of q is wrong: the prior and the model's answer give P(q true) (Noisy.local_true), and every
    answer of the designer counts with error rate em.  d assumes a net yes and a conflict (a net no implied by the net
    yes answers) true, and a net no false.  d depends on a net yes q if it is not good once q is taken from Y, on a net
    no q if it is not good once q joins Y, and always on a conflict; an answer with r_q below small is counted in R
    without this test (the union bound only grows)."""
    pt = nz.local_true(every)
    R, dep = 0.0, {}
    for p, v in hum.items():
        a = nets[p]
        if a is None:                           # a tie: the sampler treats q as unanswered
            continue
        y, n = v.count(True), v.count(False)
        t, f = pt[nz.ix[p]] * (1 - em) ** y * em ** n, (1 - pt[nz.ix[p]]) * em ** y * (1 - em) ** n
        r = f / (t + f) if a is True or p in conflict else t / (t + f)
        if r < small:
            R += r
            continue
        if p in conflict:
            on = True
        elif a is True:
            on = not inst.good(d, inst.close([q for q in yes if q != p]), eps)
        else:
            on = not inst.good(d, inst.close(yes + [p]), eps)
        if on:
            R += r
            dep[p] = r
    return R, dep


def run_hybrid(inst, lr, human, budget=100, hbatch=5, eps=0, delta=0.1, seed=0, K=80, recal=True, policy="marg",
               on_round=None, err=None, sound=False, rb=False, onesided=False, designer_eps=None, reask=1):
    """The designer in the loop: lr and err as in run, for the model's answer on every candidate; human (candidate,
    number of its earlier answers -> bool) answers hbatch questions a round, chosen by the policy among the candidates
    not yet put to the designer, until a design is certified or the designer has answered budget questions.  The
    certificate is checked on a fresh sample, as in run.  Returns the last state (the certificate's, if one was issued),
    the trace, the questions in the order first asked and every answer; a state's questions are the designer's.

    sound (design note, component selection item 21): a certified design must also be good under H_Y, the closure of sigma0 and
    the designer's yes answers Y, so that the FDs the designer confirmed alone justify its tables and its losslessness;
    both samples of the certificate need an effective sample size of at least K / 4; while the design of most mass is
    not good under H_Y, the candidates true in every sample but not implied by H_Y are informative too, since only
    the designer's yes makes them part of H_Y; candidates in H_Y are not asked, and a round skips a candidate that its
    earlier picks true in every sample imply (as if asked one at a time).

    rb (item 23, with sound): the sampler sets the candidates of H_Y that the designer did not answer instead of
    drawing them (Noisy.fix).

    onesided (item 25, with sound): the completeness of a certificate, and the bound, are checked on a second
    posterior in which the model's answers count only where they speak for a candidate (onesided_evidence); the
    sound decision of most mass under the first posterior is the one checked.

    designer_eps (item 26, with sound and rb): the designer errs with probability designer_eps.  The sampler takes the
    net answers (net_answer) as exact, with ties and conflicts (a net no implied by the net yes answers) withdrawn,
    and the certificate pays for the designer: P(d bad) <= P(d bad | net answers right) + R, R the sum of r_q over the
    answers d depends on (designer_risk).  d needs a share of at least 1 - (delta - R) on both samples.  While
    R > delta / 2 a round first asks again the answers d depends on, most likely wrong first, up to reask answers a
    candidate; conflicts, then ties, are asked again first in every round."""
    rnd = random.Random(seed)
    nz = Noisy(inst, lr, recal, err)
    one = onesided_evidence(lr, err, recal) if onesided else None
    # without evidence against any candidate (no model, or one that never says no) the two posteriors coincide
    nzc = Noisy(inst, *one) if one is not None and (one[0], one[2]) != (lr, err) else nz
    tolerant = bool(designer_eps)
    every, hum, rounds, trace = list(inst.P), {}, 0, []
    few = max(10, K // 4)
    min_ess = K / 4 if sound else 0
    assert sound or not (rb or onesided)
    assert not tolerant or (sound and rb and nzc is nz)
    while True:
        nets = {p: net_answer(v) for p, v in hum.items()}
        nq = sum(len(v) for v in hum.values())
        yes = [p for p, a in nets.items() if a is True]
        hY = inst.close(yes) if sound else None
        conflict = [p for p, a in nets.items() if a is False and p in hY] if tolerant else []
        if tolerant:                            # the sampler's exact answers: the net ones, less ties and conflicts
            for p, a in nets.items():
                nz.designer(p, None if p in conflict else a)
        if rb:
            nz.fix(hY)
            nzc.fix(hY)
        samples, ess = nz.sample(every, rnd, K)
        ds = drd.decisions(inst, {p: a for p, a in nets.items() if a is not None and p not in conflict}, samples)
        if sound:
            ds = list(dict.fromkeys(ds + [inst.alg(hY)]))
        G = drd.good_matrix(inst, ds, samples, eps)
        cand = [x for x in ds if inst.good(x, hY, eps)] if sound else ds
        R, dep, d_sound = None, {}, None
        if tolerant:
            d_sound = d = drd.covering(inst, cand, samples, eps, 1.0, G)
            if d is not None:
                R, dep = designer_risk(inst, nz, every, hum, nets, yes, conflict, d, designer_eps, eps)
                if R >= delta or len(samples) < few or ess < min_ess or \
                        sum(G[d]) < (1 - (delta - R) - 1e-12) * len(samples):
                    d = None
        elif nzc is nz:
            d = drd.covering(inst, cand, samples, eps, delta, G)
            if d is not None and (len(samples) < few or ess < min_ess):
                d = None
        else:
            d = drd.covering(inst, cand, samples, eps, 1.0, G)
            if d is not None:
                cs, cess = nzc.sample(every, rnd, K)
                if len(cs) < few or cess < min_ess or \
                        sum(inst.good(d, h, eps) for h in cs) < (1 - delta - 1e-12) * len(cs):
                    d = None
        if d is not None:
            new, ess2 = nzc.sample(every, rnd, 2 * K)
            if len(new) < few or ess2 < 2 * min_ess or \
                    sum(inst.good(d, h, eps) for h in new) < (1 - (delta - (R or 0.0)) - 1e-12) * len(new):
                d = None
        certified = d is not None
        if d is None:
            d = drd.covering(inst, ds, samples, eps, 1.0, G)
        cnt = {p: 0 for p in inst.P}
        for h in samples:
            for p in h:
                if p in cnt:
                    cnt[p] += 1
        n = max(len(samples), 1)
        state = {"questions": nq, "rounds": rounds, "certified": certified, "design": d,
                 "share": sum(G[d]) / len(samples) if samples and d in G else 0.0, "ess": ess,
                 "marg": {p: c / n for p, c in cnt.items()}}
        if sound:
            state["sound"] = inst.good(d, hY, eps)
        if tolerant:
            state.update(risk=R, conflicts=len(conflict))
        if on_round is not None:
            trace.append(on_round(state))
        # asked again first: conflicts, ties, then (while R > delta / 2) the answers d depends on, most likely wrong first
        again = [p for p in conflict if len(hum[p]) < reask] + \
            [p for p, a in nets.items() if a is None and len(hum[p]) < reask]
        if R is not None and R > delta / 2:
            again += [p for p in sorted(dep, key=lambda q: -dep[q]) if p not in again and len(hum[p]) < reask]
        open_ = [p for p in inst.P if p not in hum and not (sound and p in hY)]
        if certified or nq >= budget or not (open_ or again):
            break
        verify = sound and not state["sound"]
        informative = [p for p in open_ if 0 < cnt[p] < len(samples) or (verify and cnt[p] == len(samples))] or open_
        if policy == "unc":
            key = lambda q: (abs(2 * cnt[q] - len(samples)), -inst.pi[q])
        else:
            key = lambda q: (-cnt[q], -inst.pi[q])
        pick, sure_yes, implied = again[:min(hbatch, budget - nq)], [], hY
        for p in sorted(informative, key=key):
            if len(pick) >= min(hbatch, budget - nq):
                break
            if sound and sure_yes and p in implied:
                continue
            pick.append(p)
            if sound and cnt[p] == len(samples):
                sure_yes.append(p)
                implied = inst.close(yes + sure_yes)
        for p in pick:
            a = bool(human(p, len(hum.get(p, ()))))
            hum.setdefault(p, []).append(a)
            if not tolerant:
                nz.designer(p, a)
                if nzc is not nz:
                    nzc.designer(p, a)
        rounds += 1
        if len(inst._hc) > 50000:
            inst._hc.clear()
    if sound:       # the completeness bound of item 22, on a fresh sample drawn after the loop (its answers unchanged)
        new, ess3 = nzc.sample(every, rnd, 2 * K)
        us = sorted(inst.unpreserved(state["design"], h) for h in new)
        state["bound"] = us[math.ceil((1 - delta) * len(us)) - 1] if us and ess3 >= 2 * min_ess else None
        state["bound_ess"] = ess3
    return {"stop": state, "end": state, "trace": trace, "asked": list(hum), "answers": hum}


def run(inst, lr, eps=0, delta=0.1, seed=0, K=80, recal=True, batch=BATCH, policy="marg", until="cert",
        on_round=None, answer=None, err=None):
    """lr: candidate -> likelihood ratio of its recorded answer (err: see Noisy).  Returns the state at the first certificate ("stop";
    the last state if no design was certified), the last state ("end"), the trace of on_round(state) and the answers
    in the order asked.  A state holds the questions, rounds, certified, the design of largest share with that share,
    and the posterior marginals.
    answer (candidate -> bool) instead of lr takes the answers as true (variant trust): the same rounds, policy,
    certificate and records, with the posterior of drd given the answers, sampled exactly (inst.sample, with its own
    recalibration), and decisions that see the answers.  Its ess is the number of samples, which falls short of K or
    is 0 when the answers contradict each other; then, as in drd.run, nothing is certified on fewer than max(10, K/4)
    samples, and without samples the design is synthesized from the yes answers.  Its states also hold the yes
    answers (what trust concludes)."""
    rnd = random.Random(seed)
    if answer is None:
        nz = Noisy(inst, lr, recal, err)
        draw = lambda k: nz.sample(asked, rnd, k)
    else:
        answers = {}

        def draw(k):
            hs = inst.sample(answers, rnd, k)
            return hs, float(len(hs))
    asked, rounds, trace, stop = [], 0, [], None
    few = max(10, K // 4)
    while True:
        if answer is not None:
            inst.forget(answers)
        samples, ess = draw(K)
        ds = drd.decisions(inst, {} if answer is None else answers, samples)
        G = drd.good_matrix(inst, ds, samples, eps)
        d = drd.covering(inst, ds, samples, eps, delta, G)
        if d is not None and len(samples) < few:
            d = None
        if d is not None:
            new, _ = draw(2 * K)
            if len(new) < few or sum(inst.good(d, h, eps) for h in new) < (1 - delta - 1e-12) * len(new):
                d = None
        certified = d is not None
        if d is None:
            d = drd.covering(inst, ds, samples, eps, 1.0, G)
        if d is None:                               # no sample: the trusted answers contradict each other
            d = inst.alg(inst.close([p for p, a in answers.items() if a]))
        cnt = {p: 0 for p in inst.P}
        for h in samples:
            for p in h:
                if p in cnt:
                    cnt[p] += 1
        n = max(len(samples), 1)
        state = {"questions": len(asked), "rounds": rounds, "certified": certified, "design": d,
                 "share": sum(G[d]) / len(samples) if samples and d in G else 0.0, "ess": ess,
                 "marg": {p: c / n for p, c in cnt.items()}}
        if answer is not None:
            state["yes"] = [p for p, a in answers.items() if a]
        if on_round is not None:
            trace.append(on_round(state))
        if certified and stop is None:
            stop = state
        done = set(asked)
        open_ = [p for p in inst.P if p not in done]
        if (stop is not None and until == "cert") or not open_:
            break
        informative = [p for p in open_ if 0 < cnt[p] < len(samples)] or open_
        if policy == "unc":
            key = lambda q: (abs(2 * cnt[q] - len(samples)), -inst.pi[q])
        else:
            key = lambda q: (-cnt[q], -inst.pi[q])
        b = len(open_) if stop is not None else max(1, math.ceil(batch * len(open_)))   # after the certificate:
        new_q = sorted(informative, key=key)[:b] if b < len(open_) else open_             # the rest at once
        asked += new_q
        if answer is not None:
            for p in new_q:
                answers[p] = answer(p)
        rounds += 1
        if len(inst._hc) > 50000:                    # keep the per-hypothesis caches of drd bounded
            inst._hc.clear()
    return {"stop": stop or state, "end": state, "trace": trace, "asked": asked}
