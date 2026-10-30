"""
Cert3NF on data that may violate the true FDs (design notes, item 43; written before any result with
theta > 0).

v5.run (frozen, imported unchanged) with the free refutation by the data relaxed: the data refute Z -> A without a
question only if more than a share theta of the records would have to be removed for Z -> A to hold, g3(Z -> A) >
theta, keeping in every Z-group the records of its most frequent A-value; otherwise the designer is asked.  Hence the
certification phase asks every maximal set M in max(H, A) on which M -> A theta-holds, for every attribute A, also
one that is no candidate's right-hand side, and the partial certificate of a schema does the same.  Candidates,
advisors, discovery, guesses and QuickXplain are those of v5.run; for an attribute without candidates nothing is
guessed and QuickXplain runs at once.  If r theta-satisfies Sigma* (every true FD theta-holds), a true M -> A is never
refuted by the data, since g3 can only fall when the left-hand side grows, so the certificate stays exact.  theta = 0
is v5.run question for question (the sets that hold on the data are those that contain a candidate's left-hand side).

g3 is computed from the integer codes of the instance (e3/dump_codes.py, CODES_DIR/<ds>.npy) with a 64-bit hash of
every column (splitmix64), summed over the left-hand side, and cached per (Z, A) in CODES_DIR/<ds>.g3.json, which the
runs of a relation share (g3 depends on the instance only).

Usage (in confirm):
  CODES_DIR=D CONFIRM_ORACLE=gold CONFIRM_BATCH=2 CONFIRM_TRUTH=full python v5tau.py --answers llm_fresh2_full_q35 \
      --datasets ... --variants v5,v5s --thetas 0.001,0.01,0.1 --out F [--budget 1000] [--workers 12]
"""
import argparse, json, math, os, statistics, time
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import auto_common as AC
import auto_confirm as C
import drd
import v5
from v5 import Budget, closure_many, advisor_for, BELIEVE, GUESS, HEAD
from price import closure, bits, maxsets

BUDGET = v5.BUDGET


def splitmix64(x):
    """splitmix64 of a uint64 array, modulo 2^64"""
    with np.errstate(over="ignore"):
        z = x + np.uint64(0x9E3779B97F4A7C15)
        z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        return z ^ (z >> np.uint64(31))


class Violations:
    """g3(Z -> A) on an instance given as integer codes (records x attributes of data/<ds>.json)"""

    def __init__(self, ds):
        X = np.load(os.path.join(os.environ["CODES_DIR"], ds + ".npy"))
        self.n = X.shape[0]
        self.h = [splitmix64(X[:, j].astype(np.int64).astype(np.uint64) + np.uint64(j << 40)) for j in range(X.shape[1])]
        self.path = os.path.join(os.environ["CODES_DIR"], ds + ".g3.json")
        self.cache = {}
        self.load()
        self.new = 0

    def load(self):
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as fh:
                self.cache.update({tuple(map(int, k.split(":"))): v for k, v in json.load(fh).items()})

    def save(self):
        """merge into the shared cache file (other processes may have written it meanwhile)"""
        if not self.new:
            return
        self.load()
        tmp = f"{self.path}.{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({f"{z}:{a}": v for (z, a), v in self.cache.items()}, fh)
        os.replace(tmp, self.path)
        self.new = 0

    def g3(self, z, a):
        """the share of records to remove so that Z -> A holds (z a bit mask, a one bit)"""
        if (z, a) in self.cache:
            return self.cache[z, a]
        key = np.zeros(self.n, dtype=np.uint64)
        with np.errstate(over="ignore"):
            for j in range(z.bit_length()):
                if z >> j & 1:
                    key += self.h[j]
            pair = splitmix64(key) + self.h[a.bit_length() - 1]
        _, gz = np.unique(key, return_inverse=True)
        _, gp, cp = np.unique(pair, return_inverse=True, return_counts=True)
        grp = np.empty(len(cp), dtype=np.int64)
        grp[gp.ravel()] = gz.ravel()                  # the Z-group of every (Z, A)-group
        best = np.zeros(int(gz.max()) + 1, dtype=np.int64)
        np.maximum.at(best, grp, cp)                  # each Z-group keeps its most frequent A-value
        v = (self.n - int(best.sum())) / self.n
        self.cache[z, a] = v
        self.new += 1
        return v


