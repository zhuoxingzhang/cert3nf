"""
The instances of the named relations as integer codes, one column per attribute of data/<ds>.json (constant columns
dropped, as in the mining), for the violation shares g3 of design note item 43 (confirm/v5tau.py).  Built by
build.instances exactly as stage mine builds them, so FRESH_RAW and FRESH_NO_REPAIR apply.
Usage:  python dump_codes.py OUT_DIR ds1,ds2,...      writes OUT_DIR/<ds>.npy (rows x attributes, int32)
"""
import json, os, sys
import numpy as np
import build


def main():
    out, wanted = sys.argv[1], sys.argv[2].split(",")
    os.makedirs(out, exist_ok=True)
    for ds in wanted:                          # one at a time: the large instances need not coexist in memory
        with open(os.path.join(build.HERE, "data", ds + ".json"), encoding="utf-8") as fh:
            d = json.load(fh)
        inst = build.instances("none", [ds])[ds]
        pos = {a: j for j, a in enumerate(inst["attributes"])}
        X = np.stack([np.asarray(inst["cols"][pos[a]].codes, dtype=np.int32) for a in d["attributes"]], axis=1)
        assert X.shape[0] == d["instance"]["rows"], (ds, X.shape, d["instance"]["rows"])
        np.save(os.path.join(out, ds + ".npy"), X)
        print(ds, X.shape, flush=True)


if __name__ == "__main__":
    main()
