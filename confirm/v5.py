"""
Cert3NF, fifth version (design notes, item 32; written before any result): bounded advisors, exact
certificate.  Exploratory on the 24 development relations.

Advisors give every candidate a probability rho': the statistics prior, recalibrated on the grid over (a, b) of drd,
times the LLM's answer as evidence with the error rates of the selected answer model (the hier grid, or a fixed
likelihood ratio).  The grid weights are updated by the designer's answers on candidates.  The LLM is queried lazily:
an answer enters only once its candidate is about to decide a question (the head of the target cover, the guess
after a yes, the ordering of QuickXplain); every candidate is queried at most once.

Discovery: the believed hypothesis h is the closure of the open candidates with rho' >= 1/2; the target cover is a
non-redundant subset of them, most likely first, without the FDs that H implies; the head of the cover is asked.
It ends when the cover is empty (the target design is sound) or after b = 10 no answers (the waste cap).
Certification: the maximal-set loop of item 29 (maxset_loop.run), with rho' in place of the static rho, asking every
maximal set of H that holds on the data (one that contains the left-hand side of a candidate, open or refuted) until
all are refuted; a question that the data refute is answered no without the designer (r satisfies Sigma*).
Output adds the partial certificate per schema (every maximal set of the projection of H onto the schema that holds
on the data is refuted) and, without a certificate, the fallback design D_rob(H, open candidates) with its evaluation.
The simulated designer answers from CONFIRM_ORACLE: "gold", the documented truth, or "reach", the first draft's
declared key plus true candidates (auto_common.oracle).

Variants: v5 (statistics + LLM, b = 10), v5s (statistics only), v5n (no advisor: no discovery, maximal sets in
attribute order, QuickXplain after every yes), v5u (statistics + LLM, no cap).

Usage (in confirm):
  CONFIRM_TRUTH=full python v5.py --answers llm_fresh_full_q35_ms --variants v5,v5s,v5n,v5u --out F [--workers 4]
"""
import argparse, json, math, os, statistics, sys, time
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import auto_common as AC
import auto_confirm as C
import auto_answer as AA
import drd
from price import closure, bits, maxsets

BUDGET, CAP, BELIEVE, GUESS, HEAD, CH = 100, 10, 0.5, 0.2, 5, 64


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
    """rho' per candidate; see the module docstring.  llm is None (statistics only), {"kind": "hier", "err": [(alpha,
    beta, weight)], "answers": {p: True/False/None}} or {"kind": "lr", "lr": {p: ratio}, "answers": ...}."""

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
            # the ratio a yes would bring: the typical ratio of the recorded yes answers
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
        """L1, L0 [E, k] of the LLM evidence that has entered for candidates idx; force "yes": as if every candidate
        had been queried and answered yes (the evidence a query could bring at most)"""
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
        """rho L1 and (1 - rho) L0, [E, G, k]"""
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
        """the LLM's answers on the candidates idx enter (lazy querying); returns how many were new"""
        new = np.array([i for i in idx if not self.queried[i] and i not in self.answered], dtype=np.int64)
        if len(new) == 0:
            return 0
        old = self._logm(new).sum(axis=2)
        self.queried[new] = True
        self.lw += self._logm(new).sum(axis=2) - old
        return len(new)

    def observe(self, i, y):
        """the designer answered candidate i with y"""
        if i in self.answered:
            return
        a, c = self._parts(np.array([i]))
        a, c = a[:, :, 0], c[:, :, 0]
        self.lw += np.log(a if y else c) - np.log(a + c)
        self.answered[i] = bool(y)
        self.observations += 1


def advisor_for(b, adir, model, llm, lazy):
    """the Advisor of a relation: the prior kind and answer model of the nested selection (llm) or the learned prior
    alone (statistics only)"""
    ds = b["name"]
    if not llm:
        pi = C.prior_for(b, "learned", adir, model)
        return Advisor(b["P"], pi, None, lazy), "learned", "none"
    AM = C.answer_model(adir, model)
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


