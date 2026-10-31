"""
Builds what the study server needs beyond this repository's code (README, "Building").

1. Checks that the modules a session imports from this repository (confirm/, e2/e2_tpch.py, o3_lossiness_check.py,
   sensitivity_bruteforce.py) have the same code as those in STUDY_SOURCE, the frozen method the experiments ran,
   comments and docstrings aside.  Two differences are expected: baseline_direct.py has another help text, and
   sensitivity_bruteforce.py loads the synthesis engine from baselines.py in this repository.
   test_session.py --compare checks that sessions agree.
2. prebuilt/<relation>.pkl: (Rel, the data of AC.load, the advisor) of each study relation under the full truth,
   built from STUDY_SOURCE with all its inputs (the advisor's prior is trained on the other relations and uses the LLM
   answers), so that the server needs neither (the build peaks near 530 MB, a session needs a few MB).
Writes prebuilt/MANIFEST.json (md5 of every pickle and input).
Usage:  python build_kit.py
"""
import ast, json, os, pickle, platform, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["STUDY_BUILD"] = "1"
import common as K

SRC_ROOT = os.path.dirname(K.SOURCE)
MODULES = [f"confirm/{f}" for f in ("v5.py", "v5tol.py", "auto_common.py", "auto_confirm.py", "auto_answer.py",
                                    "auto_noisy.py", "baseline_direct.py", "bench.py", "drd.py", "estimators.py",
                                    "llm_rules.py", "price.py")]
MODULES += ["e2/e2_tpch.py", "o3_lossiness_check.py", "sensitivity_bruteforce.py"]
EXPECTED = {"confirm/baseline_direct.py", "sensitivity_bruteforce.py"}


def code_of(path):
    """the module's syntax tree without docstrings (comments are not in it)"""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for n in ast.walk(tree):
        body = getattr(n, "body", None)
        if (isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and body
                and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            n.body = body[1:] or [ast.Pass()]
    return ast.dump(tree)


def check_method():
    man = {}
    for m in MODULES:
        here, there = os.path.join(K.REPO, m), os.path.join(SRC_ROOT, m)
        same = code_of(here) == code_of(there)
        assert same or m in EXPECTED, (m, "differs from the frozen method in code")
        man[m] = {"md5": K.md5(here), "source_md5": K.md5(there), "same_code": same}
    print("method:", sum(v["same_code"] for v in man.values()), "of", len(man), "modules have the frozen code;",
          "expected differences:", sorted(m for m, v in man.items() if not v["same_code"]))
    return man


def build_pickles(method):
    import numpy as np
    os.makedirs(K.PREBUILT, exist_ok=True)
    man = {"python": platform.python_version(), "numpy": np.__version__, "variant": K.VARIANT,
           "answers": K.ANSWERS, "frozen": {m: method[m]["source_md5"] for m in ("confirm/v5.py", "confirm/v5tol.py")},
           "method": method, "relations": {}}
    for ds in K.RELATIONS.values():
        path = os.path.join(K.PREBUILT, ds + ".pkl")
        with open(path, "wb") as fh:
            pickle.dump(K.build(ds), fh, protocol=5)
        man["relations"][ds] = {"pkl": K.md5(path), "bytes": os.path.getsize(path),
                                "data": K.md5(os.path.join(SRC_ROOT, "e3", "data", ds + ".json")),
                                "sample": K.md5(os.path.join(K.SAMPLES, ds + ".json"))}
        print("prebuilt", ds, man["relations"][ds])
    man["supplement"] = K.md5(os.path.join(K.BLOCKS, "supplement.json"))
    with open(os.path.join(K.PREBUILT, "MANIFEST.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(man, fh, indent=1)


if __name__ == "__main__":
    build_pickles(check_method())
