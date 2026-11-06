"""Design note item 69 (c), check 1: v6f_designer.flip on random questions against the frozen v5tol.py and auto_confirm.designer_flip,
and the moments of the correlated designer.  Any difference exits with 1.
Usage (in confirm/, where v5tol.py is the frozen file):  python scripts/test_v6f_designer.py"""
import hashlib, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import auto_confirm as C
import v5tol
import v6f_designer as D

FROZEN = {"v5tol.py": "f3ec39c04c59", "v6f.py": "e2a6af907596", "auto_confirm.py": "cf2a596a1578"}
for f, h in FROZEN.items():
    got = hashlib.md5(open(f, "rb").read()).hexdigest()[:12]
    assert got == h, (f, got, h)
ORIG = D.FLIP
assert ORIG is C.designer_flip
rnd = random.Random(69)


def question():
    n = rnd.randint(2, 25)
    z = sorted(rnd.sample(range(n), rnd.randint(1, n - 1)))
    return (f"rel{rnd.randint(0, 57)}", rnd.randint(0, 2), (tuple(z), (rnd.randint(0, n - 1),)), rnd.choice((0.02, 0.05)), rnd.randint(0, 3))


bad = 0
N = 20000
for _ in range(N):
    ds, seed, p, eps, k = question()
    D.RHO, D.REPEATED = 0.0, False
    bad += D.flip(ds, seed, p, eps, k) != ORIG(ds, seed, p, eps, k)
    bad += D.flip_uniform(ds, seed, p, eps, k) != v5tol.flip_uniform(ds, seed, p, eps, k)
    bad += (D.flip_uniform(ds, seed, p, eps, k) < eps) != ORIG(ds, seed, p, eps, k)
    D.REPEATED = True
    bad += D.flip(ds, seed, p, eps, k) != ORIG(ds, seed, p, eps, 0)
    for rho in (0.25, 0.5):
        bad += D.flip_rate(ds, seed, p, eps, rho) != v5tol.flip_rate(ds, seed, p, eps, rho)
        D.RHO, D.REPEATED = rho, False
        bad += D.flip(ds, seed, p, eps, k) != (v5tol.flip_uniform(ds, seed, p, eps, k) < v5tol.flip_rate(ds, seed, p, eps, rho))
        D.RHO, D.REPEATED = rho, True
        bad += D.flip(ds, seed, p, eps, k) != (v5tol.flip_uniform(ds, seed, p, eps, 0) < v5tol.flip_rate(ds, seed, p, eps, rho))
        D.RHO, D.REPEATED = 0.0, False
print(f"{N} random questions, differences {bad}")

M = 200000
for eps in (0.02, 0.05):
    for rho in (0.25, 0.5):
        D.RHO, D.REPEATED = rho, False
        a, b, r = [], [], []
        for i in range(M):
            p = ((i,), (0,))
            r.append(D.flip_rate("moments", 0, p, eps, rho))
            a.append(D.flip("moments", 0, p, eps, 0))
            b.append(D.flip("moments", 0, p, eps, 1))
        c = float(np.corrcoef(np.array(a, dtype=float), np.array(b, dtype=float))[0, 1])
        print(f"eps {eps} rho {rho}: mean eps_q {np.mean(r):.5f}, first answer wrong {np.mean(a):.5f}, second {np.mean(b):.5f}, correlation {c:.3f}")
        if abs(np.mean(r) - eps) > 3 * np.sqrt(eps * (1 - eps) * rho / M) + 1e-4 or abs(c - rho) > 0.05:
            bad += 1
            print("  outside the expected range")
sys.exit(1 if bad else 0)