def run(b, adv, cap, discovery, guess, theta, viol):
    """one run with an exact designer; the data refute Z -> A only if g3(Z -> A) > theta (viol: the Violations of r).
    adv None: no advisor (rho' = 1/2, attribute order)."""
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
          "guess_q": 0, "guess_hit": 0, "qx_q": 0, "found": 0, "llm_q": 0, "attrs": [], "theta_q": 0}
    rp = np.full(len(P), 0.5)                      # rho' of every candidate (the cache)
    ry = np.full(len(P), 0.5)                      # rho' if the LLM answered yes: what a query could bring
    where = {int(i): (a, k) for a, (_, _, _, idx) in cand.items() for k, i in enumerate(idx)}
    poss = []                                      # candidates that a query could make believed, (i, a, k)
    attrs = [1 << i for i in range(n)]
    nocand = (np.zeros(0, dtype=np.int64), np.zeros(0), [], np.zeros(0, dtype=np.int64))
    nostate = np.zeros(0, dtype=np.int8)
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

    def exact(z, a):
        """Z -> A holds on the data iff Z contains the left-hand side of a minimal FD of the data (Thm. price (a))"""
        return a in minfd and bool(((minfd[a] & ~z) == 0).any())

    def holds(z, a):
        """Z -> A theta-holds on the data: removing a share theta of the records makes it hold"""
        return exact(z, a) or viol.g3(z, a) <= theta

    def ask(z, a, kind):
        k = known(z, a)
        if k is None and not holds(z, a):
            st["data_no"] += 1                    # the data refute Z -> A: no question (r theta-satisfies Sigma*)
            k = False
        if k is not None:
            st["free"] += 1
            return k
        if st["q"] >= BUDGET:
            raise Budget
        st["q"] += 1
        st[kind] += 1
        if not exact(z, a):
            st["theta_q"] += 1                    # a question that the tolerance leaves to the designer
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
            # every maximal set of H that theta-holds on the data has to be refuted (Thm. certificate with Thm. price
            # (a) for r theta-satisfying Sigma*), for every attribute, a right-hand side of a candidate or not.  For
            # theta = 0 these are the sets that contain the left-hand side of a candidate, open or refuted, as in
            # v5.run: a maximal set contains no candidate that H implies.  The sets that hold an open candidate first.
            best = None
            for a in attrs:
                L, R_, _, _ = cand.get(a, nocand)
                s = state.get(a, nostate)
                for M in maxsets(H, a, full):
                    if known(M, a) is False or not holds(M, a):
                        continue
                    ins = (s == 0) & ((L & ~M) == 0)
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
            L, R_, ps, idx = cand.get(a, nocand)
            x = None
            if adv is not None and len(L):                # no candidate of A: nothing to guess, QuickXplain at once
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
        """the partial certificate (T-b): every maximal set of the projection of H onto S that theta-holds on the
        data, i.e. the maximal M ∩ S over M in max(H, A) for A in S on which M ∩ S -> A theta-holds, is refuted by the
        answers (for theta = 0, those that contain the left-hand side of a candidate X -> A with XA in S)"""
        sm = mask(S)
        for a in bits(sm):
            ms = {M & sm for M in maxsets(H, a, full)}
            ms = [M for M in ms if not any(M != M2 and M & ~M2 == 0 for M2 in ms)]
            for M in ms:
                if known(M, a) is not False and holds(M, a):
                    return False
        return True
    cert_s = sum(1 for S in D if schema_certified(S))
    out = {"certified": certified, "questions": st["q"], "switch_q": st.get("switch_q", st["q"]), "sound": sound,
           "oracle": AC.oracle_mode(), "free": st["free"], "data_no": st["data_no"], "theta_questions": st["theta_q"],
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


VIOL = {}


def one(args):
    global BUDGET
    variant, ds, adir, model, BUDGET, theta = args
    t0 = time.time()
    b = AC.load(ds)
    if ds not in VIOL:                                # one instance per worker at a time, shared by its runs
        VIOL.clear()
        VIOL[ds] = Violations(ds)
    viol = VIOL[ds]
    advisor, llm, cap, guess = v5.VARIANTS[variant]
    adv, pk, am = (advisor_for(b, adir, model, llm, True) if advisor else (None, "none", "none"))
    r = {"variant": variant, "dataset": ds, "truth": AC.truth_mode(), "theta": theta, "candidates": len(b["P"]),
         "true": len(b["truth"]), "prior_kind": pk, "answer_model": am, "cap": cap, "budget": BUDGET,
         **run(b, adv, cap, advisor, guess, theta, viol)}
    viol.save()
    r["secs"] = round(time.time() - t0, 1)
    return r


def group(jobs):
    """the runs of one relation, in one worker, so that they share the instance and its g3 values"""
    return [one(j) for j in jobs]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", required=True)
    ap.add_argument("--model", default="q35")
    ap.add_argument("--datasets", required=True)
    ap.add_argument("--variants", default="v5,v5s")
    ap.add_argument("--thetas", default="0.001,0.01,0.1")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--out", required=True)
    ap.add_argument("--budget", type=int, default=BUDGET)
    a = ap.parse_args()
    done = set()
    if os.path.exists(a.out):
        for x in open(a.out, encoding="utf-8"):
            if x.strip():
                r = json.loads(x)
                done.add((r["variant"], r["dataset"], r["theta"]))
    thetas = [float(t) for t in a.thetas.split(",")]
    groups = [[(v, ds, a.answers, a.model, a.budget, t) for t in thetas for v in a.variants.split(",")
               if (v, ds, t) not in done] for ds in a.datasets.split(",")]
    groups = [g for g in groups if g]
    with open(a.out, "a", encoding="utf-8") as fo:
        it = map(group, groups) if a.workers <= 1 else ProcessPoolExecutor(a.workers).map(group, groups)
        for rs in it:
            for r in rs:
                fo.write(json.dumps(r) + "\n")
                fo.flush()
                print(f"{r['variant']:4s} theta {r['theta']:<6} {r['dataset']:22s} cert {r['certified']!s:5s} "
                      f"good {r['gold_good']!s:5s} q {r['questions']:4d} (theta {r['theta_questions']}, data_no "
                      f"{r['data_no']}) schemata {r['schemata_certified']}/{r['schemata']} {r['secs']}s", flush=True)


if __name__ == "__main__":
    main()
