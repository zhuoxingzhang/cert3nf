"""
Design note item 82 (b): the EC^2 order with the Find step of Cert3NF.

The EC^2 order of the paper (ec2full.py, variant ec2full0) differs from Cert3NF in two things at once: the next question
is the one with the largest EC^2 score, and the FD behind a yes to a maximal set is found by QuickXplain alone.  The
variant ec2find0 of this file keeps the first and drops the second, so that the two can be told apart:
  the next question: ec2full.py's, unchanged (pool, posterior samples, classes, score, ties, stopping rule);
  a yes to a maximal set (M, A): the Find step of v6f.py's cert_step, verbatim but for the bookkeeping of the rule hone,
    which belongs to the order of Cert3NF: the left-hand sides inside M that the designer confirmed for other attributes
    (rule rl), then the likeliest open candidates inside M while they are likely given M -> A, then QuickXplain over the
    attributes of M ordered by these probabilities.  The probabilities are those of Cert3NF's advisor without an LLM
    (v6f.advisor_for and v6f.LCAdvisor, the form v6s|lc+hone+kf+rl), which sees every answer of the run as it does in
    v6f.py: a candidate asked directly through observe, a settled candidate through evidence, a left-hand side found by
    QuickXplain through evidence_lhs.  A maximal set that is itself a candidate is that FD when it is answered yes, as
    under the dominance rule of v6f.py.  The probabilities are recomputed before the step and after each of its answers.
The answers of the Find step reach the EC^2 posterior as every other answer does (ec2full.py's ask).
ec2full.py and v6f.py are imported and not changed.  The variant ec2full0 of this file runs ec2full.py's own step, so a
control run through this file can be compared with the rows of the paper field by field.

Usage (in confirm/):
  CONFIRM_TRUTH=full CONFIRM_ORACLE=gold CONFIRM_BATCH=3 python ec2find.py --answers llm_fresh3_full_q35 \
      --variants ec2find0 --budget 1000 --seeds 3 --workers 6 --out item82/ec2find_full.jsonl
"""
import argparse, hashlib, json, math, os, random, statistics, time
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
import auto_common as AC
import auto_confirm as C
import drd
import ec2full as E
import v6f
from price import closure, bits, maxsets

K, FEW, STARVE, DEBUG = E.K, E.FEW, E.STARVE, E.DEBUG
VARIANTS = {"ec2full0": (False, False), "ec2find0": (True, False)}      # the Find step of Cert3NF, llm


def md5_12(path):
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()[:12]


CODE, CODE_E = md5_12(os.path.abspath(__file__)), md5_12(os.path.abspath(E.__file__))
closure_many, reduce_fds = E.closure_many, E.reduce_fds


