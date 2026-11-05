"""
Cert3NF, the frozen method with the question order of its confirmatory evaluation.  The question pool, the stopping
rule (every maximal set of H that holds on the data is refuted), the certificate and the price are those of v5.py; the order of the questions and the probabilities that decide it change.  The designer's answers are the only thing
the method learns from about the relation; nothing in the choice of a question reads its truth.

The order (v6.py, item 60).  At every answer: an open candidate X -> A with cl_H(X) = M is asked instead of the maximal set M -> A
(dominance: its no refutes M -> A all the same, its yes is the FD at one answer instead of two); else a believed candidate
(rho' >= 1/2) while the direct questions answered no are fewer than b = 10; else the maximal set with the smallest expected
waste p (1 + e_M), e_M the answers that a yes on M -> A costs beyond the FD's own (the function expected_extra).

Four rules, each optional through the variant's specification ("v6s|lc+hone+kf+rl"):
  lc: the latent class of a left-hand side (class LCAdvisor): the answers on one candidate of X move the others of X.
  hone: the first guess before the maximal set.  A maximal set M -> A whose likeliest candidate the guess rule would take
    costs two answers when it holds and the guess hits; asking the candidate first costs one.  With p the rate of maximal
    sets that hold and h the rate of first guesses that hit given that M -> A holds (Beta(1, 1), counted in the run), the
    swap wastes 1 - p h answers where the plain order wastes p, so it is taken iff p (1 + h) > 1.  After a miss M -> A is
    asked at once, and the miss counts as a guess of that maximal set.  Since h < 1, a swap needs p > 1/2, that is more
    maximal sets that held than sets refuted, so the misses on refuted sets are at most the FDs found.
  kf: among the believed candidates, the one with the largest rho'_c (1 + number of other believed FDs that H + {c} implies):
    a yes settles those FDs without an answer of their own.  Only the order changes.
  rl: the reuse of a left-hand side.  A true FD X -> A that is not minimal on the data has no candidate of its own: the candidate is
    a proper subset of X, and the designer refutes it.  So a maximal set that holds because of that FD gives the guesses nothing to hit,
    and QuickXplain pays.  A left-hand side that the designer has confirmed for another attribute is the likely X (lc: Z = 1).  After
    M -> A holds, such a left-hand side inside M that is no candidate of A is tried first, the most used first, while the rate of
    these tries in this run (Beta(1, 1)) reaches the guess threshold.  Its yes narrows the search as the yes on M -> A did: the guesses
    and QuickXplain go on inside it, with its thresholds.  The tries count among the g guesses, so the bound below stands.
Bound, for an exact designer on data that satisfy the true FDs: b + m_r + min(m_r, d) + d + sum over the FDs found through a
maximal set of (g + J(|X|, |M|)), with d the FDs that enter H.  The misses of hone are counted among the g guesses when M -> A
holds, and by min(m_r, d) when it is refuted.  p counts the maximal sets asked and the hits of hone, not the dominance questions.

The designer: exact (the default) or flips with probability eps (--eps, --seeds, seeded by the question,
auto_confirm.designer_flip).  --careful: mechanism c of item 34, v5tol.py's rule with this file's order: every answer is kept, H and
the no answers come from the majority, and a certificate needs every premise answered twice with a majority.  An unresolved
conflict does not certify (v5tol.py lets it through).
--theta: the data refute Z -> A only if more than a share theta of the records would have to go (g3, v5tau.Violations; item 43).
Variants: v6s (statistics only: the main form), v6 (with the answers of an LLM), v5, v5s, v5n (v5.py reproduced, identity check).

Usage (in confirm/):
  CONFIRM_TRUTH=full CONFIRM_ORACLE=gold python v6f.py --answers llm_fresh_full_q35_ms --variants 'v6s|lc+hone+kf' --out F
  V6_TRACE=1 adds a per-answer trace to every row (kind, answer, the probabilities the rule compared).
"""
import argparse, hashlib, json, math, os, statistics, time
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
import auto_common as AC
import auto_confirm as C
import auto_answer as AA
import drd
from price import closure, bits, maxsets

BUDGET, CAP, BELIEVE, GUESS, HEAD, CH = 100, 10, 0.5, 0.2, 5, 64
TRACE = os.environ.get("V6_TRACE") == "1"
with open(os.path.abspath(__file__), "rb") as _fh:
    CODE = hashlib.md5(_fh.read()).hexdigest()[:12]
TOKENS = {"lc", "hone", "kf", "rl"}
REASK = 3


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


def logit(v):
    v = min(max(float(v), 1e-6), 1 - 1e-6)
    return math.log(v / (1 - v))


