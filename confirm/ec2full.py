"""
The interactive baseline of design note item 58: the EC^2 certificate on the question pool of Cert3NF.  Written after
the fifth simulated review (R3 W4): the baselines of item 52 ask candidates only, so by construction they cannot issue
the certificate of the paper; this one has the same questions and the same stopping rule as Cert3NF and differs in the
order of the questions alone.

Question pool Q(H, NEG): the open candidates X -> A (not implied by H, not refuted by a no answer) and the maximal-set
questions (M, A), M a maximal set of H for A that holds on the data (it contains the left-hand side of a candidate that
H does not imply) and that H and NEG do not decide -- the enumeration of the certificate phase of v5.py (known, update,
holds, maxsets), verbatim.
Hypotheses: the closed FD sets of posterior samples, as in the posterior certificate rbhyb (auto_noisy.Noisy, K = 80,
the nested prior and answer model, every model answer entering at once).  The designer's answers enter exactly:
a candidate asked directly through Noisy.designer; a candidate that H implies through Noisy.fix (rbhyb's rb); a
candidate that the answers refute (update) through Noisy.designer as a no, since it is a fact about that candidate
(under the sampler's independent-candidate model the refuted candidates are what the no answer observed, and the grid
posterior over (a, b) learns from them that the prior was too generous).  An answer on a set Z -> A filters the
samples: a no is implied by no hypothesis; a yes must be implied by the hypothesis's own candidates as long as some
candidate that is not refuted can explain it (closed world: the designer's yes is a true FD among the candidates); once
every candidate below it is refuted it is a fact Hx that every hypothesis holds (a true FD that is not minimal on the
data, which the closed candidate sets cannot express; item 32, F22), and a candidate counts as implied by a hypothesis
h when Sigma0 + Hx + h implies it.
Particle filter: every answer drops the inconsistent samples (exact conditioning); below max(10, K / 4) = 20 samples
(drd.run's few) fresh samples are drawn (class Sampler: Noisy's proposal and weights, the answers by rejection; the
pool of proposals is kept and filtered as long as it holds 4K consistent proposals of effective size K / 4; with
fewer the run goes on with what it has, and with no sample every score is 0).
Classes: the decision regions of ec2hyb (drd.decisions, drd.good_matrix, greedy cover; an uncovered sample is its own
class).  Score: EC^2's expected weight of cut edges (Golovin, Krause and Ray, NIPS 2010), edges joining samples of
different classes, uniform weights; a question splits the samples into those whose closure implies it and the rest.
One question a round, the largest score; ties by the marginal (share of samples implying the question) descending,
then candidates first when the marginal is at least 1/2 and maximal sets first otherwise, then (A, M) or the index.
A yes on a candidate joins H; a no joins NEG and refutes the candidates inside (update).  A yes on a maximal set:
  ec2full  QuickXplain at once (v5.py's qx, attributes of M ordered by the summed marginals of the open candidates
           inside M that hold them; attribute order without samples), the minimal X -> A joins H (no guesses);
  ec2nqx   M -> A joins H and the next question is EC^2's again (the pure EC^2 order).
Stop: the certificate of Cert3NF -- every maximal set of H that holds on the data is refuted -- or the budget.
Questions that H and NEG decide, or that the data refute, are not asked and not counted, as in v5.py.
Variants ec2full0 and ec2nqx0 use the learned prior alone (as rbhyb0 and v5s).

Usage (in confirm/):
  CONFIRM_TRUTH=full CONFIRM_ORACLE=gold CONFIRM_BATCH=2 python ec2full.py --answers llm_fresh2_full_q35 \
      --variants ec2full,ec2nqx --budget 100 --seeds 3 --workers 12 --out ec2full_results/ec2full_full_b100.jsonl
"""
import argparse, json, os, random, statistics, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
import bench
import auto_common as AC
import auto_confirm as C
import auto_answer as AA
import auto_noisy as AN
import drd
from price import closure, bits, maxsets

if os.environ.get("EC2FULL_DEV") == "1":          # local smoke tests on the development relations (llm_auto): the
    AC.FRESH[:] = []                               # confirmatory relations are not loaded

K, FEW, STARVE = 80, 20, 10
DEBUG = os.environ.get("EC2FULL_DEBUG") == "1"
VARIANTS = {"ec2full": (True, True), "ec2nqx": (False, True), "ec2full0": (True, False), "ec2nqx0": (False, False)}  # qx, llm


