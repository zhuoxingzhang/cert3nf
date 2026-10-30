"""
Applies the blind audit of the confirmatory relations (truth/audit_fresh/audit_result_*.json) to truth/fresh.json, by
the rule of design notes, component selection item 28, written before the audit: a right-hand side that the
documentation contradicts (FALSE_DOC) is removed; a right-hand side of a sure=false item that it supports (TRUE)
becomes sure; a candidate judged TRUE is added as a sure item with the auditor's quote; UNDETERMINED changes nothing.
Every item keeps the audit verdicts of its right-hand sides under "audit".  The original file is kept as
truth/fresh_preaudit.json.

Usage:  python apply_audit_fresh.py [fresh|fresh2]   (item 33: truth/fresh2.json, truth/audit_fresh2/)
"""
import glob, json, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BATCH = sys.argv[1] if len(sys.argv) > 1 else "fresh"
TRUTH = os.path.join(HERE, "truth", BATCH + ".json")


def main():
    pre = os.path.join(HERE, "truth", BATCH + "_preaudit.json")
    if not os.path.exists(pre):
        shutil.copyfile(TRUTH, pre)
    with open(pre, encoding="utf-8") as fh:
        doc = json.load(fh)
    rel = {}
    for f in sorted(glob.glob(os.path.join(HERE, "truth", "audit_" + BATCH, "audit_result_*.json"))):
        with open(f, encoding="utf-8") as fh:
            rel.update(json.load(fh)["relations"])
    assert set(rel) == set(doc["datasets"]), sorted(set(doc["datasets"]) ^ set(rel))
    log = []
    for ds, e in doc["datasets"].items():
        verdict = {it["id"]: it for it in rel[ds]["sigma_items"]}
        out = []
        for i, t in enumerate(e["truth"]):
            v = verdict[f"{ds}#{i}"]
            per = {a: v.get("rhs_verdicts", {}).get(a, v["verdict"]) for a in t["rhs"]}
            keep = [a for a in t["rhs"] if per[a] != "FALSE_DOC"]
            gone = [a for a in t["rhs"] if per[a] == "FALSE_DOC"]
            if gone:
                log.append(f"{ds}#{i}: removed {t['lhs']} -> {gone}")
            up = [a for a in keep if not t["sure"] and per[a] == "TRUE"]
            rest = [a for a in keep if a not in up]
            note = {"verdicts": {a: per[a] for a in t["rhs"]}, "quote": v.get("quote", ""), "source": v.get("source", "")}
            if up:
                log.append(f"{ds}#{i}: sure now {t['lhs']} -> {up}")
                out.append({**t, "rhs": up, "sure": True, "audit": note})
            if rest:
                out.append({**t, "rhs": rest, "audit": note})
        added = [c for c in rel[ds]["candidates"] if c["verdict"] == "TRUE"]
        for c in added:
            out.append({"lhs": c["lhs"], "rhs": [c["rhs"]], "sure": True,
                        "clause": f"documentation-only audit: \"{c.get('quote', '')}\" ({c.get('source', '')})",
                        "justification": c.get("reason", ""), "audit": {"verdicts": {c["rhs"]: "TRUE"},
                                                                         "derived_from": c.get("derived_from", [])}})
            log.append(f"{ds}: added {c['lhs']} -> {c['rhs']}")
        e["truth"] = out
    doc["audit"] = (f"Blind documentation-only audit (truth/audit_{BATCH}/), applied by apply_audit_fresh.py; the file "
                    f"before it is truth/{BATCH}_preaudit.json")
    with open(TRUTH, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    print("\n".join(log) or "no change")


if __name__ == "__main__":
    main()
