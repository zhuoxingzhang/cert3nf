"""
Checks of study/code/v6fstudy.py against the frozen v6f.py on the three relations of the study, both truths, in the main form:
the trusting mode (exact designer) and the careful mode (designer error 0, 0.02, 0.05, three seeds).

  same      v6fstudy.run with ASK unset gives v6f.run's output field for field
  hook      v6fstudy.run with ASK set to a person who answers as v6f's simulated designer gives the same output (the robust design
            of an uncertified run, fb_*, is not computed for a person)
  stored    under CONFIRM_BATCH=1 and budget 1000, both reproduce the rows of confirm/v6f_runs/main_e2a6af907596_dev_<truth>.jsonl
  dk        a person who answers don't know at random (15%): every run ends within the budget, every certificate is exact, and no
            certificate leaves an undecided maximal set of H that holds on the data
  stop      a person who stops before the j-th answer: the run ends with j - 1 questions and no certificate
auto_confirm caches the training relations of the first truth it sees, so each truth runs in its own process.
Usage (STUDY_SOURCE, the confirm/ folder with all inputs; see common.py):
  python study/code/check_v6fstudy.py --truth full|sure [--quick]
  CONFIRM_BATCH=1 python study/code/check_v6fstudy.py --truth full|sure --stored
"""
import hashlib, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["STUDY_BUILD"] = "1"      # the method in STUDY_SOURCE, with all its inputs
import common as K

TRUTH = sys.argv[sys.argv.index("--truth") + 1]
K.setenv(TRUTH)
import auto_common as AC
import auto_confirm as C
import v6f
import v6fstudy
from price import closure

SPEC = K.VARIANT
BASE, _, RULES = SPEC.partition("|")
RULES = tuple(RULES.split("+"))
EXTRA = {"dk", "undecided"}


def advisor(b):
    adv = v6f.advisor_for(b, os.path.join(K.SOURCE, K.ANSWERS), "q35", False, True)[0]
    adv.__class__ = v6f.LCAdvisor
    adv.attach(v6f.class_rate(b["name"]), [K.mask(p[0]) for p in b["P"]])
    return adv


def run(mod, ds, err, seed, careful):
    b = AC.load(ds)
    _, _, cap, guess, mode, mcheap = v6f.VARIANTS[BASE]
    return mod.run(b, advisor(b), cap, True, guess, mode, mcheap, RULES, err, seed, careful), b


def simulated_person(b, ds, seed, err):
    """the simulated designer of v6f, as a person who answers through the hook"""
    n = len(b["R"])
    reach = [(K.mask(l), K.mask(r)) for l, r in AC.oracle(b)]

    def ask(z, a, k, kind):
        truth = bool(closure(z, reach) & a)
        if err <= 0:
            return truth
        return truth != C.designer_flip(ds, seed, (tuple(i for i in range(n) if z >> i & 1), (a.bit_length() - 1,)), err, k)
    return ask


def dk_person(b, ds, seed, rate=0.15):
    reach = [(K.mask(l), K.mask(r)) for l, r in AC.oracle(b)]

    def ask(z, a, k, kind):
        h = hashlib.sha256(repr((ds, seed, z, a, k, "dk")).encode()).digest()
        if int.from_bytes(h[:8], "big") / 2 ** 64 < rate:
            return None
        return bool(closure(z, reach) & a)
    return ask


def stop_person(b, j):
    cnt = [0]
    base = simulated_person(b, b["name"], 0, 0.0)

    def ask(z, a, k, kind):
        cnt[0] += 1
        if cnt[0] >= j:
            raise v6fstudy.Budget
        return base(z, a, k, kind)
    return ask


def differ(a, s):
    skip = EXTRA | {k for k in set(a) | set(s) if k.startswith("fb_")}
    return sorted(k for k in set(a) | set(s) if k not in skip and a.get(k) != s.get(k))


def plan(quick):
    out = [(ds, 0.0, 0, False) for ds in K.RELATIONS.values()] + [(ds, 0.0, 0, True) for ds in K.RELATIONS.values()]
    if not quick:
        out += [(ds, e, s, True) for ds in K.RELATIONS.values() for e in (0.02, 0.05) for s in range(3)]
    return out


def compare(quick):
    bad = 0
    for ds, err, seed, careful in plan(quick):
        a, b = run(v6f, ds, err, seed, careful)
        v6fstudy.ASK = None
        s, _ = run(v6fstudy, ds, err, seed, careful)
        v6fstudy.ASK = simulated_person(b, ds, seed, err)
        h, _ = run(v6fstudy, ds, err, seed, careful)
        v6fstudy.ASK = None
        d1, d2 = differ(a, s), differ(a, h)
        bad += bool(d1 or d2)
        print(f"{TRUTH} {ds:14s} err {err} seed {seed} careful {int(careful)}: questions {a['questions']:3d} certified {a['certified']} exact {a['cert_exact']} wrong {a['wrong_cert']}"
              + (f" DIFF same {d1} hook {d2}" if d1 or d2 else ""))
    print(f"same/hook: {len(plan(quick))} runs, {bad} differ")
    return bad


def stored():
    assert os.environ["CONFIRM_BATCH"] == "1", "the stored rows use the first pool"
    v6f.BUDGET = v6fstudy.BUDGET = 1000
    with open(os.path.join(K.SOURCE, "v6f_runs", f"main_e2a6af907596_dev_{TRUTH}.jsonl"), encoding="utf-8") as fh:
        rows = {r["dataset"]: r for r in map(json.loads, fh) if r["variant"] == SPEC}
    bad = 0
    for ds in K.RELATIONS.values():
        r = rows[ds]
        a, _ = run(v6f, ds, 0.0, 0, False)
        s, _ = run(v6fstudy, ds, 0.0, 0, False)
        d = [k for k in a if k != "secs" and a[k] != r.get(k)] + differ(a, s)
        bad += bool(d)
        print(f"stored {TRUTH} {ds}: questions {a['questions']} (stored {r['questions']})" + (f" DIFF {d}" if d else " same"))
    print(f"stored: {bad} differ")
    return bad


def dk_stop(quick):
    nd = nbad = 0
    for ds in K.RELATIONS.values():
        for careful in (False, True):
            for seed in range(3 if quick else 20):
                b = AC.load(ds)
                v6fstudy.ASK = dk_person(b, ds, seed)
                o, _ = run(v6fstudy, ds, 0.0, seed, careful)
                v6fstudy.ASK = None
                nd += 1
                if o["questions"] > v6fstudy.BUDGET or (o["certified"] and not o["cert_exact"]):
                    nbad += 1
                    print("DK FAIL", TRUTH, ds, careful, seed, o["questions"], o["certified"], o["cert_exact"])
        for j in (1, 7):              # the runs of an exact person take at least 11 answers
            b = AC.load(ds)
            v6fstudy.ASK = stop_person(b, j)
            o, _ = run(v6fstudy, ds, 0.0, 0, False)
            v6fstudy.ASK = None
            if o["questions"] != j - 1 or o["certified"]:
                nbad += 1
                print("STOP FAIL", TRUTH, ds, j, o["questions"], o["certified"])
    print(f"dk runs {nd}, dk/stop failures {nbad}")
    return nbad


def main():
    quick = "--quick" in sys.argv
    if "--stored" in sys.argv:
        sys.exit(1 if stored() else 0)
    sys.exit(1 if compare(quick) + dk_stop(quick) else 0)


if __name__ == "__main__":
    main()