def run(b, inst, nz, budget, seed, adv=None):
    """ec2full.run with qx_mode True; adv None: verbatim; else the Find step of v6f.py with the advisor adv"""
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
          "debug": [], "guess_q": 0, "guess_hit": 0, "reuse_q": 0, "reuse_hit": 0}
    parts = []                                     # particles: dicts h, hF (reduced FDs), vec (over P), label
    hver = [0]                                     # grows with H: caches keyed on it
    negc = {"ver": -1, "list": []}                 # per no answer (Z, A2): closure(Z, H) and the attributes whose
    trace, at100 = [], [None]                      # addition to it implies A2 under H (as a bitmask)
    starve = [-1]                                  # question index until which a refresh is not tried again
    single = np.array([1 << i for i in range(n)], dtype=np.int64)
    smp = E.Sampler(nz)
    fdobj = lambda z, a: AC.S.fd(tuple(i for i in range(n) if z >> i & 1), a.bit_length() - 1)
    split = {"ver": None, "Hx": []}                # the closed-world yes answers Yc and the facts Hx, per version
    # ---- the advisor of Cert3NF, for the Find step only (item 82) ----
    if adv is not None:
        aix = np.array([adv.ix[p] for p in P], dtype=np.int64)     # this file's index of a candidate -> the advisor's
        aall = np.arange(len(adv.P))
        seen = np.zeros(N, dtype=bool)             # settled candidates that the latent classes have seen
        found_lhs, reuse_stat = {}, [1, 2]         # v6f.py: confirmed left-hand side -> FDs found with it; Beta(1, 1) of rl

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
        if o.any():
            imp = (closure_many(Lm, H) & Am) != 0
            state[o & imp] = 1
            for c, hit in negs():
                for a in bits(hit):
                    idx = by_a.get(a)
                    if idx is None:
                        continue
                    state[idx[(state[idx] == 0) & ((Lm[idx] & ~c) == 0)]] = 2     # state[idx] is a copy: assign through idx
        if adv is not None:                        # v6f.update, rule lc: the classes see the candidates settled since
            for a, idx in by_a.items():
                new = idx[(state[idx] != 0) & ~seen[idx]]
                if len(new):
                    seen[new] = True
                    adv.evidence(aix[new], state[new] == 1)

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
        for pt, lb in zip(parts, E.class_labels(inst, ds, hs, G).tolist()):
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
            raise E.Budget
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
        if adv is not None and i is not None:
            adv.note(z, ans)                      # v6f.put: the answer to a question that is a candidate
        update()
        if adv is not None and i is not None and kind != "qx_q":
            adv.observe(int(aix[i]), ans)         # v6f.py: a candidate asked directly (disc_step, dominance, guesses)
            if ans:
                found_lhs[z] = found_lhs.get(z, 0) + 1
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

    def find(M, a):
        """v6f.py's cert_step after the yes to M -> A (lines of the rules rl and guess, then QuickXplain), without the
        counts of the rule hone; returns nothing, the FD is in H"""
        idx = by_a[a]
        L = Lm[idx]
        R_ = adv.rho_prime(aall)[aix[idx]]
        ins = (state[idx] == 0) & ((L & ~M) == 0)
        qx_cost = math.ceil(math.log2(max(bin(M).count("1"), 2))) + 1
        x, guesses, narrow = None, 0, None
        for x0 in sorted((l_ for l_ in found_lhs if l_ and l_ & ~M == 0 and l_ != M), key=lambda l_: (-found_lhs[l_], bin(l_).count("1"), l_)):
            if guesses >= qx_cost or reuse_stat[0] / reuse_stat[1] < max(v6f.GUESS, 1.0 / qx_cost):
                break
            if (L == x0).any() or known(x0, a) is not None or not holds(x0, a):
                continue
            guesses += 1
            ans = ask(x0, a, "reuse_q")
            reuse_stat[1] += 1
            reuse_stat[0] += bool(ans)
            R_ = adv.rho_prime(aall)[aix[idx]]
            if ans:
                st["reuse_hit"] += 1
                narrow = x0
                ins = ins & ((L & ~x0) == 0)
                qx_cost = math.ceil(math.log2(max(bin(x0).count("1"), 2))) + 1
                break
        while guesses < qx_cost:
            o2 = ins & (state[idx] == 0)
            if not o2.any():
                break
            guesses += 1
            py = 1 - float(np.exp(np.log1p(-np.minimum(R_[o2], 1 - 1e-12)).sum()))
            cond = R_ * o2 / max(py, 1e-12)
            i = int(np.argmax(cond))
            if cond[i] < max(v6f.GUESS, 1.0 / qx_cost):
                break
            ans = ask(int(L[i]), a, "guess_q")
            R_ = adv.rho_prime(aall)[aix[idx]]
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
        if x is None:
            x = qx(0, 0, order, a) if order else 0      # M is empty: A is constant
            if not (L == x).any():
                adv.evidence_lhs(x)
            if not closure(x, H) & a:
                H.append((x, a))
                hver[0] += 1
                update()
                parts[:] = [pt for pt in parts if implies(pt, x, a)]
            if closure(x, H) & a:
                found_lhs[x] = found_lhs.get(x, 0) + 1

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
                score, marg = E.ec2_scores(X, labels)
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
            if adv is not None:
                if (M, a) not in cmap:            # a maximal set that is a candidate is the FD itself (v6f.py: dominance)
                    find(M, a)
                st["found"] += 1
                continue
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
    except E.Budget:
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
    if adv is not None:
        reach_ok = lambda z, a: bool(closure(z, reach) & a)
        out.update({"guess_questions": st["guess_q"], "guess_hits": st["guess_hit"], "reuse_questions": st["reuse_q"],
                    "reuse_hits": st["reuse_hit"], "advisor_observations": adv.observations,
                    "cert_exact": all(reach_ok(z, a) for z, a in H[len(sig0):]) and not any(reach_ok(z, a) for z, a in NEG)})
    return out


def one(args):
    variant, ds, adir, model, budget, seed = args
    t0 = time.time()
    b = AC.load(ds)
    find, llm = VARIANTS[variant]
    inst, nz, pk, am = E.posterior(b, adir, model, llm)
    adv = None
    if find:                                       # the advisor of v6s|lc+hone+kf+rl, as v6f.one builds it
        adv = v6f.advisor_for(b, adir, model, False, True)[0]
        adv.__class__ = v6f.LCAdvisor
        adv.attach(v6f.class_rate(ds), [sum(1 << i_ for i_ in p_[0]) for p_ in b["P"]])
    r = {"variant": variant, "dataset": ds, "truth": AC.truth_mode(), "seed": seed, "budget": budget,
         "candidates": len(b["P"]), "true": len(b["truth"]), "prior_kind": pk, "answer_model": am, "K": K,
         **run(b, inst, nz, budget, seed, adv), "find": find, "code_find": CODE, "code_ec2full": CODE_E, "code_v6f": v6f.CODE}
    r["secs"] = round(time.time() - t0, 1)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", required=True)
    ap.add_argument("--model", default="q35")
    ap.add_argument("--datasets", default=",".join(AC.FRESH))
    ap.add_argument("--variants", default="ec2find0")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--budget", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    done = set()
    if os.path.exists(a.out):
        for x in open(a.out, encoding="utf-8"):
            if x.strip():
                r = json.loads(x)
                if r.get("code_find") != CODE:
                    raise SystemExit(f"{a.out} holds rows of another version of this file: {r.get('code_find')}")
                done.add((r["variant"], r["dataset"], r["seed"], r["budget"]))
    dss = a.datasets.split(",")
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
            print(f"{r['variant']:8s} {r['dataset']:34s} s{r['seed']} b{r['budget']:4d} cert {r['certified']!s:5s} "
                  f"good {r['gold_good']!s:5s} q {r['questions']:4d} (cand {r['cand_questions']}/{r['cand_no']}no, "
                  f"max {r['max_questions']}/{r['max_no']}no, qx {r['qx_questions']}, guess {r.get('guess_questions', '-')}/{r.get('guess_hits', '-')}, "
                  f"reuse {r.get('reuse_questions', '-')}/{r.get('reuse_hits', '-')}, found {r['found']}) open {r['open_left']} {r['secs']}s", flush=True)


if __name__ == "__main__":
    main()