class Advisor:
    """rho' per candidate (v5.py, verbatim).  llm is None (statistics only), {"kind": "hier", "err": [(alpha, beta,
    weight)], "answers": {p: True/False/None}} or {"kind": "lr", "lr": {p: ratio}, "answers": ...}."""

    def __init__(self, P, pis, llm, lazy=True):
        self.P, N = P, len(P)
        self.ix = {p: i for i, p in enumerate(P)}
        lg = np.array([logit(pis[p]) for p in P])
        A = np.array([a for a, _ in drd.GRID])
        B = np.array([b for _, b in drd.GRID])
        self.rho = 1 / (1 + np.exp(-(A[:, None] * lg[None, :] + B[:, None])))        # [G, N]
        self.kind = "none" if llm is None else llm["kind"]
        if self.kind == "hier":
            eg = llm["err"]
            self.al = np.array([e[0] for e in eg])
            self.be = np.array([e[1] for e in eg])
            lwE = np.log(np.array([e[2] for e in eg]))
        else:
            lwE = np.zeros(1)
        if self.kind != "none":
            T = llm["answers"]
            self.yes = np.array([T.get(p) is True for p in P])
            self.no = np.array([T.get(p) is False for p in P])
        if self.kind == "lr":
            self.lr = np.array([llm["lr"].get(p, 1.0) for p in P])
            ys = self.lr[self.yes]
            self.lr_yes = float(np.median(ys)) if len(ys) else 1.0
        self.E = len(lwE)
        self.queried = np.zeros(N, dtype=bool) if (lazy and self.kind != "none") else np.ones(N, dtype=bool)
        self.lw = lwE[:, None] + np.log(np.array(drd.GRID_PRIOR))[None, :]            # [E, G]
        for s in range(0, N, CH):
            self.lw += self._logm(np.arange(s, min(N, s + CH))).sum(axis=2)
        self.answered = {}
        self.observations = 0

    def _L(self, idx, force=None):
        if force == "yes" and self.kind != "none":
            q = y = np.ones(len(idx), dtype=bool)
            n = np.zeros(len(idx), dtype=bool)
        else:
            q = self.queried[idx]
            if self.kind != "none":
                y, n = self.yes[idx] & q, self.no[idx] & q
        if self.kind == "hier":
            L1 = np.where(y[None, :], 1 - self.be[:, None], np.where(n[None, :], self.be[:, None], 1.0))
            L0 = np.where(y[None, :], self.al[:, None], np.where(n[None, :], 1 - self.al[:, None], 1.0))
        elif self.kind == "lr":
            r = np.where(y, self.lr_yes if force == "yes" else self.lr[idx], np.where(n, self.lr[idx], 1.0))
            L1, L0 = (r / (1 + r))[None, :], (1 / (1 + r))[None, :]
        else:
            L1 = L0 = np.ones((1, len(idx)))
        return L1, L0

    def _parts(self, idx, force=None):
        L1, L0 = self._L(idx, force)
        r = self.rho[:, idx]
        return r[None] * L1[:, None, :], (1 - r)[None] * L0[:, None, :]

    def _logm(self, idx):
        a, c = self._parts(idx)
        return np.log(a + c)

    def weights(self):
        w = np.exp(self.lw - self.lw.max())
        return w / w.sum()

    def rho_prime(self, idx, force=None):
        idx = np.asarray(idx, dtype=np.int64)
        out = np.empty(len(idx))
        if len(idx) == 0:
            return out
        w = self.weights()
        for s in range(0, len(idx), CH):
            j = idx[s:s + CH]
            a, c = self._parts(j, force)
            out[s:s + CH] = np.tensordot(w, a / (a + c), axes=([0, 1], [0, 1]))
        return out

    def query(self, idx):
        new = np.array([i for i in idx if not self.queried[i] and i not in self.answered], dtype=np.int64)
        if len(new) == 0:
            return 0
        old = self._logm(new).sum(axis=2)
        self.queried[new] = True
        self.lw += self._logm(new).sum(axis=2) - old
        return len(new)

    def observe(self, i, y):
        if i in self.answered:
            return
        a, c = self._parts(np.array([i]))
        a, c = a[:, :, 0], c[:, :, 0]
        self.lw += np.log(a if y else c) - np.log(a + c)
        self.answered[i] = bool(y)
        self.observations += 1


def logits(v):
    v = np.clip(v, 1e-9, 1 - 1e-9)
    return np.log(v / (1 - v))


class LCAdvisor(Advisor):
    """rho' under the latent class of a left-hand side X: X is a determinant (Z = 1) or not, and a candidate X -> A can hold
    only if Z = 1.  Given Z = 1 a candidate holds with its rho' / P(Z = 1), P(Z = 1) = max rho' over the candidates of X / h,
    and h is the rate at which a candidate holds given that another one of X holds (the pool without the target, every
    relation once, then the answers of this run).  A yes on a candidate of X settles Z = 1, so its other candidates get
    at least h (with the answers of an LLM: h moved by the likelihood ratio of its answer).  A no on c leaves the likelihood
    1 - rho'_c / P(Z = 1) under Z = 1 and 1 under Z = 0, and Bayes' rule scales the other candidates of X by the result."""

    def attach(self, h0, lhs_masks):
        keys = {}
        self.gid = np.array([keys.setdefault(m, len(keys)) for m in lhs_masks], dtype=np.int64)
        self.gkey = keys
        ng = len(keys)
        order = np.argsort(self.gid, kind="stable")
        cuts = np.flatnonzero(np.diff(self.gid[order])) + 1
        self.members = np.split(order, cuts)
        self.has_yes = np.zeros(ng, dtype=bool)
        self.logF = np.zeros(ng)
        self.pz = np.full(ng, 0.5)
        self.touched = np.zeros(ng, dtype=bool)
        self.h = [h0 * 2.0, 2.0]
        self._ck, self._cb, self._c0 = None, None, None

    def forget(self):
        """careful mode: an answer was overturned, the classes start again from the net answers"""
        self.has_yes[:] = False
        self.logF[:] = 0.0
        self.pz[:] = 0.5
        self.touched[:] = False

    def rate(self):
        return self.h[0] / self.h[1]

    def base_all(self):
        k = (self.observations, int(self.queried.sum()))
        if k != self._ck:
            self._cb = Advisor.rho_prime(self, np.arange(len(self.P)))
            self._c0 = self.weights().sum(axis=0) @ self.rho      # rho' without the answers of the LLM
            self._ck = k
        return self._cb

    def note(self, z, y):
        g = self.gkey.get(z)
        if g is not None and self.has_yes[g]:
            self.h[1] += 1
            self.h[0] += bool(y)

    def evidence(self, idx, ys):
        idx = np.asarray(idx, dtype=np.int64)
        ys = np.asarray(ys, dtype=bool)
        base = self.base_all()
        gs = self.gid[idx]
        hr = self.rate()
        for g in np.unique(gs).tolist():
            pz = float(np.clip(base[self.members[g]].max() / hr, 1e-6, 0.99))
            sel = gs == g
            if ys[sel].any():
                self.has_yes[g] = True
            nos = idx[sel][~ys[sel]]
            if len(nos):
                self.logF[g] += float(np.log(np.maximum(1 - np.minimum(base[nos] / pz, 0.999), 1e-3)).sum())
            self.pz[g] = pz
            self.touched[g] = True

    def evidence_lhs(self, x):
        g = self.gkey.get(x)
        if g is not None:
            self.has_yes[g] = True
            self.touched[g] = True

    def rho_prime(self, idx, force=None):
        idx = np.asarray(idx, dtype=np.int64)
        if len(idx) == 0:
            return np.empty(0)
        base = self.base_all()
        out = Advisor.rho_prime(self, idx, force) if force is not None else base[idx].copy()
        g = self.gid[idx]
        sel = self.touched[g]
        if not sel.any():
            return out
        g = g[sel]
        v = out[sel]
        F = np.exp(self.logF[g])
        pz = self.pz[g]
        fac = F / (pz * F + 1 - pz)
        if self.kind == "none":
            lift = self.rate()
        else:
            lift = 1 / (1 + np.exp(-(logits(self.rate()) + logits(v) - logits(self._c0[idx[sel]]))))
        out[sel] = np.where(self.has_yes[g], np.maximum(v, lift), np.minimum(v * fac, 1 - 1e-9))
        return out


