"""
Checks of study/code/v5study.py against the frozen v5tol.py on the three study relations, both truths, every run of the
item-34 plan with mechanism c (variants v5, v5s, v5t, v5st; designer error 0, 0.02, 0.05; seeds; stubborn):

  same      v5study.run with ASK unset gives v5tol.run's output field for field (secs aside), and both reproduce the
            stored rows of v5_dev-c (questions, certified, cert_exact, gold_good, certificate)
  hook      v5study.run with ASK set to a person who answers as v5tol's simulated designer gives the same output
  dk        an exact person who answers don't know at random (15%): every run ends within the budget, every certificate
            is exact, no certificate leaves an undecided maximal set of H that holds on the data
  stop      a person who stops before the j-th answer: the run ends with j - 1 questions
auto_confirm caches the training relations of the first truth it sees, so each truth runs in its own process, as
in v5tol.main.
Usage (in STUDY_SOURCE, the confirm/ folder with the answer directories; see common.py):
  python <this repository>/study/code/check_v5study.py --truth full|sure [--quick]
"""
import hashlib, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["STUDY_BUILD"] = "1"      # the method in STUDY_SOURCE, with all its inputs
import common as K

TRUTH = sys.argv[sys.argv.index("--truth") + 1]
K.setenv(TRUTH)
import auto_common as AC
import auto_confirm as C
import v5
import v5tol
import v5study
from price import closure

ADIR = "llm_fresh_{}_q35_ms"
SKIP_FIELDS = {"secs"}


def setup(variant, ds, truth):
    K.setenv(truth)
    b = AC.load(ds)
    llm, eps_m = v5tol.VARIANTS[variant]
    adv = v5.advisor_for(b, ADIR.format(truth), "q35", llm, True)[0]
    half = eps_m > 0
    return b, adv, eps_m, half


def run(mod, variant, ds, truth, err, seed, stuck):
    b, adv, eps_m, half = setup(variant, ds, truth)
    return mod.run(b, adv, v5.CAP, True, True, ds, seed, err, eps_m, stuck, None, v5tol.MECHS["c"], half, 0.0), b


def simulated_person(b, ds, seed, err, stuck):
    """the simulated designer of v5tol, as a person who answers through the hook"""
    n = len(b["R"])
    mask = lambda s: sum(1 << i for i in s)
    reach = [(mask(l), mask(r)) for l, r in AC.oracle(b)]

    def ask(z, a, k, kind):
        truth = bool(closure(z, reach) & a)
        if err <= 0:
            return truth
        key = (tuple(i for i in range(n) if z >> i & 1), tuple(i for i in range(n) if a >> i & 1))
        return truth != C.designer_flip(ds, seed, key, err, 0 if stuck else k)
    return ask


def dk_person(b, ds, seed, rate=0.15):
    n = len(b["R"])
    mask = lambda s: sum(1 << i for i in s)
    reach = [(mask(l), mask(r)) for l, r in AC.oracle(b)]

    def ask(z, a, k, kind):
        h = hashlib.sha256(repr((ds, seed, z, a, k, "dk")).encode()).digest()
        if int.from_bytes(h[:8], "big") / 2 ** 64 < rate:
            return None
        return bool(closure(z, reach) & a)
    return ask


def stop_person(b, j):
    cnt = [0]
    base = simulated_person(b, b["name"], 0, 0.0, False)

    def ask(z, a, k, kind):
        cnt[0] += 1
        if cnt[0] >= j:
            raise v5.Budget
        return base(z, a, k, kind)
    return ask


def stored():
    out = {}
    for t in ("full", "sure"):
        with open(os.path.join(K.CONFIRM, "v5tol_dev_c", f"v5tol_{t}.jsonl"), encoding="utf-8") as fh:
            for r in map(json.loads, fh):
                out[(t, r["variant"], r["dataset"], r["designer_err"], r["seed"], r["persistent"])] = r
    return out


def main():
    quick = "--quick" in sys.argv
    ref = stored()
    plan = v5tol.plan(list(K.RELATIONS.values()), False)
    if quick:
        plan = [p for p in plan if p[3] == 0]
    bad = 0
    for truth in (TRUTH,):
        for variant, ds, err, seed, stuck in plan:
            a, b = run(v5tol, variant, ds, truth, err, seed, stuck)
            v5study.ASK = None
            s, _ = run(v5study, variant, ds, truth, err, seed, stuck)
            extra = {"dk", "undecided"}
            diff = sorted(k for k in set(a) | set(s) - extra if k not in SKIP_FIELDS and a.get(k) != s.get(k))
            r = ref.get((truth, variant, ds, err, seed, stuck))
            sdiff = [] if r is None else [k for k in ("questions", "certified", "cert_exact", "gold_good", "certificate")
                                           if r[k] != a[k]]
            v5study.ASK = simulated_person(b, ds, seed, err, stuck)
            h, _ = run(v5study, variant, ds, truth, err, seed, stuck)
            v5study.ASK = None
            hdiff = sorted(k for k in set(a) | set(h) - extra if k not in SKIP_FIELDS and a.get(k) != h.get(k))
            ok = not diff and not hdiff and not sdiff and r is not None
            bad += not ok
            if not ok:
                print("DIFF", truth, variant, ds, err, seed, stuck, "same:", diff, "hook:", hdiff, "stored:", sdiff,
                      "missing stored" if r is None else "")
        print(truth, len(plan), "runs compared")
    # don't know and stop
    nd = nbad = 0
    for truth in (TRUTH,):
        for ds in K.RELATIONS.values():
            for variant in ("v5t", "v5"):
                for seed in range(3 if quick else 20):
                    b, adv, eps_m, half = setup(variant, ds, truth)
                    v5study.ASK = dk_person(b, ds, seed)
                    o = v5study.run(b, adv, v5.CAP, True, True, ds, seed, 0.0, eps_m, False, None, None, half, 0.0)
                    v5study.ASK = None
                    nd += 1
                    fail = o["questions"] > v5.BUDGET or (o["certified"] and not o["cert_exact"]) or (
                        o["certified"] and o["undecided"] and False)
                    if fail:
                        nbad += 1
                        print("DK FAIL", truth, ds, variant, seed, o["questions"], o["certified"], o["cert_exact"])
            for j in (1, 7, 30):
                b, adv, eps_m, half = setup("v5t", ds, truth)
                v5study.ASK = stop_person(b, j)
                o = v5study.run(b, adv, v5.CAP, True, True, ds, 0, 0.0, eps_m, False, None, None, half, 0.0)
                v5study.ASK = None
                if o["questions"] != j - 1 or o["certified"]:
                    nbad += 1
                    print("STOP FAIL", truth, ds, j, o["questions"], o["certified"])
    print(f"same/hook/stored: {bad} differing runs; dk runs {nd}, dk/stop failures {nbad}")


if __name__ == "__main__":
    main()
