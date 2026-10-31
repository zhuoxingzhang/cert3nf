"""
Shared pieces of the human-designer study (study/README.md): the three relations, the fixed assignment table, the
truths, and how a question Z -> A is shown to a participant.

Questions are (Z, A) pairs of bit masks over the attributes of the data file, as in v5.py and v5tol.py.  A question is
shown in the form that lists fewer attributes: "agree on Z" when |Z| <= n - |Z|, otherwise "agree on everything
except R - Z" (R - Z contains A).  a(q) = min(|Z|, n - |Z|) + 1, the attrs statistic of v5.

Two places of the method.  Sessions, the server and replay import it from this repository's confirm/ and take each
relation, its data and its advisor from prebuilt/<relation>.pkl, so that the server needs neither the other relations
nor the LLM answers.  The build steps (make_block, check_v5study, build_kit) set STUDY_BUILD=1 and import it from
STUDY_SOURCE, a confirm/ folder with all its inputs including the LLM answers (default: ../paper1/confirm next to this
repository, the authors' working copy, whose code equals confirm/ up to comments; build_kit.py checks this).
"""
import json, os, pickle, sys

HERE = os.path.dirname(os.path.abspath(__file__))           # study/code
KIT = os.path.dirname(HERE)                                  # study
REPO = os.path.dirname(KIT)
BLOCKS = os.path.join(KIT, "blocks")
PREBUILT = os.path.join(KIT, "prebuilt")
BUILD = os.environ.get("STUDY_BUILD") == "1"
SOURCE = os.environ.get("STUDY_SOURCE") or os.path.join(os.path.dirname(REPO), "paper1", "confirm")   # build steps
METHOD = os.path.join(REPO, "confirm")
CONFIRM = SOURCE if BUILD else METHOD
if CONFIRM not in sys.path:
    sys.path.insert(0, CONFIRM)

RELATIONS = {"R1": "ssb_customer", "R2": "tpcds_core", "R3": "fresh_abs_mb"}
ASSIGN = {"01": ("R1", "R2"), "02": ("R2", "R3"), "03": ("R3", "R1")}     # README, the same for E, P, U
CONDITIONS = ("E", "P", "U")
ANSWERS = "llm_fresh_full_q35_ms"         # the advisor of the live session: full truth, the settings of item 34
VARIANT = "v5t"                           # the tolerant mode (mechanism c), statistics and LLM advisor
SAMPLES = os.path.join(os.path.dirname(SOURCE), "e3", "samples")      # build steps only


def setenv(truth):
    """the environment of the item-34 runs (CONFIRM_BATCH unset: the development pool of v5_dev)"""
    os.environ["CONFIRM_ORACLE"] = "gold"
    os.environ["CONFIRM_TRUTH"] = truth
    os.environ.pop("CONFIRM_BATCH", None)


def parse(participant):
    """(condition, number, test) of a participant code: E01, P02, U03; TE01 etc. for a test that is not part of the
    study (the experimenter's own tries and the pilot), and TP02-1a2b3c for a try from the site's start page"""
    code, _, tag = participant.partition("-")
    test = code.startswith("T") and len(code) == 4
    cond, num = code[1 if test else 0], code[-2:]
    assert cond in CONDITIONS and num in ASSIGN and len(code) == 3 + test, participant
    assert not tag or test and len(tag) == 6 and all(c in "0123456789abcdef" for c in tag), participant
    return cond, num, test


def relation_of(participant, session_no):
    """the relation of a participant (E01, P02, ..., TE01) in session 1 or 2"""
    _, num, _ = parse(participant)
    assert session_no in (1, 2), session_no
    return RELATIONS[ASSIGN[num][session_no - 1]]


def mask(idx):
    return sum(1 << i for i in idx)


def members(m, n):
    return [i for i in range(n) if m >> i & 1]


def closure(x, F):
    while True:
        y = x
        for l, r in F:
            if l & ~y == 0:
                y |= r
        if y == x:
            return x
        x = y