def advisor_for(b, adir, model, llm, lazy):
    ds = b["name"]
    if not llm:
        pi = C.prior_for(b, "learned", adir, model)
        return Advisor(b["P"], pi, None, lazy), "learned", "none"
    AM = C.answer_model(adir, model)
    if not set(AM["selected_for"]) <= set(C.benches()):
        raise RuntimeError(f"{adir}: answer models fitted on relations that this run does not know (CONFIRM_BATCH?)")
    pk, am = AM["prior_for"][ds], AM["selected_for"][ds]
    pi = C.prior_for(b, pk, adir, model)
    A = C.read_answers(adir, model)
    T, Cf = A.get("expert", {}).get(ds, {}), A.get("expert_conf", {}).get(ds, {})
    ans = {p: AA.first(T.get(p)) for p in b["P"]}
    if am == "hier":
        spec = {"kind": "hier", "err": AA.err_grid(AM["params"][am][ds]), "answers": ans}
    elif am == "none":
        spec = None
    else:
        spec = {"kind": "lr", "lr": AA.lr_table(am, AM["params"][am][ds], b, T, Cf), "answers": ans}
    return Advisor(b["P"], pi, spec, lazy), pk, am


_RATE = {}


def class_rate(ds):
    """h of LCAdvisor at the start of a run: the mean, over the relations of the pool other than ds, of the rate at which a
    candidate holds given that another candidate with the same left-hand side holds"""
    bs = C.benches()
    rates = []
    for d in AC.pool():
        if d == ds:
            continue
        if d not in _RATE:
            tr, g = set(bs[d]["truth"]), {}
            for p in bs[d]["P"]:
                g.setdefault(p[0], []).append(p in tr)
            w = sum(sum(ys) * (len(ys) - 1) for ys in g.values())
            _RATE[d] = sum(sum(ys) * (sum(ys) - 1) for ys in g.values()) / w if w else None
        if _RATE[d] is not None:
            rates.append(_RATE[d])
    return statistics.mean(rates)


def expected_extra(rhos_desc, qx_cost):
    """e_M: the expected answers beyond the yes on M -> A and the FD's own answer, under v5's guess rule, given that
    M -> A holds and the open candidates inside M have the probabilities rhos_desc (descending) under the advisor's
    independent model.  The g-th guess is the likeliest candidate still open; it hits with probability rho_g / p_g,
    p_g = 1 - prod_{i >= g} (1 - rho_i) (v5 renormalizes over the candidates still open), and it is taken while that
    probability reaches max(GUESS, 1 / qx_cost) and fewer than qx_cost guesses were taken; a miss wastes one answer;
    when the guesses stop, QuickXplain costs qx_cost answers of which one stands for the FD."""
    thr = max(GUESS, 1.0 / qx_cost)
    e, reach = 0.0, 1.0                           # reach: probability that the g-th guess is taken
    rest = [1.0] * (len(rhos_desc) + 1)           # prod_{i >= g} (1 - rho_i)
    for g in range(len(rhos_desc) - 1, -1, -1):
        rest[g] = rest[g + 1] * (1 - min(rhos_desc[g], 1 - 1e-12))
    for g, rho in enumerate(rhos_desc):
        if g >= qx_cost:
            break
        hit = min(rho / max(1 - rest[g], 1e-12), 1.0)
        if hit < thr:
            break
        e += reach * (1 - hit)
        reach *= (1 - hit)
    return e + reach * (qx_cost - 1)


def net(v):
    y = v.count(True)
    return None if 2 * y == len(v) else 2 * y > len(v)


def margin(v):
    return abs(2 * v.count(True) - len(v))


