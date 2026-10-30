"""
Classical 3NF synthesis and iCONF as one elimination skeleton over the atomic closure, ported from the Java code
base of iCONF.

Algorithms:
  - synthesis : classical lossless, dependency-preserving 3NF synthesis  [Biskup-Dayal-Bernstein 1979]
  - bccover   : BCNF whenever one exists                                  [Osborn 1979]
  - conf      : 3NF, redundant schemata removed by decreasing #min keys   [Zhang-Chen-Link 2023]
  - iconf     : 3NF, critical removed by decreasing #non-key FDs (f),      [Zhang-Link 2025]
                then non-critical removed by decreasing #min keys

Input: (R, Sigma_a, keys), where Sigma_a is a set of single-RHS atomic FDs and keys are the minimal keys of R.
An attribute is an int, an attribute set a frozenset, and an FD a pair (lhs frozenset, rhs frozenset of one attribute).
"""

# ---------- FD primitives ----------

def closure(X, sigma):
    c = set(X)
    changed = True
    while changed:
        changed = False
        for lhs, rhs in sigma:
            if lhs <= c and not rhs <= c:
                c |= rhs
                changed = True
    return c

def is_superkey(X, R, sigma):
    return R <= closure(X, sigma)

def refine_min_key(sigma, key, R):
    # greedily drop attributes while the rest still determines R
    k = set(key)
    for a in list(key):
        if R <= closure(k - {a}, sigma):
            k.discard(a)
    return frozenset(k)

def minimal_keys(R, sigma):
    # Lucchesi-Osborn
    keys = [refine_min_key(sigma, R, R)]
    i = 0
    while i < len(keys):
        cur = keys[i]
        for lhs, rhs in sigma:
            S = set(lhs) | (cur - rhs)
            if not any(mk <= S for mk in keys):       # non-redundant candidate
                mk = refine_min_key(sigma, S, R)
                if mk not in keys:
                    keys.append(mk)
        i += 1
    return keys

def projection(sigma, XA):
    # the atomic FDs within XA; exact when sigma is a complete atomic closure
    return [(lhs, rhs) for lhs, rhs in sigma if (lhs | rhs) <= XA]

def is_redundant(fd, sigma):
    lhs, rhs = fd
    rest = [f for f in sigma if f is not fd]
    return rhs <= closure(lhs, rest)

def mixed_nonkey_fds(XA, proj_XA, keys_XA):
    # greedy non-redundant non-key FD set of the mixed cover: keep the FDs that the minimal keys together with the
    # other FDs do not imply (iCONF ranks critical schemata by its size)
    sigma_k = [(k, XA - k) for k in keys_XA]          # key FDs  K -> XA\K
    sigma_f = list(proj_XA)
    for fd in list(proj_XA):
        sigma_f.remove(fd)
        if not fd[1] <= closure(fd[0], sigma_k + sigma_f):   # keys + others do NOT imply fd
            sigma_f.append(fd)
    return sigma_f

# ---------- synthesis skeleton ----------

def _add(D, XA, proj_XA):
    if not any(s == XA for s, _ in D):
        D.append((XA, proj_XA))

def _eliminate(order, sigma_work, D, proj):
    # walk FDs in `order`; drop redundant ones from sigma_work, otherwise keep their schema
    for fd in order:
        if is_redundant(fd, sigma_work):
            sigma_work.remove(fd)
        else:
            XA = fd[0] | fd[1]
            _add(D, XA, proj[XA])

def prepare(sigma_a):
    subs = {fd[0] | fd[1] for fd in sigma_a}
    proj = {XA: projection(sigma_a, XA) for XA in subs}
    mkeys = {XA: minimal_keys(XA, proj[XA]) for XA in subs}
    nonkey = {XA: mixed_nonkey_fds(XA, proj[XA], mkeys[XA]) for XA in subs}
    crit = [fd for fd in sigma_a if nonkey[fd[0] | fd[1]]]   # critical iff its mixed cover has a non-key FD
    cset = set(crit)
    noncrit = [fd for fd in sigma_a if fd not in cset]
    return {"proj": proj, "mkeys": mkeys, "nonkey": nonkey, "crit": crit, "noncrit": noncrit}

def synthesize(R, sigma_a, keys, mode, prep=None):
    R = frozenset(R)
    if prep is None:
        prep = prepare(sigma_a)
    proj, mkeys, nonkey = prep["proj"], prep["mkeys"], prep["nonkey"]
    crit, noncrit = prep["crit"], prep["noncrit"]
    sigma_work = list(sigma_a)
    D = []

    f_count = lambda fd: len(nonkey[fd[0] | fd[1]])      # f: greedy non-key FD count
    key_count = lambda fd: len(mkeys[fd[0] | fd[1]])

    if mode == "synthesis":
        _eliminate(list(sigma_a), sigma_work, D, proj)
    elif mode == "bccover":
        _eliminate(crit, sigma_work, D, proj)         # strip removable critical first
        _eliminate(noncrit, sigma_work, D, proj)
    elif mode == "conf":
        _eliminate(sorted(sigma_a, key=key_count, reverse=True), sigma_work, D, proj)
    elif mode == "iconf":
        _eliminate(sorted(crit, key=f_count, reverse=True), sigma_work, D, proj)
        _eliminate(sorted(noncrit, key=key_count, reverse=True), sigma_work, D, proj)
    else:
        raise ValueError(mode)

    # subset removal
    D = [(XA, p) for XA, p in D if not any(XA < XA2 for XA2, _ in D)]
    # losslessness: ensure some schema contains a candidate key of R
    if not any(any(k <= XA for k in keys) for XA, _ in D):
        K = frozenset(min(keys, key=len))
        _add(D, K, projection(sigma_a, K))
    return D
