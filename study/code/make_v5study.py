"""
Generate study/code/v5study.py, the method of the live sessions, from confirm/v5tol.py by exact replacements (each
pattern must occur once), so that the difference to the frozen method is these lines only:

  hook      designer(z, a, k, kind) calls the module-level ASK(z, a, k, kind) when it is set: a person answers True,
            False or None (don't know), or raises Budget to stop.  With ASK None the designer is v5tol's.
  stop      a Budget raised by the person does not count the unanswered question; the run ends as at the budget.
  dk        don't know counts as a question and enters no history: a candidate of discovery is
            skipped, a guess is not made again, a maximal set (asked, or in QuickXplain, or the confirmation of the FD
            it found) stays undecided and is not asked again, a question to ask again is not asked again.  An
            undecided maximal set that is still one of H that holds on the data leaves no certificate (a partial one).

With no don't know and no stop, v5study.run is v5tol.run question for question (check_v5study.py).
Usage:  python study/code/make_v5study.py
"""
import hashlib, os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(os.path.dirname(HERE)), "confirm", "v5tol.py")
OUT = os.path.join(HERE, "v5study.py")

REPL = [
    # module: the hook and the exception
    ('def flip_uniform(ds, seed, p, eps, k=0):',
     'ASK = None             # study: the person who answers, ASK(z, a, k, kind) -> True / False / None (don\'t know)\n\n\n'
     'class DontKnow(Exception):\n    pass\n\n\n'
     'def flip_uniform(ds, seed, p, eps, k=0):'),
    # state
    ('    hist = {}                                      # question (Z, A) -> the designer\'s answers\n',
     '    hist = {}                                      # question (Z, A) -> the designer\'s answers\n'
     '    DK, UND, SKIP = set(), set(), set()            # study: questions answered don\'t know, maximal sets left\n'
     '                                                   # undecided, candidates skipped\n'),
    ('          "reask_q": 0}\n', '          "reask_q": 0, "dk": 0}\n'),
    # the designer
    ('    def designer(z, a, k):\n        truth = bool(closure(z, reach) & a)\n',
     '    def designer(z, a, k, kind=None):\n'
     '        if ASK is not None:                        # study: a person answers\n'
     '            return ASK(z, a, k, kind)\n'
     '        truth = bool(closure(z, reach) & a)\n'),
    ('        v = hist.setdefault(key, [])\n        v.append(designer(key[0], key[1], len(v)))\n',
     '        v = hist.setdefault(key, [])\n'
     '        try:\n'
     '            x = designer(key[0], key[1], len(v), kind)\n'
     '        except Budget:                             # study: the person stopped, the open question is not counted\n'
     '            st["q"] -= 1\n'
     '            st[kind] -= 1\n'
     '            st["attrs"].pop()\n'
     '            if not v:\n'
     '                del hist[key]\n'
     '            raise\n'
     '        if x is None:                              # study: don\'t know counts as a question, enters no history\n'
     '            st["dk"] += 1\n'
     '            DK.add(key)\n'
     '            if not v:\n'
     '                del hist[key]\n'
     '            raise DontKnow\n'
     '        v.append(x)\n'),
    # re-asks
    ('                if len(hist[q]) < REASK:\n                    return q\n',
     '                if len(hist[q]) < REASK and q not in DK:\n                    return q\n'),
    ('            if net(v) is None and len(v) < REASK:\n',
     '            if net(v) is None and len(v) < REASK and k not in DK:\n'),
    ('                if k is not None:\n                    put(k, "reask_q")\n                    continue\n',
     '                if k is not None:\n'
     '                    try:\n'
     '                        put(k, "reask_q")\n'
     '                    except DontKnow:\n'
     '                        pass\n'
     '                    continue\n'),
    ('                again = [k for k in sorted(dep, key=lambda q: -dep[q]) if len(hist[k]) < REASK]\n',
     '                again = [k for k in sorted(dep, key=lambda q: -dep[q]) if len(hist[k]) < REASK and k not in DK]\n'),
    ('                put(again[0], "reask_q")\n                continue\n',
     '                try:\n'
     '                    put(again[0], "reask_q")\n'
     '                except DontKnow:\n'
     '                    pass\n'
     '                continue\n'),
    # discovery
    ('                opn = [i for i, a, k in poss if state[a][k] == 0 and i not in adv.answered]\n',
     '                opn = [i for i, a, k in poss if state[a][k] == 0 and i not in adv.answered and i not in SKIP]\n'),
    ('                ans = ask(l, a, "disc_q")\n                observe(i, ans)\n',
     '                try:\n'
     '                    ans = ask(l, a, "disc_q")\n'
     '                except DontKnow:                       # study: the candidate is skipped\n'
     '                    SKIP.add(i)\n'
     '                    continue\n'
     '                observe(i, ans)\n'),
    # certification: selection, end, the maximal set, guesses, QuickXplain
    ('                    if not inside.any() or known(M, a) is False:\n',
     '                    if not inside.any() or known(M, a) is False or (M, a) in UND:\n'),
    ('            if best is None:\n                if not tol:\n',
     '            if best is None:\n'
     '                if UND and UND & set(targets()):       # study: an undecided maximal set, a partial certificate\n'
     '                    break\n'
     '                if not tol:\n'),
    ('            if not ask(M, a, "max_asked"):\n',
     '            try:\n'
     '                ansm = ask(M, a, "max_asked")\n'
     '            except DontKnow:                          # study: the maximal set stays undecided\n'
     '                UND.add((M, a))\n'
     '                continue\n'
     '            if not ansm:\n'),
    ('                    o2 = ins & (state[a] == 0)\n',
     '                    o2 = ins & (state[a] == 0) & ~np.isin(idx, list(SKIP))\n'),
    ('                    ans = ask(int(L[i]), a, "guess_q")\n',
     '                    try:\n'
     '                        ans = ask(int(L[i]), a, "guess_q")\n'
     '                    except DontKnow:                   # study: no guess on this candidate again\n'
     '                        SKIP.add(int(idx[i]))\n'
     '                        continue\n'),
    ('            if x is None:\n'
     '                x = qx(0, 0, order, a)\n'
     '                if not closure(x, H) & a:\n'
     '                    if tol:                           # H holds only the designer\'s answers\n'
     '                        ask(x, a, "confirm_q")\n'
     '                    else:\n'
     '                        H.append((x, a))\n'
     '                        update()\n',
     '            if x is None:\n'
     '                try:\n'
     '                    x = qx(0, 0, order, a)\n'
     '                    if not closure(x, H) & a:\n'
     '                        if tol:                           # H holds only the designer\'s answers\n'
     '                            ask(x, a, "confirm_q")\n'
     '                        else:\n'
     '                            H.append((x, a))\n'
     '                            update()\n'
     '                except DontKnow:                      # study: QuickXplain gives up, the maximal set stays undecided\n'
     '                    UND.add((M, a))\n'
     '                    continue\n'),
    # output
    ('           "schemata": len(D)}\n',
     '           "schemata": len(D), "dk": st["dk"],\n'
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
    head = (f'# GENERATED by study/code/make_v5study.py from confirm/v5tol.py {src_md5}; do not edit\n'
            '# imported after common.py, which puts the method on sys.path\n')
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(head + s)
    print("wrote", OUT, "from v5tol.py", src_md5)


if __name__ == "__main__":
    main()