class Rel:
    """one relation under both truths: sigma0, the documented FDs, the minimal FDs on the data"""

    def __init__(self, ds):
        import auto_common as AC
        self.ds = ds
        bs = {}
        for t in ("full", "sure"):
            setenv(t)
            bs[t] = AC.load(ds)
        setenv("full")
        b = bs["full"]
        self.names = b["names"]
        self.n = len(self.names)
        self.full = (1 << self.n) - 1
        self.sig0 = [(mask(l), mask(r)) for l, r in b["sigma0"]]
        self.gold = {t: self.sig0 + [(mask(l), mask(r)) for l, r in bs[t]["gold"]] for t in bs}
        with open(os.path.join(BLOCKS, "supplement.json"), encoding="utf-8") as fh:
            sup = json.load(fh)["datasets"].get(ds, [])
        idx = {x: i for i, x in enumerate(b["names"])}
        self.supplement = sup
        self.gold["supp"] = self.gold["full"] + [(mask(idx[x] for x in f["lhs"]), mask(idx[x] for x in f["rhs"]))
                                                 for f in sup]          # full truth plus the hand-checked FDs
        self.P = [(mask(l), mask(r)) for l, r in b["P"]]
        minfd = {}
        for l, r in b["P"] + b["implied0"]:
            minfd.setdefault(mask(r), []).append(mask(l))
        self.minfd = minfd
        with open(os.path.join(SAMPLES, ds + ".json"), encoding="utf-8") as fh:
            s = json.load(fh)
        assert s["attributes"] == self.names, ds
        self.sample, self.rows = s["sample"], s["rows"]

    def truth(self, z, a, t):
        return bool(closure(z, self.gold[t]) & a)

    def holds(self, z, a):
        """Z -> A holds on the data: Z contains the left-hand side of a minimal FD on the data"""
        return any(l & ~z == 0 for l in self.minfd.get(a, ()))

    def minimal(self, z, a):
        return z in self.minfd.get(a, ())

    def implied0(self, z, a):
        return bool(closure(z, self.sig0) & a)

    def show(self, z, a):
        """how the question is shown: (form, listed attribute names, rhs name, a_q, English text).  The question is
        about the rule of the domain, not about the rows: every question the method asks holds on the data."""
        n = self.n
        k = bin(z).count("1")
        rhs = self.names[a.bit_length() - 1]
        if n - k < k:
            others = [self.names[i] for i in members(self.full & ~z & ~a, n)]
            form, listed = "except", others + [rhs]
            text = (f"Must any two records that agree on all attributes except {join(listed)} "
                    f"also agree on {rhs}?")
        else:
            form, listed = "agree", [self.names[i] for i in members(z, n)]
            text = (f"Must any two records that agree on {join(listed)} also agree on {rhs}?" if listed else
                    f"Must all records agree on {rhs}?")
        return form, listed, rhs, min(k, n - k) + 1, text

    def key(self, lhs_names, rhs_name):
        idx = {a: i for i, a in enumerate(self.names)}
        return mask(idx[x] for x in lhs_names), 1 << idx[rhs_name]


def join(xs):
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def md5(path):
    import hashlib
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()[:12]


_PICKLES = {}


def build(ds):
    """(Rel, the data b of AC.load, the advisor of VARIANT) of relation ds under the full truth, from STUDY_SOURCE"""
    assert BUILD, "building needs STUDY_BUILD=1 (STUDY_SOURCE with all inputs)"
    import auto_common as AC
    import v5
    import v5study
    rel = Rel(ds)
    setenv("full")
    b = AC.load(ds)
    llm, _ = v5study.VARIANTS[VARIANT]
    return rel, b, v5.advisor_for(b, os.path.join(SOURCE, ANSWERS), "q35", llm, True)[0]


def prebuilt(ds):
    """fresh copies of (Rel, b, advisor) of relation ds: built from STUDY_SOURCE in a build step, otherwise
    unpickled from prebuilt/; a session changes its advisor, so every session gets its own"""
    if BUILD:
        return build(ds)
    if ds not in _PICKLES:
        with open(os.path.join(PREBUILT, ds + ".pkl"), "rb") as fh:
            _PICKLES[ds] = fh.read()
    return pickle.loads(_PICKLES[ds])
