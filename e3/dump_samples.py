"""
Sample rows of the benchmark instances for the prompts of the LLM expert (design notes, section 4).
Runs on the experiment server, where build.instances finds the TPC-H tables and the real data.

The sample is 10 rows drawn uniformly without replacement with a fixed seed, in instance order, over the attributes of
data/<ds>.json (constant columns dropped, as in the mining).  Ten rows show the formats and codes of the values; every
candidate holds on all rows, so more rows cannot refute one and would only lengthen the prompt.

Usage:  python dump_samples.py TBL_DIR OUT_DIR ds1,ds2,...      writes OUT_DIR/<ds>.json
"""
import json, os, sys
import numpy as np
import build

K, SEED = 10, 0


def main():
    tbl, out, wanted = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
    os.makedirs(out, exist_ok=True)
    for ds in wanted:                          # one at a time: the large instances need not coexist in memory
        inst = build.instances(tbl, [ds])[ds]
        cols, names = inst["cols"], inst["attributes"]
        keep = [j for j, c in enumerate(cols) if len(np.unique(c.codes)) > 1]
        n = len(cols[0].codes)
        idx = np.sort(np.random.default_rng(SEED).choice(n, size=min(K, n), replace=False))
        sample = [[str(cols[j].values[int(cols[j].codes[i])]) for j in keep] for i in idx]
        rec = {"dataset": ds, "rows": int(n), "attributes": [names[j] for j in keep], "seed": SEED,
               "row_indices": idx.tolist(), "sample": sample}
        with open(os.path.join(out, ds + ".json"), "w", encoding="utf-8") as fh:
            json.dump(rec, fh, ensure_ascii=False, indent=0)
        print(ds, n, "rows,", len(keep), "attributes", flush=True)


if __name__ == "__main__":
    main()