class Budget(Exception):
    pass


def closure_many(xs, F):
    c = xs.copy()
    while True:
        prev = c.copy()
        for l, r in F:
            c[(c & l) == l] |= r
        if (c == prev).all():
            return c


def reduce_fds(L, A):
    """the FDs (L[i], A[i]) without those whose left-hand side properly contains another's with the same right-hand
    side (and without duplicates); the closure is unchanged"""
    keep = np.ones(len(L), dtype=bool)
    for a in np.unique(A):
        idx = np.flatnonzero(A == a)
        l = L[idx]
        sub = (l[None, :] & ~l[:, None]) == 0                     # sub[i, j]: l[j] subset of l[i]
        np.fill_diagonal(sub, False)
        red = (sub & (l[None, :] != l[:, None])).any(axis=1)      # a proper subset exists
        dup = np.triu(l[None, :] == l[:, None], 1).any(axis=0)    # equal left-hand sides: keep the first
        keep[idx[red | dup]] = False
    return [(int(l), int(a)) for l, a in zip(L[keep], A[keep])]


def posterior(b, adir, model, llm):
    """(inst, Noisy, prior kind, answer model) of rbhyb's posterior for relation b (auto_confirm.job), or the learned
    prior alone (rbhyb0) when llm is False"""
    ds = b["name"]
    truth = set(b["truth"])
    kept = sorted(b["P"], key=bench.tiekey)
    if llm:
        AM = C.answer_model(adir, model)
        pk = AM.get("prior_for", {}).get(ds, "learned")
        am = AM["selected_for"][ds]
        A = C.read_answers(adir, model)
        table, conf = A.get("expert", {}).get(ds, {}), A.get("expert_conf", {}).get(ds, {})
    else:
        pk, am, table, conf = "learned", "none", {}, {}
    pi = C.prior_for(b, pk, adir, model)
    inst = drd.Instance(b["R"], b["sigma0"], kept, {p: pi[p] for p in kept}, [p for p in kept if p in truth],
                        name=ds, recal=True)
    if am == "hier":
        lr, err = None, ({p: table.get(p) for p in kept}, AA.err_grid(AM["params"][am][ds]))
    elif am == "none":
        lr, err = {p: 1.0 for p in kept}, None
    else:
        t = AA.lr_table(am, AM["params"][am][ds], b, table, conf)
        lr, err = {p: t[p] for p in kept}, None
    return inst, AN.Noisy(inst, lr, True, err), pk, am


