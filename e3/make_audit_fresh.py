"""
The material of the blind audit of the confirmatory relations (design notes, component selection item 28;
truth/audit_fresh/AUDIT_TASK.md): sigma_current.json (attributes, construction and the Sigma* items of truth/fresh.json,
each with an id) and candidates.txt (per relation, the mined minimal FDs that Sigma* does not imply: all of them up to
CAP, otherwise CAP drawn with a fixed seed).  Reads data/<ds>.json, so it runs after build.py stage json.

Usage:  python make_audit_fresh.py [fresh|fresh2]   writes truth/audit_<batch>/sigma_current.json and candidates.txt
        (the second confirmatory batch of item 33 is truth/fresh2.json, audited into truth/audit_fresh2/)
"""
import json, os, random, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
BATCH = sys.argv[1] if len(sys.argv) > 1 else "fresh"
OUT = os.path.join(HERE, "truth", "audit_" + BATCH)
CAP = 200


def main():
    with open(os.path.join(HERE, "truth", BATCH + ".json"), encoding="utf-8") as fh:
        doc = json.load(fh)["datasets"]
    sigma, lines = {}, []
    for ds, e in doc.items():
        sigma[ds] = {"attributes": e["attributes"], "construction": e["construction"],
                     "items": [{"id": f"{ds}#{i}", **{k: t[k] for k in ("lhs", "rhs", "sure", "clause", "justification")
                                                      if k in t}} for i, t in enumerate(e["truth"])]}
        with open(os.path.join(HERE, "data", ds + ".json"), encoding="utf-8") as fh:
            d = json.load(fh)
        cands = sorted((sorted(f["lhs"]), f["rhs"]) for f in d["fds"] if not f["implied_by_truth"])
        pick = cands if len(cands) <= CAP else sorted(random.Random(zlib.crc32(ds.encode())).sample(cands, CAP))
        head = f"== {ds}: {len(cands)} candidates not implied by Sigma*"
        lines.append(head + (f", {CAP} drawn at random" if len(pick) < len(cands) else ""))
        lines += [f"   {','.join(l) if l else '{}'} -> {r}" for l, r in sorted(pick, key=lambda c: (len(c[0]), c))]
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "sigma_current.json"), "w", encoding="utf-8") as fh:
        json.dump(sigma, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "candidates.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(l for l in lines if l.startswith("==")))


if __name__ == "__main__":
    main()