def run(b, adv, cap, discovery, guess, mode, mcheap=False, rules=(), eps=0.0, seed=0, careful=False, theta=0.0, viol=None):
    """one run.  adv None: no advisor (rho' = 1/2, attribute order).  mode "v5": the two phases of v5.py (exact designer,
    no tolerance); "v6": the order of the header, decided at every answer."""
    n = len(b["R"])
    full = (1 << n) - 1
    mask = lambda s: sum(1 << i for i in s)
    sig0 = [(mask(l), mask(r)) for l, r in b["sigma0"]]
    reach = [(mask(l), mask(r)) for l, r in AC.oracle(b)]          # what the designer answers from
    P = b["P"]
    pix = {p: i for i, p in enumerate(P)}
    by = {}
    for p in P:
        by.setdefault(mask(p[1]), []).append(p)
    minfd = {}
    for p in P + b["implied0"]:
        minfd.setdefault(mask(p[1]), []).append(mask(p[0]))
    minfd = {a: np.array(ls, dtype=np.int64) for a, ls in minfd.items()}
    cand = {a: (np.array([mask(p[0]) for p in ps], dtype=np.int64), np.full(len(ps), 0.5), ps,
                np.array([pix[p] for p in ps], dtype=np.int64)) for a, ps in by.items()}
    state = {a: np.zeros(len(ps), dtype=np.int8) for a, ps in by.items()}     # 0 open, 1 implied, 2 refuted
    attrs = [1 << i for i in range(n)]
    nocand = (np.zeros(0, dtype=np.int64), np.zeros(0), [], np.zeros(0, dtype=np.int64))
    nostate = np.zeros(0, dtype=np.int8)
    H, NEG, conflict, hist = list(sig0), [], [], {}      # hist: question (Z, A) -> the designer's answers
    st = {"q": 0, "free": 0, "data_no": 0, "disc_q": 0, "disc_no": 0, "max_q": 0, "max_asked": 0, "max_no": 0,
          "guess_q": 0, "guess_hit": 0, "qx_q": 0, "found": 0, "llm_q": 0, "attrs": [], "direct_late": 0,
          "rule_direct": 0, "rule_max": 0, "dominated": 0, "hone_q": 0, "hone_no": 0, "reuse_q": 0, "reuse_hit": 0, "confirm_q": 0, "reask_q": 0, "theta_q": 0}
    rp = np.full(len(P), 0.5)
    ry = np.full(len(P), 0.5)
    where = {int(i): (a, k) for a, (_, _, _, idx) in cand.items() for k, i in enumerate(idx)}
    poss = []
    fresh = [True]
    trace = [] if TRACE else None
    last = {}                                      # what the trace records about the pending question
    seen_re = {a: np.zeros(len(ps), dtype=bool) for a, ps in by.items()}      # settled candidates the classes have seen
    first_stat, set_stat = [1, 2], [1, 2]          # Beta(1, 1) counts, hits + 1 and trials + 2: h and p of the rule hone
    missed = set()
    found_lhs, reuse_stat = {}, [1, 2]             # confirmed left-hand side -> FDs found with it; the Beta(1, 1) counts of the rule rl

    def refresh():
        if adv is not None:
            rp[:] = adv.rho_prime(np.arange(len(P)))
            ry[:] = adv.rho_prime(np.arange(len(P)), "yes") if adv.kind != "none" else rp
            poss[:] = [(i,) + where[i] for i in np.flatnonzero(ry >= BELIEVE / 5).tolist()]
            for a, (_, R_, _, idx) in cand.items():
                R_[:] = rp[idx]
        fresh[0] = True

    def observe(i, y):
        if adv is not None:
            adv.observe(i, y)
            if adv.observations % 10 == 0:
                fresh[0] = False

    def update():
        for a, (L, _, _, _) in cand.items():
            s = state[a]
            o = s == 0
            if not o.any():
                continue
            imp = (closure_many(L, H) & a) != 0
            s[o & imp] = 1
            for z, a2 in NEG:
                c = closure(z, H)
                if closure(c | a, H) & a2:
                    s[(s == 0) & ((L & ~c) == 0)] = 2
        if "lc" in rules and adv is not None:
            for a, (_, _, _, idx_) in cand.items():
                new_ = (state[a] != 0) & ~seen_re[a]
                if new_.any():
                    seen_re[a] |= new_
                    adv.evidence(idx_[new_], state[a][new_] == 1)
                    fresh[0] = False

    def known(z, a):
        if closure(z, H) & a:
            return True
        for z2, a2 in NEG:
            c = closure(z2, H)
            if z & ~c == 0 and closure(c | a, H) & a2:
                return False
        return None

    def exact(z, a):
        """Z -> A holds on the data iff Z contains the left-hand side of a minimal FD of the data (Thm. price (a))"""
        return a in minfd and bool(((minfd[a] & ~z) == 0).any())

    def holds(z, a):
        """Z -> A holds on the data up to the tolerance"""
        return exact(z, a) or (theta > 0 and viol.g3(z, a) <= theta)

    def designer(z, a, k):
        """the k-th answer to Z -> A: the truth, flipped with probability eps"""
        truth = bool(closure(z, reach) & a)
        if eps <= 0:
            return truth
        return truth != C.designer_flip(b["name"], seed, (tuple(i for i in range(n) if z >> i & 1), (a.bit_length() - 1,)), eps, k)

    def rebuild():
        """careful mode: H and the no answers from the net answers of the history; a net no that H implies is a conflict"""
        H[:] = sig0 + [k for k, v in hist.items() if net(v) is True]
        no = [k for k, v in hist.items() if net(v) is False]
        conflict[:] = [k for k in no if closure(k[0], H) & k[1]]
        NEG[:] = [k for k in no if k not in conflict]
        for s in state.values():
            s[:] = 0
        update()

    def put(z, a, kind):
        """the question Z -> A goes to the designer; returns the net answer (a tie counts as no: pending settles it next)"""
        if st["q"] >= BUDGET:
            raise Budget
        st["q"] += 1
        st[kind] += 1
        m = bin(z).count("1")
        st["attrs"].append(min(m, n - m) + 1)
        if not exact(z, a):
            st["theta_q"] += 1                    # a question that the tolerance leaves to the designer
        v = hist.setdefault((z, a), [])
        v.append(designer(z, a, len(v)))
        if "lc" in rules and adv is not None and len(v) == 1 and a in cand and (cand[a][0] == z).any():
            adv.note(z, v[-1])
        if careful:
            if len(v) > 1 and net(v[:-1]) is True and net(v) is not True and z in found_lhs:
                found_lhs[z] -= 1                 # an overturned yes takes its left-hand side back
                if not found_lhs[z]:
                    del found_lhs[z]
            if "lc" in rules and adv is not None and len(v) > 1 and net(v) != net(v[:-1]):
                adv.forget()
                for s_ in seen_re.values():
                    s_[:] = False
            rebuild()
        elif v[-1]:
            H.append((z, a))
            update()
        else:
            NEG.append((z, a))
            update()
        if trace is not None:
            trace.append({"q": st["q"], "kind": kind, "ans": int(v[-1]), "m": m, **last})
            last.clear()
        return net(v) is True

    def ask(z, a, kind):
        k = known(z, a)
        if k is None and not holds(z, a):
            st["data_no"] += 1
            k = False
        if k is not None:
            st["free"] += 1
            return k
        return put(z, a, kind)

    def qx(base, last_, cs, a):
        if last_ and ask(base, a, "qx_q"):
            return 0
        if len(cs) == 1:
            return cs[0]
        k = len(cs) // 2
        c1, c2 = cs[:k], cs[k:]
        m1 = sum(c1)
        x2 = qx(base | m1, m1, c2, a)
        x1 = qx(base | x2, x2, c1, a)
        return x1 | x2

    # ---------------- the two steps of v5 ----------------
    def believed(thr=BELIEVE):
        """(G, r): the target cover of the believed hypothesis (rho' >= thr), most likely first, without the FDs
        that H implies, and the rho' of the open candidates it was drawn from; None when the lazy LLM queried a
        candidate first (v5.py's discovery loop, verbatim, one iteration; the head of G is the likeliest open
        candidate that H does not imply, or the choice of the rule kf)"""
        opn = [i for i, a, k in poss if state[a][k] == 0 and i not in adv.answered]
        unq = [i for i in opn if not adv.queried[i]]
        if unq:
            bel = [i for i, v in zip(unq, adv.rho_prime(unq, "yes")) if v >= thr]
            if bel and adv.query(bel):
                return None, None
        r = dict(zip(opn, adv.rho_prime(opn))) if opn else {}
        order = sorted((i for i in opn if r[i] >= thr), key=lambda i: -r[i])
        Ft, G = list(H), []
        for i in order:
            l, a = mask(P[i][0]), mask(P[i][1])
            if closure(l, Ft) & a:
                continue
            G.append(i)
            Ft.append((l, a))
        if "kf" in rules and len(order) > 1 and G:
            # the question with the largest expected number of believed FDs settled by its yes: a yes on X -> A settles
            # every believed FD that H + {X -> A} implies, which then needs no answer of its own
            live = [(i, mask(P[i][0]), mask(P[i][1])) for i in order]
            cl_ = {i: closure(l, H) for i, l, _ in live}
            bs_, bi_ = -1.0, None
            for i, l, a in live:
                n_ = 1
                for j, l2, a2 in live:
                    if j != i and l & ~cl_[j] == 0 and closure(cl_[j] | a, H) & a2:
                        n_ += 1
                s_ = float(r[i]) * n_
                if s_ > bs_ + 1e-12:
                    bs_, bi_ = s_, i
            G = [bi_] + [i for i in G if i != bi_]
        return G, r

    def disc_step(i, r, hone=False):
        l, a = mask(P[i][0]), mask(P[i][1])
        if trace is not None:
            last.update({"rho": round(float(r[i]), 4)})
        ans = ask(l, a, "hone_q" if hone else "disc_q")
        observe(i, ans)
        if ans:
            found_lhs[l] = found_lhs.get(l, 0) + 1
        if not ans:
            st["hone_no" if hone else "disc_no"] += 1
        if not fresh[0]:
            refresh()
        return ans

    def best_maxset():
        """the next maximal set of H that holds on the data: the smallest expected waste p (1 + e_M), or v5.py's largest p"""
        best = None
        for a in (attrs if theta > 0 else cand):
            L, R_, _, _ = cand.get(a, nocand)
            s = state.get(a, nostate)
            if theta == 0 and not (s != 1).any():
                continue
            for M in maxsets(H, a, full):
                if known(M, a) is False or not holds(M, a):
                    continue
                ins = (s == 0) & ((L & ~M) == 0)
                if adv is None:
                    key = (bool(ins.any()), -a, -M)
                else:
                    py = 1 - float(np.exp(np.log1p(-np.minimum(R_[ins], 1 - 1e-12)).sum())) if ins.any() else 0.0
                    if mcheap:
                        qx_cost = math.ceil(math.log2(max(bin(M).count("1"), 2))) + 1
                        e = expected_extra(np.sort(R_[ins])[::-1].tolist(), qx_cost) if ins.any() else 0.0
                        key = (-py * (1 + e), -a, M)
                    else:
                        key = (py, -a, M)
                if best is None or key > best[0]:
                    best = (key, M, a, ins)
        return best

    def guessable(M, a, ins):
        """the guess rule of cert_step would take the likeliest open candidate inside M"""
        o2 = ins & (state[a] == 0)
        if not o2.any():
            return False
        R_ = cand[a][1]
        py = 1 - float(np.exp(np.log1p(-np.minimum(R_[o2], 1 - 1e-12)).sum()))
        qx_cost = math.ceil(math.log2(max(bin(M).count("1"), 2))) + 1
        return float(R_[o2].max()) / max(py, 1e-12) >= max(GUESS, 1.0 / qx_cost)

    def cert_step(best):
        key, M, a, ins = best
        L, R_, ps, idx = cand.get(a, nocand)
        st["max_q"] += 1
        if trace is not None:
            py = 1 - float(np.exp(np.log1p(-np.minimum(R_[ins], 1 - 1e-12)).sum())) if ins.any() else 0.0
            top = float(R_[ins].max()) if ins.any() else 0.0
            last.update({"py": round(py, 4), "k": int(ins.sum()), "top": round(top, 4)})
        miss = (M, a) in missed
        set_stat[1] += 1
        if not ask(M, a, "max_asked"):
            st["max_no"] += 1
            return
        set_stat[0] += 1
        if miss:
            first_stat[1] += 1
        if "lc" in rules and not fresh[0]:
            refresh()
        x = None
        if adv is not None and len(L):            # no candidate of A: nothing to guess, QuickXplain at once
            top = np.flatnonzero(ins)[np.argsort(-R_[ins], kind="stable")][:HEAD]
            if adv.query(idx[top].tolist()):
                rq = adv.rho_prime(idx[top])
                R_[top] = rq
                rp[idx[top]] = rq
            qx_cost = math.ceil(math.log2(max(bin(M).count("1"), 2))) + 1
            guesses = 1 if miss else 0
            narrow, first = None, not miss
            if "rl" in rules and guess:
                for x0 in sorted((l_ for l_ in found_lhs if l_ and l_ & ~M == 0 and l_ != M), key=lambda l_: (-found_lhs[l_], bin(l_).count("1"), l_)):
                    if guesses >= qx_cost or reuse_stat[0] / reuse_stat[1] < max(GUESS, 1.0 / qx_cost):
                        break
                    if (L == x0).any() or known(x0, a) is not None or not holds(x0, a):
                        continue
                    guesses += 1
                    ans = ask(x0, a, "reuse_q")
                    reuse_stat[1] += 1
                    reuse_stat[0] += bool(ans)
                    if "lc" in rules and not fresh[0]:
                        refresh()
                    if ans:
                        st["reuse_hit"] += 1
                        narrow = x0
                        ins = ins & ((L & ~x0) == 0)
                        qx_cost = math.ceil(math.log2(max(bin(x0).count("1"), 2))) + 1
                        top = np.flatnonzero(ins)[np.argsort(-R_[ins], kind="stable")][:HEAD]
                        if adv.query(idx[top].tolist()):
                            rq = adv.rho_prime(idx[top])
                            R_[top] = rq
                            rp[idx[top]] = rq
                        break
            while guess and guesses < qx_cost:
                o2 = ins & (state[a] == 0)
                if not o2.any():
                    break
                guesses += 1
                py = 1 - float(np.exp(np.log1p(-np.minimum(R_[o2], 1 - 1e-12)).sum()))
                cond = R_ * o2 / max(py, 1e-12)
                i = int(np.argmax(cond))
                if cond[i] < max(GUESS, 1.0 / qx_cost):
                    break
                if trace is not None:
                    last.update({"cond": round(float(cond[i]), 4), "rho": round(float(R_[i]), 4)})
                ans = ask(int(L[i]), a, "guess_q")
                observe(int(idx[i]), ans)
                if ans:
                    found_lhs[int(L[i])] = found_lhs.get(int(L[i]), 0) + 1
                if "lc" in rules and not fresh[0]:
                    refresh()
                if first:
                    first = False
                    first_stat[1] += 1
                    first_stat[0] += bool(ans)
                if ans:
                    x = int(L[i])
                    st["guess_hit"] += 1
                    break
            py = 1 - float(np.exp(np.log1p(-np.minimum(R_[ins], 1 - 1e-12)).sum()))
            cond = R_ * ins / max(py, 1e-12)
            w = {bt: float(cond[(L & bt) != 0].sum()) for bt in bits(M)}
            order = sorted(w, key=lambda bt: (-w[bt], bt))
            if narrow is not None:
                order = [bt for bt in order if bt & narrow]
        else:
            order = list(bits(M))
        if x is None:
            x = qx(0, 0, order, a) if order else 0      # M is empty: A is constant
            if "lc" in rules and adv is not None and not (L == x).any():
                adv.evidence_lhs(x)
                fresh[0] = False
            if not closure(x, H) & a:
                if careful:                       # H holds only FDs that the designer answered
                    ask(x, a, "confirm_q")
                else:
                    H.append((x, a))
                    update()
            if closure(x, H) & a:
                found_lhs[x] = found_lhs.get(x, 0) + 1
        st["found"] += 1
        if not fresh[0]:
            refresh()

    # ---------------- careful mode (item 34, mechanism c) ----------------
    def targets():
        """the maximal sets of H that hold on the data, each with its attribute"""
        return [(M, a) for a in attrs for M in maxsets(H, a, full) if holds(M, a)]

    def refutes(key, M, a):
        """whether the net no on key refutes M -> A under H"""
        c = closure(key[0], H)
        return M & ~c == 0 and bool(closure(c | a, H) & key[1])

    def premises():
        """D_yes: the net yes answers without the redundant ones; D_no: a cover of the targets by the net no answers without
        the redundant ones.  If they are right, so is the certificate.  None with a conflict"""
        if conflict:
            return None
        yes = [k for k, v in hist.items() if net(v) is True]
        keep = list(yes)
        for k in sorted(yes, key=lambda q: margin(hist[q])):         # the weakest answers go first if redundant
            if closure(k[0], sig0 + [q for q in keep if q != k]) & k[1]:
                keep.remove(k)
        T = targets()
        cover = {}
        for k, v in hist.items():
            if net(v) is False:
                cv = {t for t, (M, a) in enumerate(T) if refutes(k, M, a)}
                if cv:
                    cover[k] = cv
        cnt = {}
        for cv in cover.values():
            for e in cv:
                cnt[e] = cnt.get(e, 0) + 1
        for k in sorted(cover, key=lambda q: margin(hist[q])):
            if all(cnt[e] > 1 for e in cover[k]):
                for e in cover[k]:
                    cnt[e] -= 1
                del cover[k]
        st["d_yes"], st["d_no"] = len(keep), len(cover)
        return keep + list(cover)

    def pending():
        """the question to ask again before anything else: for a conflict, the weakest answer among the no and a minimal set
        of yes answers that imply it; a tie"""
        for k in conflict:
            yes = [q for q, v in hist.items() if net(v) is True]
            sub = list(yes)
            for q in sorted(yes, key=lambda q: -margin(hist[q])):
                if closure(k[0], sig0 + [x for x in sub if x != q]) & k[1]:
                    sub.remove(q)
            for q in sorted(sub + [k], key=lambda q: margin(hist[q])):
                if len(hist[q]) < REASK:
                    return q
        for k, v in hist.items():
            if net(v) is None and len(v) < REASK:
                return k
        return None

    update()
    if adv is not None:
        refresh()
    sound = capped = certified = False
    try:
        if mode == "v5":
            # ---------------- discovery, then certification (v5.py) ----------------
            if discovery and adv is not None:
                while True:
                    if not fresh[0]:
                        refresh()
                    G, r = believed()
                    if G is None:
                        continue
                    if not G:
                        sound = True
                        break
                    if st["disc_no"] >= cap:
                        capped = True
                        break
                    disc_step(G[0], r)
            st["switch_q"] = st["q"]
            if not fresh[0]:
                refresh()
            while True:
                best = best_maxset()
                if best is None:
                    certified = True
                    break
                cert_step(best)
        else:
            # ---------------- v6: the order of the header, decided at every answer ----------------
            while True:
                if careful:
                    k = pending()
                    if k is not None:
                        put(*k, "reask_q")
                        continue
                if not fresh[0]:
                    refresh()
                best = best_maxset()
                if best is None:      # no maximal set of H that holds on the data is left: an open candidate
                    if not careful:   # X -> A would lie in one, so none is open either
                        certified = True
                        break
                    dep = premises()
                    if dep is None:   # a conflict that cannot be asked again
                        break
                    if all(len(hist[k]) >= 2 for k in dep):
                        certified = True
                        break
                    put(*next(k for k in dep if len(hist[k]) < 2), "reask_q")
                    continue
                key, M, a2, ins = best
                L, R_, ps, idx = cand.get(a2, nocand)
                # dominance: an open candidate X -> A inside M with cl_H(X) = M is asked instead of M -> A; its no
                # refutes M -> A exactly as the no on M -> A would (M lies within cl_H(X)), and its yes is the FD
                # at one answer instead of two
                dom = [int(j) for j in np.flatnonzero(ins) if closure(int(L[j]), H) == M]
                if dom:
                    j = max(dom, key=lambda j: (float(R_[j]), -j))
                    st["max_q"] += 1
                    st["dominated"] += 1
                    if trace is not None:
                        last.update({"dom": 1, "rho": round(float(R_[j]), 4), "k": int(ins.sum())})
                    ans = ask(int(L[j]), a2, "max_asked")
                    observe(int(idx[j]), ans)
                    if ans:
                        found_lhs[int(L[j])] = found_lhs.get(int(L[j]), 0) + 1
                        st["found"] += 1
                    else:
                        st["max_no"] += 1
                    if not fresh[0]:
                        refresh()
                    continue
                ruled = False
                if discovery and adv is not None and st["disc_no"] < cap:
                    G, r = believed()
                    if G is None:
                        continue
                    if G:
                        st["rule_direct"] += 1
                        if st.get("switch_q") is not None:
                            st["direct_late"] += 1
                        disc_step(G[0], r)
                        continue
                    ruled = True
                elif discovery and adv is not None and not capped:
                    capped = True
                if "hone" in rules and discovery and adv is not None and a2 in cand and (M, a2) not in missed:
                    o2 = ins & (state[a2] == 0)
                    h_, p_ = first_stat[0] / first_stat[1], set_stat[0] / set_stat[1]
                    if o2.any() and p_ * (1 + h_) > 1:
                        top = np.flatnonzero(o2)[np.argsort(-R_[o2], kind="stable")][:HEAD]
                        if adv.query(idx[top].tolist()):
                            rq = adv.rho_prime(idx[top])
                            R_[top] = rq
                            rp[idx[top]] = rq
                        if guessable(M, a2, ins):
                            i_ = int(idx[np.flatnonzero(o2)[int(np.argmax(R_[o2]))]])
                            if disc_step(i_, {i_: p_ * h_}, True):
                                first_stat[0] += 1
                                first_stat[1] += 1
                                set_stat[0] += 1
                                set_stat[1] += 1
                                st["found"] += 1
                                continue
                            missed.add((M, a2))
                            best = (key, M, a2, ins & (state[a2] == 0))
                if ruled:
                    st["rule_max"] += 1
                if st.get("switch_q") is None:
                    st["switch_q"] = st["q"]
                    sound = not capped
                cert_step(best)
    except Budget:
        certified = False
    st.setdefault("switch_q", st["q"])
    st["llm_q"] = int(adv.queried.sum()) if adv is not None and adv.kind != "none" else 0
    # ---------------- output (v5.py) ----------------
    pred = {p for a, (_, _, ps, _) in cand.items() for i, p in enumerate(ps) if state[a][i] == 1}
    refuted = {p for a, (_, _, ps, _) in cand.items() for i, p in enumerate(ps) if state[a][i] == 2}
    opn = [p for a, (_, _, ps, _) in cand.items() for i, p in enumerate(ps) if state[a][i] == 0]
    inst = drd.Instance(b["R"], b["sigma0"], P, {p: 0.5 for p in P}, list(b["truth"]), name=b["name"])
    Hf = [AC.S.fd(tuple(i for i in range(n) if z >> i & 1), a.bit_length() - 1) for z, a in H[len(sig0):]]
    D = inst._synth(inst._atomic(b["sigma0"] + Hf))[0]
    extra = [f for f in Hf if f not in pix]

    def schema_certified(S):
        """the partial certificate: every maximal set of the projection of H onto S that holds on the data is refuted"""
        sm = mask(S)
        for a in bits(sm):
            ms = {M & sm for M in maxsets(H, a, full)}
            ms = [M for M in ms if not any(M != M2 and M & ~M2 == 0 for M2 in ms)]
            for M in ms:
                if known(M, a) is not False and holds(M, a):
                    return False
        return True
    cert_s = sum(1 for S in D if schema_certified(S))
    truth = lambda z, a: bool(closure(z, reach) & a)
    cexact = all(truth(z, a) for z, a in H[len(sig0):]) and not any(truth(M, a) for M, a in targets())
    pairs = [v for v in hist.values() if len(v) >= 2]
    out = {"certified": certified, "cert_exact": cexact, "wrong_cert": certified and not cexact, "questions": st["q"], "switch_q": st.get("switch_q", st["q"]), "sound": sound,
           "oracle": AC.oracle_mode(), "free": st["free"], "data_no": st["data_no"],
           "capped": capped, "disc_questions": st["disc_q"], "disc_no": st["disc_no"], "open_left": len(opn),
           "max_questions": st["max_q"], "max_no": st["max_no"], "guess_questions": st["guess_q"],
           "guess_hits": st["guess_hit"], "qx_questions": st["qx_q"], "found": st["found"],
           "confirmed": len(H) - len(sig0), "refuted_answers": len(NEG), "llm_queries": st["llm_q"],
           "attrs_median": statistics.median(st["attrs"]) if st["attrs"] else None,
           "attrs_max": max(st["attrs"]) if st["attrs"] else None,
           "schemata": len(D), "schemata_certified": cert_s, "theta_questions": st["theta_q"],
           "confirm_questions": st["confirm_q"], "reask_questions": st["reask_q"], "conflicts": len(conflict),
           "d_yes": st.get("d_yes"), "d_no": st.get("d_no"),
           "first_answers": len(hist), "first_wrong": sum(v[0] != truth(*k) for k, v in hist.items()),
           "designer_wrong": sum(x != truth(*k) for k, v in hist.items() for x in v),
           "pairs": len(pairs), "pairs_both_wrong": sum(v[0] != truth(*k) and v[1] != truth(*k) for k, v in hist.items() if len(v) >= 2),
           "false_in_H": sum(1 for z, a in H[len(sig0):] if not truth(z, a)),
           "true_sets_refuted": sum(1 for M, a in targets() if truth(M, a) and known(M, a) is False),
           "time_model": round(sum(1 + 0.25 * (x - 2) for x in st["attrs"]), 2), "attrs_sum": int(sum(st["attrs"]))}
    if mode == "v6":
        out.update({"rule_direct": st["rule_direct"], "rule_max": st["rule_max"], "direct_late": st["direct_late"],
                    "dominated": st["dominated"], "hone_questions": st["hone_q"], "hone_no": st["hone_no"],
                    "set_rate": set_stat, "first_rate": first_stat, "reuse_questions": st["reuse_q"], "reuse_hits": st["reuse_hit"]})
    names = b["names"]
    nm = lambda m: [names[i] for i in range(n) if m >> i & 1]
    out["certificate"] = {"yes": [[nm(z), nm(a)[0]] for z, a in H[len(sig0):]],
                          "no": [[nm(z), nm(a)[0]] for z, a in NEG]}
    out.update(C.evaluate(b, D, pred))
    if not certified and len(opn) <= 500:
        answers = {p: True for p in pred}
        answers.update({p: False for p in refuted})
        answers.update({f: True for f in extra})
        Dr = inst.robust(answers)
        ev = C.evaluate(b, Dr, pred)
        out.update({"fb_tables": len(Dr), "fb_lossless": ev["reach_lossless"], "fb_preserving": ev["reach_preserving"],
                    "fb_nf3": ev["reach_nf3"], "fb_good": ev["reach_good"], "fb_gold_good": ev["gold_good"]})
    if trace is not None:
        out["trace"] = trace
    return out


