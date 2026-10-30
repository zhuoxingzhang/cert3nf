"""
Prompts of the automated pipeline (design notes, sections 4 and 8), one JSON line each.

  expert        one prompt per candidate: is X -> A a rule of the domain?  The evidence is the attribute names, the
                declared key, the number of rows and ten sample rows (e3/samples, dump_samples.py).  No statistics:
                the prior uses them already, and the expert must add evidence the prior lacks.
  expert_names  the same without the sample rows (ablation A4: do the values help?), on a random sample of at most
                200 candidates per relation (seed fixed): the ablation compares the accuracy of the answers with and
                without rows, which a sample estimates to a few points, while all 44,231 would double the GPU time
  design        ablation L1: the model designs a 3NF schema directly from the same evidence, three runs
  rules         ablation A5: the model states the rules of the domain with probabilities (as llm_rules.py), from the
                same evidence, three elicitations averaged; the prior that double-counts the expert's beliefs

One prompt per candidate, never a batch: the answer to one candidate must not depend on which other candidates share
its prompt or in which order they appear.  No system prompt: DeepSeek-R1 asks for all instructions in the user turn.

Ablation K (no declared key): --no-key --kinds expert writes the expert prompts of every candidate with "Declared key:
none declared", the candidates including the minimal FDs that the key implies (auto_common.py).

Usage:  python auto_prompts.py OUT.jsonl [--no-key] [--kinds expert,expert_names,design,rules]
"""
import argparse, json, os, random, sys, zlib
import auto_common as AC

CUT = 60     # longer values are cut: free text beyond this length shows no more about the format of a value


def describe(b, sample, with_rows=True):
    key = ", ".join(b["key"]) if b["key"] else "none declared"
    lines = [f"The relation has {b['rows']:,} rows and these attributes:"]
    lines += [f"- {a}" for a in b["names"]]
    lines.append(f"Declared key: {key}")
    if with_rows:
        assert sample["attributes"] == b["names"], b["name"]
        cut = lambda v: v if len(v) <= CUT else v[:CUT] + "..."
        lines.append("")
        lines.append(f"Ten rows drawn at random from the relation (values longer than {CUT} characters are cut):")
        lines.append(" | ".join(b["names"]))
        lines += [" | ".join(cut(v) for v in row) for row in sample["sample"]]
    return "\n".join(lines)


def conj(xs):
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


EXPERT = """You are a database designer who knows the application domain of the following relation.

{relation}

The functional dependency {lhs} -> {rhs} holds on all {rows:,} rows: any two rows that agree on {agree} also agree on {rhs}.

Question: is {lhs} -> {rhs} a rule of the domain, so that every valid instance of this relation must satisfy it because of what the attributes mean? Or does it hold only by coincidence in this data?

Reason about the meaning of the attributes, then end your reply with exactly one line, either
ANSWER: YES
or
ANSWER: NO"""

DESIGN = """You are a database designer who knows the application domain of the following relation.

{relation}

Task: design a relational schema for this data in third normal form (3NF). Base the design on the functional dependencies (FDs) you believe are genuine rules of this relation's domain. A genuine rule holds in every valid instance because of what the attributes mean, not by coincidence in one sample.

The decomposition must be lossless and preserve every FD you believe is genuine, and it should use as few tables as that allows. Every attribute must appear in some table. Use the exact attribute names above.

End your reply with one JSON object of the form
{{"tables": [{{"attributes": ["A1", "A2", "B"], "key": ["A1"]}}], "fds": [{{"lhs": ["A1"], "rhs": "B"}}]}}
where "fds" lists the genuine FDs your design is based on."""

RULES = """You are a database designer who knows the application domain of the following relation.

{relation}

Task: state which functional dependencies (FDs) you believe are genuine rules of this relation's domain. A genuine rule holds in every valid instance because of what the attributes mean, not by coincidence in one sample.

Write each rule with a minimal left-hand side and a single attribute on the right, using the exact attribute names above. Give each rule your probability that it is genuine. Include rules you are unsure about with a lower probability, down to 0.05. Do not list FDs that follow from the declared key, and do not list trivial FDs.

Then give one base probability, "other": the chance that an FD over these attributes that does not follow from your rules and the declared key is nonetheless genuine. Be calibrated.

End your reply with one JSON object of the form
{{"rules": [{{"lhs": ["A1", "A2"], "rhs": "B", "p": 0.9}}], "other": 0.01}}"""

RUNS = ("a", "b", "c")
NAMES_SAMPLE = 200


def main(out, kinds=("expert", "expert_names", "design", "rules"), datasets=None):
    recs = []
    for ds in datasets or AC.DATASETS:
        b = AC.load(ds)
        with open(os.path.join(AC.SAMPLES, ds + ".json"), encoding="utf-8") as fh:
            sample = json.load(fh)
        rel = {True: describe(b, sample, True), False: describe(b, sample, False)}
        ids = sorted(AC.fd_id(ds, *b["fdnames"][p]) for p in b["P"])
        names_ids = set(random.Random(zlib.crc32(ds.encode())).sample(ids, min(NAMES_SAMPLE, len(ids))))
        for p in b["P"]:
            lhs, rhs = b["fdnames"][p]
            fid = AC.fd_id(ds, lhs, rhs)
            for kind, rows in (("expert", True), ("expert_names", False)):
                if kind == "expert_names" and fid not in names_ids:
                    continue
                recs.append({"id": f"{kind}|{fid}", "kind": kind, "dataset": ds, "lhs": lhs, "rhs": rhs,
                             "prompt": EXPERT.format(relation=rel[rows], lhs=", ".join(lhs), rhs=rhs,
                                                     rows=b["rows"], agree=conj(lhs))})
        for kind, tpl in (("design", DESIGN), ("rules", RULES)):
            for r in RUNS:
                recs.append({"id": f"{kind}|{ds}|{r}", "kind": kind, "dataset": ds, "run": r,
                             "prompt": tpl.format(relation=rel[True])})
    recs = [r for r in recs if r["kind"] in kinds]
    with open(out, "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    kinds = {}
    for r in recs:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print(out, kinds)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--no-key", action="store_true")
    ap.add_argument("--kinds", default="expert,expert_names,design,rules")
    ap.add_argument("--datasets", default=None, help="comma-separated; default the development relations "
                                                      "(the confirmatory ones: --datasets fresh)")
    a = ap.parse_args()
    if a.no_key:
        os.environ["CONFIRM_NO_KEY"] = "1"
    main(a.out, a.kinds.split(","),
         AC.FRESH if a.datasets == "fresh" else a.datasets.split(",") if a.datasets else None)
