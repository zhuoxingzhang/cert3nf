"""
Generate study/code/v6fstudy.py, the method of the live sessions, from confirm/v6f.py by exact replacements (each
pattern must occur once), so that the difference to the frozen method is these lines only:

  hook      designer(z, a, k, kind) calls the module-level ASK(z, a, k, kind) when it is set: a person answers True,
            False or None (don't know), or raises Budget to stop.  With ASK None the designer is v6f's.
  stop      a Budget raised by the person does not count the unanswered question; the run ends as at the budget.
  dk        don't know counts as a question and enters no history: a candidate is skipped, a left-hand side is not tried
            for that attribute again, a maximal set (asked, or in QuickXplain, or the confirmation of the FD it found)
            stays undecided and is not asked again, a question to ask again is not asked again.  An undecided maximal set
            that is still one of H that holds on the data leaves no certificate (a partial one), and so does a premise
            that stays answered once in the careful mode.
  fallback  the robust design of an uncertified run is not computed for a person; nothing in a session reads it.

With no don't know and no stop, v6fstudy.run is v6f.run question for question (check_v6fstudy.py).
Usage:  python study/code/make_v6fstudy.py
"""
import hashlib, os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(os.path.dirname(HERE)), "confirm", "v6f.py")
OUT = os.path.join(HERE, "v6fstudy.py")