VARIANTS = {   # advisor, llm, cap, guess, mode, cheapest maximal set first
    "v6s": (True, False, CAP, True, "v6", True),
    "v6": (True, True, CAP, True, "v6", True),
    "v5": (True, True, CAP, True, "v5", False),      # v5.py reproduced (identity check)
    "v5s": (True, False, CAP, True, "v5", False),
    "v5n": (False, False, 0, False, "v5", False)}
VIOL = {}


def provenance(answers, model, budget):
    """what decides the rows of a run besides the variant and the relation; one output file holds one provenance"""
    return {"truth": AC.truth_mode(), "oracle": AC.oracle_mode(), "batch": os.environ.get("CONFIRM_BATCH", "1"), "pool": AC.pool_mode(),
            "budget": budget, "answers": answers, "model": model, "code": CODE}


def one(args):
    global BUDGET
    variant, ds, adir, model, BUDGET, *rest = args
    eps, careful, seed, theta = rest or (0.0, False, 0, 0.0)
    t0 = time.time()
    b = AC.load(ds)
    base, _, spec = variant.partition("|")
    rules = tuple(x for x in spec.split("+") if x)
    if set(rules) - TOKENS:
        raise ValueError(f"unknown rules {set(rules) - TOKENS}")
    advisor, llm, cap, guess, mode, mcheap = VARIANTS[base]
    if mode == "v5" and (eps > 0 or careful or theta > 0):
        raise ValueError("mode v5 reproduces v5.py for an exact designer; v5tol.py and v5tau.py hold the rest")
    adv, pk, am = (advisor_for(b, adir, model, llm, True) if advisor else (None, "none", "none"))
    h0 = None
    if "lc" in rules:
        h0 = class_rate(ds)
        adv.__class__ = LCAdvisor
        adv.attach(h0, [sum(1 << i_ for i_ in p_[0]) for p_ in b["P"]])
    viol = None
    if theta > 0:
        import v5tau
        if ds not in VIOL:                    # one instance per worker at a time, shared by its runs
            VIOL.clear()
            VIOL[ds] = v5tau.Violations(ds)
        viol = VIOL[ds]
    r = {"variant": variant, "dataset": ds, "candidates": len(b["P"]),
         "true": len(b["truth"]), "prior_kind": pk, "answer_model": am, "cap": cap, "h0": h0,
         "pool_size": len(AC.pool()), "target_in_pool": ds in AC.pool(), **provenance(adir, model, BUDGET),
         "am_relations": len(C.answer_model(adir, model)["selected_for"]) if llm else None,
         "designer_err": eps, "careful": careful, "seed": seed, "theta": theta,
         **run(b, adv, cap, advisor, guess, mode, mcheap, rules, eps, seed, careful, theta, viol)}
    if viol is not None:
        viol.save()
    r["secs"] = round(time.time() - t0, 1)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", required=True)
    ap.add_argument("--model", default="q35")
    ap.add_argument("--datasets", default=",".join(AC.DATASETS + AC.FRESH))
    ap.add_argument("--variants", default="v6s|lc+hone+kf")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--out", required=True)
    ap.add_argument("--budget", type=int, default=BUDGET)
    ap.add_argument("--eps", type=float, default=0.0)
    ap.add_argument("--careful", action="store_true")
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--theta", type=float, default=0.0)
    a = ap.parse_args()
    prov = provenance(a.answers, a.model, a.budget)
    done = set()
    if os.path.exists(a.out):
        for x in open(a.out, encoding="utf-8"):
            if x.strip():
                r = json.loads(x)
                wrong = {k: (r.get(k), v) for k, v in prov.items() if r.get(k) != v}
                if wrong:
                    raise SystemExit(f"{a.out} holds rows of another run: {wrong}")
                done.add((r["variant"], r["dataset"], r["designer_err"], r["careful"], r["seed"], r["theta"]))
    big = {"fresh_tpcds_customer", "tpch_lineitem_orders", "fresh_scorecard_fos", "ssb_lineorder"}
    dss = sorted(a.datasets.split(","), key=lambda d: (d not in big, d))
    seeds = range(a.seeds) if a.eps > 0 else [0]
    jobs = [(v, ds, a.answers, a.model, a.budget, a.eps, a.careful, s, a.theta) for ds in dss for s in seeds
            for v in a.variants.split(",") if (v, ds, a.eps, a.careful, s, a.theta) not in done]
    with open(a.out, "a", encoding="utf-8") as fo:
        if a.workers <= 1:
            it = map(one, jobs)
        else:
            ex = ProcessPoolExecutor(a.workers)
            it = (f.result() for f in as_completed([ex.submit(one, j) for j in jobs]))
        for r in it:
            fo.write(json.dumps(r) + "\n")
            fo.flush()
            print(f"{r['variant']:4s} {r['dataset']:28s} cert {r['certified']!s:5s} good {r['gold_good' if r['oracle'] == 'gold' else 'reach_good']!s:5s} "
                  f"q {r['questions']:3d} (disc {r['disc_questions']}/{r['disc_no']}no, switch {r['switch_q']} "
                  f"{'sound' if r['sound'] else 'cap' if r['capped'] else '-'}, max {r['max_questions']}, "
                  f"no {r['max_no']}, guess {r['guess_questions']}/{r['guess_hits']}, qx {r['qx_questions']}"
                  + (f", late {r['direct_late']}, dom {r['dominated']}, hone {r['hone_questions']}/{r['hone_no']}no" if 'direct_late' in r else "") + ") "
                  f"open {r['open_left']} schemata {r['schemata_certified']}/{r['schemata']} llm {r['llm_queries']} "
                  f"attrs {r['attrs_median']} f1 {r['f1']:.2f} {r['secs']}s", flush=True)


if __name__ == "__main__":
    main()
