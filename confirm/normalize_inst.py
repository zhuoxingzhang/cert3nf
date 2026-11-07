"""
Design note item 74: the instances of the 23 confirmatory relations with their values, for the value and duplication
features of Normalize (Papenbrock and Naumann, EDBT 2017), which the relation files of e3/data do not hold.

Each instance is rebuilt as build.py's mining stage builds it (build.instances, fresh.py with FRESH_RAW pointing at the
raw files of batch 3), constant columns dropped, and checked against e3/data/<ds>.json: attributes in order, dropped
constant columns, records, and distinct values per attribute.  A mismatch stops the script before anything is written.
Stored per relation in v6f_fresh3_extra/normalize/inst/<ds>.npz: names, M (records x attributes, int32 codes), len<j>
(the length of every value of attribute j, by code) and null (whether attribute j holds '?', the cleaned empty value).

Usage (in confirm/, on the host with the raw files of batch 3):
  FRESH_RAW=<raw files of batch 3> python normalize_inst.py [<ds>,...]
"""
import json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
E3 = os.path.join(HERE, "..", "e3")
OUT = os.path.join(HERE, "v6f_fresh3_extra", "normalize", "inst")
sys.path.insert(0, E3)
import build                                       # noqa: E402  (reads FRESH_RAW through fresh.py)


def main():
    fresh3 = [d for d, f in build.FAMILY.items() if f == "fresh3"]
    wanted = sys.argv[1].split(",") if len(sys.argv) > 1 else fresh3
    assert len(fresh3) == 23 and set(wanted) <= set(fresh3), (len(fresh3), wanted)
    os.makedirs(OUT, exist_ok=True)
    for ds in wanted:
        inst = build.instances(None, [ds])[ds]
        cols, all_names = inst["cols"], inst["attributes"]
        const = [a for a, c in zip(all_names, cols) if len(np.unique(c.codes)) <= 1]
        keep = [j for j, a in enumerate(all_names) if a not in const]
        names = [all_names[j] for j in keep]
        with open(os.path.join(E3, "data", ds + ".json"), encoding="utf-8") as fh:
            ref = json.load(fh)
        M = np.stack([cols[j].codes for j in keep], axis=1).astype(np.int32)
        problems = []
        if names != ref["attributes"]:
            problems.append(f"attributes {names} against {ref['attributes']}")
        if const != ref["dropped_constant_columns"]:
            problems.append(f"constant columns {const} against {ref['dropped_constant_columns']}")
        if M.shape[0] != ref["instance"]["rows"]:
            problems.append(f"records {M.shape[0]} against {ref['instance']['rows']}")
        for j, a in enumerate(names):
            k = len(np.unique(M[:, j]))
            if k != ref["distinct_values"][a]:
                problems.append(f"distinct values of {a}: {k} against {ref['distinct_values'][a]}")
        if problems:
            raise SystemExit(f"{ds}: the rebuilt instance differs from e3/data: " + "; ".join(problems))
        lens = {f"len{j}": np.array([len(str(v)) for v in cols[i].values], dtype=np.int32) for j, i in enumerate(keep)}
        null = np.array([any(str(v) == "?" for v in cols[i].values) for i in keep])
        np.savez_compressed(os.path.join(OUT, ds + ".npz"), names=np.array(names), M=M, null=null, **lens)
        print(f"{ds}: {M.shape[0]} records, {len(names)} attributes, {int(null.sum())} with '?', identical to e3/data", flush=True)


if __name__ == "__main__":
    main()