class Sampler:
    """Posterior samples given every answer, with the proposal and the importance weights of auto_noisy.Noisy.sample:
    a grid point (a, b) and an error point from the grid posterior (which the designer's answers update as in rbhyb),
    every candidate drawn with its local posterior (1 for the candidates of H), the closure of the drawn set, and the
    weight prod L1 / L0 of the model evidence on the candidates that the closure adds.  Differences: a proposal whose
    closure holds a refuted candidate is rejected instead of weighted by EPS_H (the limit EPS_H -> 0 of Noisy's
    target; with hundreds of refutations Noisy's weights degenerate and its proposals reach the cap of 20,000 per call
    in the smoke test), and the effective sample size counts the remaining proposals.  The pool of proposals is kept
    across refreshes: an answer drops the proposals it contradicts at the candidate level (refuted candidates, and
    the candidates that the closed-world yes answers imply), which leaves a weighted sample of the new posterior, and
    the pool is rebuilt once fewer than 4K proposals or an effective size below K / 4 are left.  The systematic
    resampling runs in rounds of K, and a resampled hypothesis enters only if it passes the set-level check
    (rejection sampling from the candidate-level posterior, so the particles are samples of the posterior given every
    answer), until FEW particles are found or max_checks distinct proposals were checked."""

    def __init__(self, nz, max_m=20000, max_checks=2000):
        self.nz, self.inst = nz, nz.inst
        self.n = len(nz.P)
        self.lq = np.log(nz.L1 / nz.L0)                                 # [E, n]: the model's evidence per candidate
        self.max_m, self.max_checks = max_m, max_checks
        self.HV = self.lw = self.alive = None                            # the pool: packed closures, log weights
        self.chk = {}                                                   # proposal -> (version, (h, hF) or None)
        self.builds = self.proposals = self.direct = self.checked = 0
        self.ess_log = []
        self.every = np.arange(self.n, dtype=np.int64)

    def build(self, rnd, k):
        nz, inst, n = self.nz, self.inst, self.n
        post = nz.grid_post(nz.P)
        l1, l0 = nz.L1 * nz.H1[None, :], nz.L0 * nz.H0[None, :]
        rs = np.random.default_rng(rnd.getrandbits(63))
        cache = {}

        def prob(g):
            pr = cache.get(g)
            if pr is None:
                e, rho = g % nz.E, nz._rho(g)
                if len(cache) >= 400:
                    cache.clear()
                pr = cache[g] = np.where(nz.fixed, 1.0, rho * l1[e] / (rho * l1[e] + (1 - rho) * l0[e]))
            return pr
        refuted = nz.H1 < 1.0                                           # answered no: never in a hypothesis
        hvs, lws = [], []
        total, m, ess = 0, 4 * k, 0.0
        self.builds += 1
        while True:
            gs = rs.choice(len(post), size=m, p=post)
            for g in gs.tolist():
                e = g % nz.E
                s = rs.random(n) < prob(g)
                hv = inst.holds(inst.has_of(np.flatnonzero(s).tolist()), self.every)
                if (hv & refuted).any():
                    self.direct += 1
                    continue
                hvs.append(np.packbits(hv))
                lws.append(float(self.lq[e][hv & ~s].sum()))
            total += m
            if lws:
                lw = np.array(lws)
                w = np.exp(lw - lw.max())
                w /= w.sum()
                ess = 1 / float((w * w).sum())
                if ess >= k / 4 or total >= self.max_m:
                    break
            elif total >= self.max_m:
                break
            m *= 2
        self.proposals += total
        self.ess_log.append(ess)
        self.HV = np.stack(hvs) if hvs else np.zeros((0, (n + 7) // 8), dtype=np.uint8)
        self.lw = np.array(lws)
        self.alive = np.ones(len(lws), dtype=bool)
        self.chk = {}

    def bit(self, idx):
        """the bits of the candidates idx in every proposal of the pool, [m, len(idx)]"""
        idx = np.asarray(idx, dtype=np.int64)
        return (self.HV[:, idx >> 3] >> (7 - (idx & 7))) & 1

    def filter(self, need, forbid):
        """drop the proposals whose closure misses a candidate of need or holds one of forbid"""
        if self.HV is None or not self.alive.any():
            return
        if len(need):
            self.alive &= (self.bit(need) == 1).all(axis=1)
        if len(forbid):
            self.alive &= (self.bit(forbid) == 0).all(axis=1)

    def draw(self, rnd, k, few, need, forbid, check, version):
        """particles (hypothesis, its reduced FDs) by systematic resampling of the consistent proposals; check(h)
        returns the reduced FDs of h or None (set-level consistency), version marks what check depends on"""
        self.filter(need, forbid)
        w = None
        if self.HV is not None and self.alive.sum() >= 4 * k:
            lw = self.lw[self.alive]
            w = np.exp(lw - lw.max())
            w /= w.sum()
            if 1 / float((w * w).sum()) < k / 4:
                w = None
        if w is None:
            self.build(rnd, k)
            if not len(self.lw):
                return []
            lw = self.lw
            w = np.exp(lw - lw.max())
            w /= w.sum()
        live = np.flatnonzero(self.alive)
        c = np.cumsum(w)
        inst, P = self.inst, self.nz.P
        out, seen = [], set()
        for _ in range(50):
            u0 = rnd.random() / k
            idx = np.searchsorted(c, u0 + np.arange(k) / k, side="left")
            for j in idx.tolist():
                j = int(live[min(int(j), len(live) - 1)])
                r = self.chk.get(j)
                if r is None or r[0] != version:
                    pos = np.flatnonzero(np.unpackbits(self.HV[j])[:self.n]).tolist()
                    h = inst._cache(frozenset(P[i] for i in pos))["h"]
                    hF = check(h)
                    r = self.chk[j] = (version, None if hF is None else (h, hF))
                    self.checked += 1
                if r[1] is None:
                    self.alive[j] = False
                else:
                    out.append(r[1])
                seen.add(j)
            if len(out) >= few or len(seen) >= min(len(live), self.max_checks):
                break
        return out


def ec2_scores(X, labels):
    """EC^2 scores of the questions (columns of X, X[i, q] = sample i implies question q) under the class labels of
    the samples: the expected weight of the edges cut, an edge joining two samples of different classes"""
    n = X.shape[0]
    if n == 0:
        return np.zeros(X.shape[1]), np.zeros(X.shape[1])
    Lb = np.zeros((n, labels.max() + 1))
    Lb[np.arange(n), labels] = 1.0
    Xf = X.astype(float)
    W = (n * n - (Lb.sum(axis=0) ** 2).sum()) / 2
    CY = Xf.T @ Lb
    ny = Xf.sum(axis=0)
    wY = (ny * ny - (CY * CY).sum(axis=1)) / 2
    CN = (1 - Xf).T @ Lb
    nn = n - ny
    wN = (nn * nn - (CN * CN).sum(axis=1)) / 2
    return (ny / n) * (W - wY) + (nn / n) * (W - wN), ny / n


def class_labels(inst, ds, hs, G):
    """greedy cover of the samples by the decision regions (drd.classes_cover with G given), uncovered samples their
    own class; returns integer labels"""
    left, label = set(range(len(hs))), {}
    regions = {d: {i for i in left if G[d][i]} for d in ds}
    nxt = 0
    while left:
        d = max(regions, key=lambda d: len(regions[d] & left)) if regions else None
        got = regions[d] & left if d is not None else set()
        if not got:
            for i in left:
                label[i] = nxt
                nxt += 1
            break
        for i in got:
            label[i] = nxt
        nxt += 1
        left -= got
    return np.array([label[i] for i in range(len(hs))], dtype=np.int64)


def run(b, inst, nz, qx_mode, budget, seed):
    n = len(b["R"])
    full = (1 << n) - 1
    mask = lambda s: sum(1 << i for i in s)
    sig0 = [(mask(l), mask(r)) for l, r in b["sigma0"]]
    reach = [(mask(l), mask(r)) for l, r in AC.oracle(b)]          # what the designer answers from
    P = inst.P
    N = len(P)
    pix = {p: i for i, p in enumerate(P)}
    Lm = np.array([mask(p[0]) for p in P], dtype=np.int64)
    Am = np.array([mask(p[1]) for p in P], dtype=np.int64)
    cmap = {(int(Lm[i]), int(Am[i])): i for i in range(N)}
    by_a = {a: np.flatnonzero(Am == a) for a in sorted(set(Am.tolist()))}
    minfd = {}                                     # rhs bit -> lhs masks of the minimal FDs that hold on the data
    for p in b["P"] + b["implied0"]:
        minfd.setdefault(mask(p[1]), []).append(mask(p[0]))
    minfd = {a: np.array(ls, dtype=np.int64) for a, ls in minfd.items()}
    state = np.zeros(N, dtype=np.int8)             # 0 open, 1 implied, 2 refuted
    H, NEG = list(sig0), []
    rnd = random.Random(seed)
    st = {"q": 0, "free": 0, "data_no": 0, "cand_q": 0, "cand_no": 0, "max_q": 0, "max_no": 0, "qx_q": 0,
          "found": 0, "refreshes": 0, "accepted": 0, "rej_set": 0, "zero_rounds": 0, "rounds": 0, "attrs": [],
          "debug": []}
    parts = []                                     # particles: dicts h, hF (reduced FDs), vec (over P), label
    hver = [0]                                     # grows with H: caches keyed on it
    negc = {"ver": -1, "list": []}                 # per no answer (Z, A2): closure(Z, H) and the attributes whose
    trace, at100 = [], [None]                      # addition to it implies A2 under H (as a bitmask)
    starve = [-1]                                  # question index until which a refresh is not tried again
    single = np.array([1 << i for i in range(n)], dtype=np.int64)
    smp = Sampler(nz)
    fdobj = lambda z, a: AC.S.fd(tuple(i for i in range(n) if z >> i & 1), a.bit_length() - 1)
    split = {"ver": None, "Hx": []}                # the closed-world yes answers Yc and the facts Hx, per version

    def negs():
        """[(c, hit)] for NEG under the current H: c = closure(Z, H); hit holds attribute A iff closure(c + A, H)
        holds A2, i.e. the no answer refutes M -> A for every M within c (v5.py's known and update, cached)"""
        if negc["ver"] != hver[0]:
            negc["ver"], negc["list"] = hver[0], []
        lst = negc["list"]
        for z, a2 in NEG[len(lst):]:
            c = closure(z, H)
            cm = closure_many(c | single, H)
            hit = int(single[(cm & a2) != 0].sum())
            lst.append((c, hit))
        return lst

    def update():
        o = state == 0
        if not o.any():
            return
        imp = (closure_many(Lm, H) & Am) != 0
        state[o & imp] = 1
        for c, hit in negs():
            for a in bits(hit):
                idx = by_a.get(a)
                if idx is None:
                    continue
                state[idx[(state[idx] == 0) & ((Lm[idx] & ~c) == 0)]] = 2     # state[idx] is a copy: assign through idx

    def known(z, a):
        if closure(z, H) & a:
            return True
        for c, hit in negs():
            if z & ~c == 0 and hit & a:
                return False
        return None

    def holds(z, a):
        """Z -> A holds on the data iff Z contains the left-hand side of a minimal FD of the data (Thm. price (a))"""
        return a in minfd and bool(((minfd[a] & ~z) == 0).any())

    def version():
        return (hver[0], len(NEG))

    def parts_of_H():
        """(Yc, Hx, need): the confirmed FDs that the candidates not refuted can still explain (closed world: a
        hypothesis must imply them by itself), the others (facts of every hypothesis), and the candidates that
        Sigma0 + Yc implies (a hypothesis must hold them)"""
        if split["ver"] != version():
            Hy = H[len(sig0):]
            if Hy:
                Z = np.array([z for z, _ in Hy], dtype=np.int64)
                A = np.array([a for _, a in Hy], dtype=np.int64)
                keep = state != 2
                Fo = sig0 + list(zip(Lm[keep].tolist(), Am[keep].tolist()))
                ex = ((closure_many(Z, Fo) & A) != 0).tolist()
            else:
                ex = []
            Yc = [f for f, e in zip(Hy, ex) if e]
            Hx = [f for f, e in zip(Hy, ex) if not e]
            need = np.flatnonzero((closure_many(Lm, sig0 + Yc) & Am) != 0)
            split.update(ver=version(), Yc=Yc, Hx=Hx, need=need, Hxo=[fdobj(z, a) for z, a in Hx])
        return split["Yc"], split["Hx"], split["need"]

    def fds(hF):
        return sig0 + parts_of_H()[1] + hF

    def implies(pt, z, a):
        i = cmap.get((z, a))
        if i is not None:
            return bool(pt["vec"][i])
        return bool(closure(z, fds(pt["hF"])) & a)

    def vec_of(h):
        """the candidates that Sigma0 + Hx + h implies (inst's bitsets)"""
        parts_of_H()
        inst.has_of([])
        Fs = [inst.indices(p) for p in h] + [inst.indices(f) for f in split["Hxo"]]
        return inst.holds(inst._prop(inst._base0[:], inst._s0 + Fs, Fs), smp.every)

    def particle(h, hF):
        return {"h": h, "hF": hF, "vec": vec_of(h), "label": 0}

    def check(h):
        """the reduced FDs of h if Sigma0 + Hx + h implies every closed-world yes and no refuted FD, else None"""
        Yc, Hx, _ = parts_of_H()
        idx = np.array([pix[p] for p in h], dtype=np.int64)
        hF = reduce_fds(Lm[idx], Am[idx]) if len(idx) else []
        F = sig0 + Hx + hF
        if Yc:
            Z = np.array([z for z, _ in Yc], dtype=np.int64)
            A = np.array([a for _, a in Yc], dtype=np.int64)
            if ((closure_many(Z, F) & A) == 0).any():
                st["rej_set"] += 1
                return None
        if NEG:
            Z = np.array([z for z, _ in NEG], dtype=np.int64)
            A = np.array([a for _, a in NEG], dtype=np.int64)
            if ((closure_many(Z, F) & A) != 0).any():
                st["rej_set"] += 1
                if DEBUG and len(st["debug"]) < 6:
                    viol = [(z, a) for z, a in NEG if closure(z, F) & a]
                    st["debug"].append({"q": st["q"], "h": sorted(idx.tolist()), "hx": Hx, "viol": viol[:3],
                                        "refuted": int((state == 2).sum())})
                return None
        return hF

    def refresh():
        """fresh posterior samples given every answer, then the class labels of the particles"""
        st["refreshes"] += 1
        nz.fix([P[i] for i in np.flatnonzero(state == 1).tolist()])
        for i in np.flatnonzero(state == 2).tolist():        # a refuted candidate is a fact: it enters as a no
            if nz.H1[nz.ix[P[i]]] == 1.0 and nz.H0[nz.ix[P[i]]] == 1.0:
                nz.designer(P[i], False)
        _, _, need = parts_of_H()
        drawn = smp.draw(rnd, K, FEW, need, np.flatnonzero(state == 2), check, version())
        st["accepted"] += len(drawn)
        parts[:] = [particle(h, hF) for h, hF in drawn]
        if len(parts) < FEW:
            starve[0] = st["q"] + STARVE
        if not parts:
            return
        hs = [pt["h"] for pt in parts]
        answers = {P[i]: True for i in np.flatnonzero(state == 1).tolist()}
        answers.update({P[i]: False for i in np.flatnonzero(state == 2).tolist()})
        ds = drd.decisions(inst, answers, hs)
        G = drd.good_matrix(inst, ds, hs, C.EPS)
        for pt, lb in zip(parts, class_labels(inst, ds, hs, G).tolist()):
            pt["label"] = lb
        if len(inst._hc) > 50000:
            inst._hc.clear()

    def snapshot():
        """the state at the 100th answer of a longer run, for the consistency check with the budget-100 run"""
        D, pred = design()
        e = C.evaluate(b, D, pred)
        return {"certified": not maxset_pool(), "confirmed": len(H) - len(sig0), "refuted": len(NEG),
                "gold_good": e["gold_good"], "f1": e["f1"], "tables": len(D)}

    def ask(z, a, kind):
        k = known(z, a)
        if k is None and not holds(z, a):
            st["data_no"] += 1                    # the data refute Z -> A: no question (r satisfies Sigma*)
            k = False
        if k is not None:
            st["free"] += 1
            return k
        if st["q"] >= budget:
            raise Budget
        st["q"] += 1
        st[kind] += 1
        m = bin(z).count("1")
        st["attrs"].append(min(m, n - m) + 1)
        ans = bool(closure(z, reach) & a)
        if ans:
            H.append((z, a))
            hver[0] += 1
        else:
            NEG.append((z, a))
        i = cmap.get((z, a))
        if i is not None:
            nz.designer(P[i], ans)
        update()
        hx_before = len(split["Hx"])
        Yc, Hx, _ = parts_of_H()
        if not (ans and i is None and (z, a) in Hx):           # a fact drops no hypothesis
            parts[:] = [pt for pt in parts if implies(pt, z, a) == ans]
        if len(Hx) != hx_before:                  # the facts changed: what a hypothesis implies may have grown
            for pt in parts:
                pt["vec"] = vec_of(pt["h"])
        trace.append([st["q"], kind[0], int(ans), len(parts)])
        if st["q"] == 100 and budget > 100:
            at100[0] = snapshot()
        return ans

    def qx(base, last, cs, a):
        if last and ask(base, a, "qx_q"):
            return 0
        if len(cs) == 1:
            return cs[0]
        k = len(cs) // 2
        c1, c2 = cs[:k], cs[k:]
        m1 = sum(c1)
        x2 = qx(base | m1, m1, c2, a)
        x1 = qx(base | x2, x2, c1, a)
        return x1 | x2

    def maxset_pool():
        """the maximal-set questions of H that the certificate still needs (v5.py's enumeration)"""
        qs = []
        for a, idx in by_a.items():
            unimplied = state[idx] != 1
            if not unimplied.any():
                continue
            L = Lm[idx]
            for M in maxsets(H, a, full):
                inside = unimplied & ((L & ~M) == 0)
                if not inside.any() or known(M, a) is False:
                    continue
                qs.append((M, a))
        qs.sort(key=lambda q: (q[1], q[0]))
        return qs

    def design():
        """the 3NF synthesis of H itself (as v5.py) and the candidates it implies"""
        Hf = [fdobj(z, a) for z, a in H[len(sig0):]]
        D = inst._synth(inst._atomic(b["sigma0"] + Hf))[0]
        return D, {P[i] for i in np.flatnonzero(state == 1).tolist()}

    update()
    certified = False
    pool, pver, IMPm = [], -1, None
    try:
        while True:
            if pver != hver[0]:
                pool, pver, IMPm = maxset_pool(), hver[0], None
            else:
                keep = [k for k, (M, a) in enumerate(pool) if known(M, a) is not False]
                if len(keep) < len(pool):
                    pool = [pool[k] for k in keep]
                    IMPm = IMPm[:, keep] if IMPm is not None else None
            if not pool:
                certified = True
                break
            st["rounds"] += 1
            if len(parts) < FEW and st["q"] >= starve[0]:
                refresh()
                IMPm = None
            if not parts:
                st["zero_rounds"] += 1
            # the implication matrix: samples x questions (open candidates, then the maximal sets)
            opn = np.flatnonzero(state == 0)
            if parts:
                VEC = np.stack([pt["vec"] for pt in parts])
                if IMPm is None or IMPm.shape[0] != len(parts):
                    Ms = np.array([M for M, _ in pool], dtype=np.int64)
                    As = np.array([a for _, a in pool], dtype=np.int64)
                    IMPm = np.stack([(closure_many(Ms, fds(pt["hF"])) & As) != 0 for pt in parts])
                X = np.concatenate([VEC[:, opn], IMPm], axis=1)
                labels = np.array([pt["label"] for pt in parts], dtype=np.int64)
                score, marg = ec2_scores(X, labels)
            else:
                score = marg = np.zeros(len(opn) + len(pool))
            nc = len(opn)
            iscand = np.arange(len(score)) < nc
            tie = np.where(iscand, np.where(marg >= 0.5, 0, 1), np.where(marg >= 0.5, 1, 0))
            det = np.concatenate([opn, nc + np.arange(len(pool))])
            best = int(np.lexsort((det, tie, -marg, -score))[0])
            sc, mg = float(score[best]), float(marg[best])
            if best < nc:
                i = int(opn[best])
                ans = ask(int(Lm[i]), int(Am[i]), "cand_q")
                trace[-1] += [round(sc, 3), round(mg, 3)]
                if not ans:
                    st["cand_no"] += 1
                continue
            M, a = pool[best - nc]
            ans = ask(M, a, "max_q")
            trace[-1] += [round(sc, 3), round(mg, 3)]
            if not ans:
                st["max_no"] += 1
                continue
            if not qx_mode:
                continue                      # ec2nqx: M -> A is in H, the next question is EC^2's
            # ec2full: QuickXplain over the attributes of M, ordered by the marginals of the open candidates inside
            idx = by_a[a]
            ins = idx[(state[idx] == 0) & ((Lm[idx] & ~M) == 0)]
            if parts and len(ins):
                mg_c = np.stack([pt["vec"] for pt in parts])[:, ins].mean(axis=0)
                w = {bt: float(mg_c[(Lm[ins] & bt) != 0].sum()) for bt in bits(M)}
                order = sorted(w, key=lambda bt: (-w[bt], bt))
            else:
                order = list(bits(M))
            x = qx(0, 0, order, a)
            if not closure(x, H) & a:
                H.append((x, a))
                hver[0] += 1
                update()
                parts[:] = [pt for pt in parts if implies(pt, x, a)]
            st["found"] += 1
    except Budget:
        certified = False
    # ---------------- output ----------------
    D, pred = design()
    refuted = {P[i] for i in np.flatnonzero(state == 2).tolist()}
    opn = [P[i] for i in np.flatnonzero(state == 0).tolist()]
    Hf = [fdobj(z, a) for z, a in H[len(sig0):]]
    extra = [f for f in Hf if f not in pix]           # confirmed FDs outside the candidates

    def schema_certified(S):
        """the partial certificate per schema, as v5.py"""
        sm = mask(S)
        for a in bits(sm):
            if a not in by_a:
                continue
            idx = by_a[a]
            L, s = Lm[idx], state[idx]
            inside = (s != 1) & ((L & ~(sm & ~a)) == 0)
            if not inside.any():
                continue
            ms = {M & sm for M in maxsets(H, a, full)}
            ms = [M for M in ms if not any(M != M2 and M & ~M2 == 0 for M2 in ms)]
            for M in ms:
                if (((L & ~M) == 0) & inside).any() and known(M, a) is not False:
                    return False
        return True

    cert_s = sum(1 for S in D if schema_certified(S))
    names = b["names"]
    nm = lambda m: [names[i] for i in range(n) if m >> i & 1]
    out = {"certified": certified, "questions": st["q"], "oracle": AC.oracle_mode(), "free": st["free"],
           "data_no": st["data_no"], "rounds": st["rounds"], "cand_questions": st["cand_q"], "cand_no": st["cand_no"],
           "max_questions": st["max_q"], "max_no": st["max_no"], "qx_questions": st["qx_q"], "found": st["found"],
           "confirmed": len(H) - len(sig0), "refuted_answers": len(NEG), "open_left": len(opn),
           "facts": len(parts_of_H()[1]),
           "refreshes": st["refreshes"], "pool_builds": smp.builds, "proposals": smp.proposals,
           "rej_direct": smp.direct, "checked": smp.checked, "rej_set": st["rej_set"], "accepted": st["accepted"],
           "ess_median": round(statistics.median(smp.ess_log), 1) if smp.ess_log else None,
           "zero_rounds": st["zero_rounds"], "particles_end": len(parts),
           "attrs_median": statistics.median(st["attrs"]) if st["attrs"] else None,
           "attrs_max": max(st["attrs"]) if st["attrs"] else None,
           "schemata": len(D), "schemata_certified": cert_s, "at100": at100[0],
           "certificate": {"yes": [[nm(z), nm(a)[0]] for z, a in H[len(sig0):]],
                           "no": [[nm(z), nm(a)[0]] for z, a in NEG]}}
    out.update(C.evaluate(b, D, pred))
    if not certified and len(opn) <= 500:
        answers = {p: True for p in pred}
        answers.update({p: False for p in refuted})
        answers.update({f: True for f in extra})
        Dr = inst.robust(answers)
        ev = C.evaluate(b, Dr, pred)
        out.update({"fb_tables": len(Dr), "fb_lossless": ev["reach_lossless"], "fb_preserving": ev["reach_preserving"],
                    "fb_nf3": ev["reach_nf3"], "fb_good": ev["reach_good"], "fb_gold_good": ev["gold_good"]})
    out["trace"] = trace
    if DEBUG:
        out["debug"] = st["debug"]
    return out


def one(args):
    variant, ds, adir, model, budget, seed = args
    t0 = time.time()
    b = AC.load(ds)
    qx_mode, llm = VARIANTS[variant]
    inst, nz, pk, am = posterior(b, adir, model, llm)
    r = {"variant": variant, "dataset": ds, "truth": AC.truth_mode(), "seed": seed, "budget": budget,
         "candidates": len(b["P"]), "true": len(b["truth"]), "prior_kind": pk, "answer_model": am, "K": K,
         **run(b, inst, nz, qx_mode, budget, seed)}
    r["secs"] = round(time.time() - t0, 1)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", required=True)
    ap.add_argument("--model", default="q35")
    ap.add_argument("--datasets", default=",".join(AC.FRESH))
    ap.add_argument("--variants", default="ec2full,ec2nqx")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--budget", type=int, default=100)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    done = set()
    if os.path.exists(a.out):
        for x in open(a.out, encoding="utf-8"):
            if x.strip():
                r = json.loads(x)
                done.add((r["variant"], r["dataset"], r["seed"], r["budget"]))
    big = ["fresh_seats", "fresh_auctionmark", "fresh_geonames", "fresh_chembl", "fresh_pluto", "fresh_stats19"]
    dss = sorted(a.datasets.split(","), key=lambda d: (d not in big, big.index(d) if d in big else 0, d))
    jobs = [(v, ds, a.answers, a.model, a.budget, s) for ds in dss for s in range(a.seeds)
            for v in a.variants.split(",") if (v, ds, s, a.budget) not in done]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "a", encoding="utf-8") as fo:
        if a.workers <= 1:
            it = map(one, jobs)
        else:                                      # results are written as they complete, so a crash loses little
            ex = ProcessPoolExecutor(a.workers)
            it = (f.result() for f in as_completed([ex.submit(one, j) for j in jobs]))
        for r in it:
            fo.write(json.dumps(r) + "\n")
            fo.flush()
            print(f"{r['variant']:8s} {r['dataset']:20s} s{r['seed']} b{r['budget']:4d} cert {r['certified']!s:5s} "
                  f"good {r['gold_good']!s:5s} q {r['questions']:4d} (cand {r['cand_questions']}/{r['cand_no']}no, "
                  f"max {r['max_questions']}/{r['max_no']}no, qx {r['qx_questions']}, found {r['found']}, facts {r['facts']}) "
                  f"open {r['open_left']} refresh {r['refreshes']} builds {r['pool_builds']} prop {r['proposals']} "
                  f"(direct {r['rej_direct']}) checked {r['checked']} (set {r['rej_set']}) particles {r['accepted']} "
                  f"ess {r['ess_median']} zero {r['zero_rounds']} schemata {r['schemata_certified']}/{r['schemata']} "
                  f"f1 {r['f1']:.2f} {r['secs']}s", flush=True)


if __name__ == "__main__":
    main()