def run(b, adv, cap, discovery, guess):
    """one run with an exact designer.  adv None: no advisor (rho' = 1/2, attribute order)."""
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
    minfd = {}                                     # rhs bit -> lhs masks of the minimal FDs that hold on the data
    for p in P + b["implied0"]:
        minfd.setdefault(mask(p[1]), []).append(mask(p[0]))
    minfd = {a: np.array(ls, dtype=np.int64) for a, ls in minfd.items()}
    cand = {a: (np.array([mask(p[0]) for p in ps], dtype=np.int64), np.full(len(ps), 0.5), ps,
                np.array([pix[p] for p in ps], dtype=np.int64)) for a, ps in by.items()}
    state = {a: np.zeros(len(ps), dtype=np.int8) for a, ps in by.items()}     # 0 open, 1 implied, 2 refuted
    H, NEG = list(sig0), []
    st = {"q": 0, "free": 0, "data_no": 0, "disc_q": 0, "disc_no": 0, "max_q": 0, "max_asked": 0, "max_no": 0,
          "guess_q": 0, "guess_hit": 0, "qx_q": 0, "found": 0, "llm_q": 0, "attrs": []}
    rp = np.full(len(P), 0.5)                      # rho' of every candidate (the cache)
    ry = np.full(len(P), 0.5)                      # rho' if the LLM answered yes: what a query could bring
    where = {int(i): (a, k) for a, (_, _, _, idx) in cand.items() for k, i in enumerate(idx)}
    poss = []                                      # candidates that a query could make believed, (i, a, k)
    fresh = [True]

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

    def known(z, a):
        if closure(z, H) & a:
            return True
        for z2, a2 in NEG:
            c = closure(z2, H)
            if z & ~c == 0 and closure(c | a, H) & a2:
                return False
        return None

    def holds(z, a):
        """Z -> A holds on the data iff Z contains the left-hand side of a minimal FD of the data (Thm. price (a))"""
        return a in minfd and bool(((minfd[a] & ~z) == 0).any())

    def ask(z, a, kind):
        k = known(z, a)
        if k is None and not holds(z, a):
            st["data_no"] += 1                    # the data refute Z -> A: no question (r satisfies Sigma*)
            k = False
        if k is not None:
            st["free"] += 1
            return k
        if st["q"] >= BUDGET:
            raise Budget
        st["q"] += 1
        st[kind] += 1
        m = bin(z).count("1")
        st["attrs"].append(min(m, n - m) + 1)
        ans = bool(closure(z, reach) & a)
        if ans:
            H.append((z, a))
        else:
            NEG.append((z, a))
        update()
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

    update()
    if adv is not None:
        refresh()
    sound = capped = False
    # ---------------- discovery ----------------
    try:
        if discovery and adv is not None:
            while True:
                if not fresh[0]:
                    refresh()
                opn = [i for i, a, k in poss if state[a][k] == 0 and i not in adv.answered]
                # lazy LLM: the candidates that a yes would make believed are queried first
                unq = [i for i in opn if not adv.queried[i]]
                if unq:
                    bel = [i for i, v in zip(unq, adv.rho_prime(unq, "yes")) if v >= BELIEVE]
                    if bel and adv.query(bel):
                        continue
                r = dict(zip(opn, adv.rho_prime(opn))) if opn else {}
                order = sorted((i for i in opn if r[i] >= BELIEVE), key=lambda i: -r[i])
                Ft, G = list(H), []
                for i in order:
                    l, a = mask(P[i][0]), mask(P[i][1])
                    if closure(l, Ft) & a:
                        continue
                    G.append(i)
                    Ft.append((l, a))
                if not G:
                    sound = True
                    break
                if st["disc_no"] >= cap:
                    capped = True
                    break
                i = G[0]
                l, a = mask(P[i][0]), mask(P[i][1])
                ans = ask(l, a, "disc_q")
                observe(i, ans)
                if not ans:
                    st["disc_no"] += 1
                if not fresh[0]:
                    refresh()
        st["switch_q"] = st["q"]
        # ---------------- certification ----------------
        if not fresh[0]:
            refresh()
        certified = False
        while True:
            # every maximal set of H that holds on the data has to be refuted (Thm. certificate with Thm. price (a)):
            # it holds on the data iff it contains the left-hand side of a candidate, open or refuted.  A set whose
            # candidates are all refuted may still hold through a true FD that is not minimal on the data, so it is
            # asked too, after the sets that hold an open candidate.
            best = None
            for a, (L, R_, _, _) in cand.items():
                s = state[a]
                unimplied = s != 1
                if not unimplied.any():
                    continue
                for M in maxsets(H, a, full):
                    inside = unimplied & ((L & ~M) == 0)
                    if not inside.any() or known(M, a) is False:
                        continue
                    ins = inside & (s == 0)
                    if adv is None:
                        key = (bool(ins.any()), -a, -M)
                    else:
                        py = 1 - float(np.exp(np.log1p(-np.minimum(R_[ins], 1 - 1e-12)).sum())) if ins.any() else 0.0
                        key = (py, -a, M)
                    if best is None or key > best[0]:
                        best = (key, M, a, ins)
            if best is None:
                certified = True
                break
            key, M, a, ins = best
            st["max_q"] += 1
            if not ask(M, a, "max_asked"):
                st["max_no"] += 1
                continue
            L, R_, ps, idx = cand[a]
            x = None
            if adv is not None:
                # lazy LLM: the likeliest open candidates inside M are queried before the guess
                top = np.flatnonzero(ins)[np.argsort(-R_[ins], kind="stable")][:HEAD]   # ties by candidate index, the same on every machine
                if adv.query(idx[top].tolist()):
                    rq = adv.rho_prime(idx[top])
                    R_[top] = rq
                    rp[idx[top]] = rq
                # guesses: a candidate inside M is asked while its probability given M -> A is at least 1 over the
                # expected cost of QuickXplain, log2|M| + 1 answers (a wrong guess costs one answer and still refutes
                # a candidate); the conditional probabilities are renormalized over the candidates still open
                qx_cost = math.ceil(math.log2(max(bin(M).count("1"), 2))) + 1
                guesses = 0
                while guess and guesses < qx_cost:        # at most the expected cost of QuickXplain (Thm. bounded damage)
                    o2 = ins & (state[a] == 0)
                    if not o2.any():
                        break
                    guesses += 1
                    py = 1 - float(np.exp(np.log1p(-np.minimum(R_[o2], 1 - 1e-12)).sum()))
                    cond = R_ * o2 / max(py, 1e-12)
                    i = int(np.argmax(cond))
                    if cond[i] < max(GUESS, 1.0 / qx_cost):
                        break
                    ans = ask(int(L[i]), a, "guess_q")
                    observe(int(idx[i]), ans)
                    if ans:
                        x = int(L[i])
                        st["guess_hit"] += 1
                        break
                py = 1 - float(np.exp(np.log1p(-np.minimum(R_[ins], 1 - 1e-12)).sum()))
                cond = R_ * ins / max(py, 1e-12)
                w = {bt: float(cond[(L & bt) != 0].sum()) for bt in bits(M)}
                order = sorted(w, key=lambda bt: (-w[bt], bt))
            else:
                order = list(bits(M))
            if x is None:
                x = qx(0, 0, order, a)
                if not closure(x, H) & a:
                    H.append((x, a))
                    update()
            st["found"] += 1
            if not fresh[0]:
                refresh()
    except Budget:
        certified = False
        st.setdefault("switch_q", st["q"])
    st["llm_q"] = int(adv.queried.sum()) if adv is not None else 0
    # ---------------- output ----------------
    pred = {p for a, (_, _, ps, _) in cand.items() for i, p in enumerate(ps) if state[a][i] == 1}
    refuted = {p for a, (_, _, ps, _) in cand.items() for i, p in enumerate(ps) if state[a][i] == 2}
    opn = [p for a, (_, _, ps, _) in cand.items() for i, p in enumerate(ps) if state[a][i] == 0]
    inst = drd.Instance(b["R"], b["sigma0"], P, {p: 0.5 for p in P}, list(b["truth"]), name=b["name"])
    # the design is the 3NF synthesis of H itself: a confirmed FD need not be minimal on the data (a true FD above a
    # refuted candidate), so the confirmed candidates alone can miss it
    Hf = [AC.S.fd(tuple(i for i in range(n) if z >> i & 1), a.bit_length() - 1) for z, a in H[len(sig0):]]
    D = inst._synth(inst._atomic(b["sigma0"] + Hf))[0]
    extra = [f for f in Hf if f not in pix]           # confirmed FDs outside the candidates

    def schema_certified(S):
        """the partial certificate (T-b): every maximal set of the projection of H onto S that holds on the data,
        i.e. the maximal M ∩ S over M in max(H, A) that contain the left-hand side of a candidate X -> A with XA in S,
        is refuted by the answers"""
        sm = mask(S)
        for a in bits(sm):
            if a not in cand:
                continue
            L, s = cand[a][0], state[a]
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
    out = {"certified": certified, "questions": st["q"], "switch_q": st.get("switch_q", st["q"]), "sound": sound,
           "oracle": AC.oracle_mode(), "free": st["free"], "data_no": st["data_no"],
           "capped": capped, "disc_questions": st["disc_q"], "disc_no": st["disc_no"], "open_left": len(opn),
           "max_questions": st["max_q"], "max_no": st["max_no"], "guess_questions": st["guess_q"],
           "guess_hits": st["guess_hit"], "qx_questions": st["qx_q"], "found": st["found"], "free": st["free"],
           "confirmed": len(H) - len(sig0), "refuted_answers": len(NEG), "llm_queries": st["llm_q"],
           "attrs_median": statistics.median(st["attrs"]) if st["attrs"] else None,
           "attrs_max": max(st["attrs"]) if st["attrs"] else None,
           "schemata": len(D), "schemata_certified": cert_s}
    # the certificate itself: the confirmed FDs and the refuted sets, by attribute name (checked by check_cert.py)
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
    return out