REPL = [
    # module: the hook and the exception
    ('class Budget(Exception):\n    pass\n',
     'class Budget(Exception):\n    pass\n\n\n'
     'class DontKnow(Exception):\n    pass\n\n\n'
     'ASK = None             # study: the person who answers, ASK(z, a, k, kind) -> True / False / None (don\'t know)\n'),
    # state
    ('    H, NEG, conflict, hist = list(sig0), [], [], {}      # hist: question (Z, A) -> the designer\'s answers\n',
     '    H, NEG, conflict, hist = list(sig0), [], [], {}      # hist: question (Z, A) -> the designer\'s answers\n'
     '    DK, UND, SKIP = set(), set(), set()            # study: questions answered don\'t know, maximal sets left\n'
     '                                                   # undecided, candidates skipped\n'),
    ('"reask_q": 0, "theta_q": 0}\n', '"reask_q": 0, "theta_q": 0, "dk": 0}\n'),
    # the designer
    ('    def designer(z, a, k):\n'
     '        """the k-th answer to Z -> A: the truth, flipped with probability eps"""\n'
     '        truth = bool(closure(z, reach) & a)\n',
     '    def designer(z, a, k, kind=None):\n'
     '        """the k-th answer to Z -> A: the truth, flipped with probability eps"""\n'
     '        if ASK is not None:                        # study: a person answers\n'
     '            return ASK(z, a, k, kind)\n'
     '        truth = bool(closure(z, reach) & a)\n'),
    ('        v = hist.setdefault((z, a), [])\n        v.append(designer(z, a, len(v)))\n',
     '        v = hist.setdefault((z, a), [])\n'
     '        try:\n'
     '            x = designer(z, a, len(v), kind)\n'
     '        except Budget:                             # study: the person stopped, the open question is not counted\n'
     '            st["q"] -= 1\n'
     '            st[kind] -= 1\n'
     '            st["attrs"].pop()\n'
     '            if not exact(z, a):\n'
     '                st["theta_q"] -= 1\n'
     '            if not v:\n'
     '                del hist[(z, a)]\n'
     '            raise\n'
     '        if x is None:                              # study: don\'t know counts as a question, enters no history\n'
     '            st["dk"] += 1\n'
     '            DK.add((z, a))\n'
     '            if not v:\n'
     '                del hist[(z, a)]\n'
     '            raise DontKnow\n'
     '        v.append(x)\n'),
    # re-asks
    ('                if len(hist[q]) < REASK:\n                    return q\n',
     '                if len(hist[q]) < REASK and q not in DK:\n                    return q\n'),
    ('            if net(v) is None and len(v) < REASK:\n',
     '            if net(v) is None and len(v) < REASK and k not in DK:\n'),
    ('                    if k is not None:\n                        put(*k, "reask_q")\n                        continue\n',
     '                    if k is not None:\n'
     '                        try:\n'
     '                            put(*k, "reask_q")\n'
     '                        except DontKnow:\n'
     '                            pass\n'
     '                        continue\n'),
    ('                    put(*next(k for k in dep if len(hist[k]) < 2), "reask_q")\n                    continue\n',
     '                    again = [k for k in dep if len(hist[k]) < 2 and k not in DK]\n'
     '                    if not again:                  # study: a premise stays answered once, a partial certificate\n'
     '                        break\n'
     '                    try:\n'
     '                        put(*again[0], "reask_q")\n'
     '                    except DontKnow:\n'
     '                        pass\n'
     '                    continue\n'),
    # the choice of a question
    ('        opn = [i for i, a, k in poss if state[a][k] == 0 and i not in adv.answered]\n',
     '        opn = [i for i, a, k in poss if state[a][k] == 0 and i not in adv.answered and i not in SKIP]\n'),
    ('                if known(M, a) is False or not holds(M, a):\n                    continue\n',
     '                if known(M, a) is False or (M, a) in UND or not holds(M, a):\n                    continue\n'),
    ('        o2 = ins & (state[a] == 0)\n        if not o2.any():\n            return False\n',
     '        o2 = ins & (state[a] == 0) & ~np.isin(cand[a][3], list(SKIP))\n        if not o2.any():\n            return False\n'),
    ('                    o2 = ins & (state[a2] == 0)\n                    h_, p_ = first_stat[0] / first_stat[1], set_stat[0] / set_stat[1]\n',
     '                    o2 = ins & (state[a2] == 0) & ~np.isin(idx, list(SKIP))\n                    h_, p_ = first_stat[0] / first_stat[1], set_stat[0] / set_stat[1]\n'),
    ('                dom = [int(j) for j in np.flatnonzero(ins) if closure(int(L[j]), H) == M]\n',
     '                dom = [int(j) for j in np.flatnonzero(ins) if closure(int(L[j]), H) == M and int(idx[j]) not in SKIP]\n'),
    # a candidate asked directly, as the first guess, or instead of its maximal set
    ('        ans = ask(l, a, "hone_q" if hone else "disc_q")\n        observe(i, ans)\n',
     '        try:\n'
     '            ans = ask(l, a, "hone_q" if hone else "disc_q")\n'
     '        except DontKnow:                           # study: the candidate is skipped\n'
     '            SKIP.add(i)\n'
     '            return False\n'
     '        observe(i, ans)\n'),
    ('                    ans = ask(int(L[j]), a2, "max_asked")\n                    observe(int(idx[j]), ans)\n',
     '                    try:\n'
     '                        ans = ask(int(L[j]), a2, "max_asked")\n'
     '                    except DontKnow:               # study: the candidate is skipped, M -> A comes next\n'
     '                        SKIP.add(int(idx[j]))\n'
     '                        continue\n'
     '                    observe(int(idx[j]), ans)\n'),
    # a maximal set, the reuse of a left-hand side, guesses, QuickXplain
    ('        if not ask(M, a, "max_asked"):\n            st["max_no"] += 1\n            return\n',
     '        try:\n'
     '            ansm = ask(M, a, "max_asked")\n'
     '        except DontKnow:                           # study: the maximal set stays undecided\n'
     '            UND.add((M, a))\n'
     '            set_stat[1] -= 1\n'
     '            return\n'
     '        if not ansm:\n'
     '            st["max_no"] += 1\n'
     '            return\n'),
    ('                    if (L == x0).any() or known(x0, a) is not None or not holds(x0, a):\n'
     '                        continue\n'
     '                    guesses += 1\n'
     '                    ans = ask(x0, a, "reuse_q")\n',
     '                    if (L == x0).any() or (x0, a) in DK or known(x0, a) is not None or not holds(x0, a):\n'
     '                        continue\n'
     '                    guesses += 1\n'
     '                    try:\n'
     '                        ans = ask(x0, a, "reuse_q")\n'
     '                    except DontKnow:               # study: this left-hand side is not tried for A again\n'
     '                        continue\n'),
    ('                o2 = ins & (state[a] == 0)\n                if not o2.any():\n                    break\n                guesses += 1\n',
     '                o2 = ins & (state[a] == 0) & ~np.isin(idx, list(SKIP))\n                if not o2.any():\n                    break\n                guesses += 1\n'),
    ('                ans = ask(int(L[i]), a, "guess_q")\n',
     '                try:\n'
     '                    ans = ask(int(L[i]), a, "guess_q")\n'
     '                except DontKnow:                   # study: no guess on this candidate again\n'
     '                    SKIP.add(int(idx[i]))\n'
     '                    continue\n'),
    ('            x = qx(0, 0, order, a) if order else 0      # M is empty: A is constant\n'
     '            if "lc" in rules and adv is not None and not (L == x).any():\n'
     '                adv.evidence_lhs(x)\n'
     '                fresh[0] = False\n'
     '            if not closure(x, H) & a:\n'
     '                if careful:                       # H holds only FDs that the designer answered\n'
     '                    ask(x, a, "confirm_q")\n'
     '                else:\n'
     '                    H.append((x, a))\n'
     '                    update()\n',
     '            try:\n'
     '                x = qx(0, 0, order, a) if order else 0      # M is empty: A is constant\n'
     '                if "lc" in rules and adv is not None and not (L == x).any():\n'
     '                    adv.evidence_lhs(x)\n'
     '                    fresh[0] = False\n'
     '                if not closure(x, H) & a:\n'
     '                    if careful:                       # H holds only FDs that the designer answered\n'
     '                        ask(x, a, "confirm_q")\n'
     '                    else:\n'
     '                        H.append((x, a))\n'
     '                        update()\n'
     '            except DontKnow:                          # study: QuickXplain gives up, the maximal set stays undecided\n'
     '                UND.add((M, a))\n'
     '                return\n'),
    # the end of a run
    ('                if best is None:      # no maximal set of H that holds on the data is left: an open candidate\n',
     '                if best is None:      # no maximal set of H that holds on the data is left: an open candidate\n'
     '                    if UND and UND & set(targets()):           # study: an undecided maximal set, a partial certificate\n'
     '                        break\n'),
    ('    if not certified and len(opn) <= 500:\n',
     '    if ASK is None and not certified and len(opn) <= 500:\n'),
    ('"time_model": round(sum(1 + 0.25 * (x - 2) for x in st["attrs"]), 2), "attrs_sum": int(sum(st["attrs"]))}\n',
     '"time_model": round(sum(1 + 0.25 * (x - 2) for x in st["attrs"]), 2), "attrs_sum": int(sum(st["attrs"])), "dk": st["dk"],\n'
     '           "undecided": [[[b["names"][i] for i in range(n) if M >> i & 1], b["names"][a.bit_length() - 1]]\n'
     '                         for M, a in sorted(UND)]}\n'),
]


def main():
    with open(SRC, encoding="utf-8") as fh:
        s = fh.read()
    src_md5 = hashlib.md5(s.encode("utf-8")).hexdigest()[:12]
    for old, new in REPL:
        assert s.count(old) == 1, ("pattern not found once", old[:70], s.count(old))
        s = s.replace(old, new)
    head = (f'# GENERATED by study/code/make_v6fstudy.py from confirm/v6f.py {src_md5}; do not edit\n'
            '# imported after common.py, which puts the method on sys.path\n')
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(head + s)
    print("wrote", OUT, "from v6f.py", src_md5)


if __name__ == "__main__":
    main()