VARIANTS = {"v5": (True, True, CAP, True), "v5s": (True, False, CAP, True), "v5n": (False, False, 0, False),
            "v5u": (True, True, 10 ** 9, True)}       # advisor, llm, cap, guess


def one(args):
    global BUDGET
    variant, ds, adir, model, BUDGET = args          # the budget of this run (design note item 39 runs without one)
    t0 = time.time()
    b = AC.load(ds)
    advisor, llm, cap, guess = VARIANTS[variant]
    adv, pk, am = (advisor_for(b, adir, model, llm, True) if advisor else (None, "none", "none"))
    r = {"variant": variant, "dataset": ds, "truth": AC.truth_mode(), "candidates": len(b["P"]),
         "true": len(b["truth"]), "prior_kind": pk, "answer_model": am, "cap": cap, "budget": BUDGET,
         **run(b, adv, cap, advisor, guess)}
    r["secs"] = round(time.time() - t0, 1)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", required=True)
    ap.add_argument("--model", default="q35")
    ap.add_argument("--datasets", default=",".join(AC.DATASETS + AC.FRESH))
    ap.add_argument("--variants", default="v5,v5s,v5n,v5u")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--out", required=True)
    ap.add_argument("--budget", type=int, default=BUDGET,
                    help="answers per run; the default is the budget B of the paper, item 39 runs with 1000")
    a = ap.parse_args()
    done = set()
    if os.path.exists(a.out):
        for x in open(a.out, encoding="utf-8"):
            if x.strip():
                r = json.loads(x)
                done.add((r["variant"], r["dataset"]))
    big = {"fresh_tpcds_customer", "tpch_lineitem_orders", "fresh_scorecard_fos", "ssb_lineorder"}
    dss = sorted(a.datasets.split(","), key=lambda d: (d not in big, d))
    jobs = [(v, ds, a.answers, a.model, a.budget) for ds in dss for v in a.variants.split(",") if (v, ds) not in done]
    with open(a.out, "a", encoding="utf-8") as fo:
        it = (map(one, jobs) if a.workers <= 1 else ProcessPoolExecutor(a.workers).map(one, jobs))
        for r in it:
            fo.write(json.dumps(r) + "\n")
            fo.flush()
            print(f"{r['variant']:4s} {r['dataset']:28s} cert {r['certified']!s:5s} good {r['gold_good' if r['oracle'] == 'gold' else 'reach_good']!s:5s} "
                  f"q {r['questions']:3d} (disc {r['disc_questions']}/{r['disc_no']}no, switch {r['switch_q']} "
                  f"{'sound' if r['sound'] else 'cap' if r['capped'] else '-'}, max {r['max_questions']}, "
                  f"no {r['max_no']}, guess {r['guess_questions']}/{r['guess_hits']}, qx {r['qx_questions']}) "
                  f"open {r['open_left']} schemata {r['schemata_certified']}/{r['schemata']} llm {r['llm_queries']} "
                  f"attrs {r['attrs_median']} f1 {r['f1']:.2f} {r['secs']}s", flush=True)


if __name__ == "__main__":
    main()
