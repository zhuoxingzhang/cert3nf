"""
Baseline L3 (design notes, section 8): a multi-agent LLM normalizer after MARS (Koh et al., "Can LLMs
Normalize Databases?", arXiv 2609.11141, 2026), the strongest published way of letting the model design the schema
itself.  MARS runs on the same model, Qwen3-30B-A3B, and reads the schema with sample rows, as our expert does.
The model, its sampling settings and the evidence (auto_prompts.describe: names, declared key, number of rows, ten
sample rows) are those of the expert prompts, so the comparison changes the method only.

MARS publishes neither code nor prompts (its artifacts are to be released on acceptance), so the agents follow its
description:
  evidence    infers the FDs of the relation from the schema and the sample rows, each labelled reliable,
              hypothetical or rejected ("semantics over statistics")
  diagnosis   names the normal-form violations and the FDs responsible, preferring reliable FDs, and plans the
              decomposition into target tables
  generator   emits the schema of the plan: tables with primary and foreign keys
  verifier    deterministic checks of the schema: every attribute kept and none invented, keys and foreign keys
              valid, every table in the normal form and the join lossless under the reliable FDs
  repair      at most two rounds (three schemata in all): errors of construction go back to the generator alone,
              errors of the decomposition (normal form, lossless join) to the diagnosis and then the generator,
              errors of foreign keys to the evidence agent and then the generator; each agent that runs again sees
              the verifier's findings
Three departures, each so that L3 solves our task and is judged like L1:
  - the target is the 3NF of our task (lossless, preserving the dependencies, fewest tables), where MARS aims at
    BCNF; so the verifier also checks that the reliable FDs are preserved, the 3NF counterpart of the BCNF check;
  - the generator emits the schema as JSON instead of SQL DDL, with the same content, so that parsing is no source
    of error;
  - every reply ends with a JSON object, parsed as the design kind of auto_llm.py (the last balanced object after
    the reasoning).
A run that never yields a schema has no design (judged not good, as L1).  Its FDs, for precision and recall, are the
reliable ones of the last evidence.

Three runs per relation (a, b, c).  Every call has its own seed (crc32 of the run, the agent and the attempt).  All
runs advance together: each step sends the next call of every unfinished run in one batch.
Output: one JSON line per run with every call (agent, attempt, prompt, reply, parse, verifier findings) and the
final schema; auto_confirm.py evaluates it as variant L3 (answers directory, mars_<short>.jsonl).

Usage:  python auto_mars.py --model M --out DIR/mars_qwen.jsonl [--datasets ...] [--runs a,b,c] [--max-tokens 8192]
                            [--max-share 0.9] [--fake]
--fake answers every call with a stub drawn from the mined FDs, to test the agents, the verifier and the repairs
without a GPU.
"""
import argparse, json, os, random, sys, time, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auto_common as AC
import auto_llm as AL
import baseline_direct as BD
from auto_prompts import describe

S = AC.S
MAX_SCHEMATA = 3                                  # one schema and at most two repairs, as MARS

EVIDENCE = """You are the evidence agent of a team that normalizes relational schemata. You know the application domain of the following relation.

{relation}

Task: infer the functional dependencies (FDs) of this relation from the attribute names and the sample rows. Prefer semantics over statistics: a genuine FD holds in every valid instance because of what the attributes mean, not by coincidence in a sample. Label every FD you consider:
- "reliable": a genuine rule of the domain;
- "hypothetical": plausible, but you are not sure it is a rule of the domain;
- "rejected": it holds in the sample rows only by coincidence.
Write each FD with a minimal left-hand side and a single attribute on the right, using the exact attribute names above. Do not list trivial FDs or FDs that follow from the declared key.{feedback}

End your reply with one JSON object of the form
{{"fds": [{{"lhs": ["A1"], "rhs": "B", "label": "reliable"}}]}}"""

DIAGNOSIS = """You are the diagnosis agent of a team that normalizes relational schemata into third normal form (3NF).

{relation}

The evidence agent inferred these functional dependencies (FDs) of the relation:
{fds}

Task: identify which normal forms the relation, stored as a single table, violates, and which FDs are responsible, preferring reliable FDs over hypothetical ones. Then plan a decomposition into 3NF that is lossless, preserves every reliable FD, and uses as few tables as that allows: list the target tables in the order you would create them, each with its attributes and primary key. Every attribute must appear in some table. Use the exact attribute names above.{feedback}

End your reply with one JSON object of the form
{{"violations": [{{"normal_form": "3NF", "lhs": ["A1"], "rhs": "B"}}], "plan": [{{"table": "T1", "attributes": ["A1", "B"], "key": ["A1"]}}]}}"""

GENERATOR = """You are the schema generator of a team that normalizes relational schemata into third normal form (3NF).

{relation}

The evidence agent inferred these functional dependencies (FDs) of the relation:
{fds}

The diagnosis agent planned this decomposition:
{plan}

Task: emit the normalized schema of the planned decomposition: every table with its attributes, its primary key and its foreign keys. Every attribute of the relation must appear in some table. Use the exact attribute names above.{feedback}

End your reply with one JSON object of the form
{{"tables": [{{"name": "T1", "attributes": ["A1", "B"], "key": ["A1"], "foreign_keys": [{{"attributes": ["B"], "references": "T2"}}]}}]}}"""

FEEDBACK = "\n\nThe verifier rejected the previous schema of the team:\n{}\nTake these findings into account."


def show_fds(fds):
    by = {lab: [f"{', '.join(g['lhs'])} -> {g['rhs']}" for g in fds if g["label"] == lab]
          for lab in ("reliable", "hypothetical")}
    return "\n".join(f"{lab.capitalize()}: " + ("; ".join(v) if v else "none") for lab, v in by.items())


def show_plan(plan):
    return "\n".join(f"{t['table']}({', '.join(t['attributes'])}) with primary key ({', '.join(t['key'])})"
                     for t in plan) or "none"


def names_of(x):
    """a list of attribute names from a reply: a list as it is, a single name as a list of one, anything else empty"""
    return [str(a) for a in x] if isinstance(x, list) else [x] if isinstance(x, str) else []


def items(parsed, field):
    v = parsed.get(field) if isinstance(parsed, dict) else None
    return [g for g in v if isinstance(g, dict)] if isinstance(v, list) else []


def clean_fds(parsed, names):
    """the well-formed FDs of an evidence reply over known attributes, deduplicated (the first label wins)"""
    out, seen = [], set()
    for g in items(parsed, "fds"):
        lhs, rhs, lab = sorted(set(names_of(g.get("lhs")))), g.get("rhs"), str(g.get("label", "")).lower()
        if not isinstance(rhs, str) or not lhs or rhs in lhs or rhs not in names or any(a not in names for a in lhs) \
                or lab not in ("reliable", "hypothetical", "rejected") or (tuple(lhs), rhs) in seen:
            continue
        seen.add((tuple(lhs), rhs))
        out.append({"lhs": lhs, "rhs": rhs, "label": lab})
    return out


def clean_plan(parsed):
    return [{"table": str(t.get("table", f"T{i + 1}")), "attributes": names_of(t.get("attributes")),
             "key": names_of(t.get("key"))} for i, t in enumerate(items(parsed, "plan")) if names_of(t.get("attributes"))]


def verify(b, tables, fds):
    """the verifier: findings per class (construction, foreign_keys, decomposition), checked against the declared key
    and the reliable FDs, the only FDs the team commits to"""
    names, idx = b["names"], {a: i for i, a in enumerate(b["names"])}
    find = {"construction": [], "foreign_keys": [], "decomposition": []}
    if not isinstance(tables, list) or not tables:
        find["construction"].append("no schema could be read from the reply (a JSON object with a list \"tables\")")
        return find, None
    D, keys, seen = [], {}, set()
    for i, t in enumerate(tables):
        if not isinstance(t, dict) or not names_of(t.get("attributes")):
            find["construction"].append(f"table {i + 1} has no list of attributes")
            continue
        nm = str(t.get("name", f"T{i + 1}"))
        if nm in seen:
            find["construction"].append(f"the table name {nm} is used twice")
        seen.add(nm)
        attrs = names_of(t["attributes"])
        unknown = [a for a in attrs if a not in idx]
        if unknown:
            find["construction"].append(f"table {nm} has attributes that the relation does not have: {', '.join(unknown)}")
        key = names_of(t.get("key"))
        if not key or any(a not in attrs for a in key):
            find["construction"].append(f"the primary key of table {nm} is missing or not among its attributes")
        keys[nm] = (set(attrs), set(key))
        D.append(frozenset(idx[a] for a in attrs if a in idx))
    missing = [a for a in names if not any(idx[a] in s for s in D)]
    if missing:
        find["construction"].append(f"attributes in no table: {', '.join(missing)}")
    for t in tables:
        if not isinstance(t, dict):
            continue
        nm = str(t.get("name", ""))
        for fk in t.get("foreign_keys") if isinstance(t.get("foreign_keys"), list) else []:
            cols, ref = names_of(fk.get("attributes")) if isinstance(fk, dict) else [],                 fk.get("references") if isinstance(fk, dict) else None
            if not cols or not isinstance(ref, str):
                find["foreign_keys"].append(f"a foreign key of table {nm} is malformed")
                continue
            if ref not in keys:
                find["foreign_keys"].append(f"a foreign key of table {nm} references the unknown table {ref}")
            elif nm in keys and not set(cols) <= keys[nm][0]:
                find["foreign_keys"].append(f"the foreign key ({', '.join(cols)}) is not among the attributes of {nm}")
            elif set(cols) != keys[ref][1]:
                find["foreign_keys"].append(f"the foreign key ({', '.join(cols)}) of {nm} is not the primary key of {ref}")
    D = [s for s in dict.fromkeys(D) if s and not any(s < u for u in D)]
    if find["construction"] or not D:
        return find, D or None
    F = b["sigma0"] + [S.fd([idx[a] for a in g["lhs"]], idx[g["rhs"]]) for g in fds if g["label"] == "reliable"]
    sa = BD.E2.atomic_closure(b["R"], F)                       # as auto_confirm.judge
    m = S.metrics(b["R"], [list(s) for s in D], sa, sa)
    if not m["lossless"]:
        find["decomposition"].append("the join of the tables is lossy under the reliable FDs and the declared key")
    if m["u_str"]:
        local = [f for s in D for f in S.proj(sa, s)]
        lost = [f for f in sa if not S.implies(local, f)]
        find["decomposition"].append("these reliable FDs are preserved by no table: " + "; ".join(
            ",".join(names[x] for x in sorted(f[0])) + " -> " + names[next(iter(f[1]))] for f in lost[:8]))
    for s in D:
        if not S.is_3nf(s, S.proj(sa, s)):
            find["decomposition"].append("the table (" + ", ".join(names[x] for x in sorted(s)) + ") is not in 3NF")
    return find, D


class Run:
    """one run of the agents on one relation: next_call() gives the next prompt, take() advances on its reply"""

    def __init__(self, b, sample, run):
        self.b, self.run, self.rel = b, run, describe(b, sample, True)
        self.calls, self.fds, self.plan, self.tables, self.design = [], [], [], None, None
        self.schemata, self.todo, self.feedback, self.done = 0, ["evidence", "diagnosis", "generator"], "", False

    def next_call(self):
        agent = self.todo[0]
        fb = FEEDBACK.format(self.feedback) if self.feedback else ""
        if agent == "evidence":
            prompt = EVIDENCE.format(relation=self.rel, feedback=fb)
        elif agent == "diagnosis":
            prompt = DIAGNOSIS.format(relation=self.rel, fds=show_fds(self.fds), feedback=fb)
        else:
            prompt = GENERATOR.format(relation=self.rel, fds=show_fds(self.fds), plan=show_plan(self.plan), feedback=fb)
        attempt = sum(1 for c in self.calls if c["agent"] == agent)
        seed = zlib.crc32(f"mars|{self.b['name']}|{self.run}|{agent}|{attempt}".encode())
        return agent, attempt, prompt, seed

    def take(self, agent, attempt, prompt, seed, text, finish, ptok, otok):
        parsed = AL.parse("design", text, finish)
        rec = {"agent": agent, "attempt": attempt, "seed": seed, "finish": finish, "prompt_tokens": ptok,
               "output_tokens": otok, "prompt": prompt, "text": text, "parsed": parsed}
        self.calls.append(rec)
        self.todo.pop(0)
        if agent == "evidence":
            self.fds = clean_fds(parsed, set(self.b["names"]))
        elif agent == "diagnosis":
            self.plan = clean_plan(parsed)
        else:
            self.schemata += 1
            tables = items(parsed, "tables") or None
            try:
                find, D = verify(self.b, tables, self.fds)
            except Exception as e:                  # an unforeseen reply never stops the other runs
                find, D = {"construction": [f"the schema could not be checked ({type(e).__name__})"],
                           "foreign_keys": [], "decomposition": []}, None
            rec["verifier"] = find
            if tables is not None and D:
                self.tables = [{"name": str(t.get("name", "")), "attributes": names_of(t.get("attributes")),
                                "key": names_of(t.get("key"))} for t in tables]
                self.design = D
            bad = [k for k, v in find.items() if v]
            if not bad or self.schemata >= MAX_SCHEMATA:
                self.done = True
                return
            self.feedback = "\n".join("- " + x for k in bad for x in find[k])
            # the earliest agent implicated runs again, and every later one after it
            self.todo = (["evidence", "diagnosis", "generator"] if "foreign_keys" in bad and "decomposition" in bad
                         else ["evidence", "generator"] if "foreign_keys" in bad
                         else ["diagnosis", "generator"] if "decomposition" in bad else ["generator"])

    def record(self, model):
        return {"id": f"mars|{self.b['name']}|{self.run}", "kind": "mars", "dataset": self.b["name"], "run": self.run,
                "model": model, "verified": bool(self.calls and not any(self.calls[-1].get("verifier", {}).values())),
                "schemata": self.schemata, "tables": self.tables, "fds": self.fds, "plan": self.plan,
                "calls": self.calls}


def fake_reply(b, agent, prompt, seed):
    """a stub answer for --fake: mined FDs as evidence, one table per left-hand side as the plan"""
    rnd, names = random.Random(seed), b["names"]
    nm = lambda p: (sorted(names[x] for x in p[0]), names[next(iter(p[1]))])
    if agent == "evidence":
        ps = rnd.sample(b["P"], min(6, len(b["P"])))
        fds = [{"lhs": nm(p)[0], "rhs": nm(p)[1], "label": rnd.choice(["reliable", "hypothetical", "rejected"])}
               for p in ps]
        return "<think>stub</think>\n" + json.dumps({"fds": fds})
    rel = rnd.sample(b["P"], min(3, len(b["P"])))      # mined candidates, never the ground truth, even in the stub
    tabs, used = [], set()
    for i, p in enumerate(rel):
        l, r = nm(p)
        tabs.append({"table": f"T{i + 1}", "name": f"T{i + 1}", "attributes": l + [r], "key": l})
        used |= set(l + [r])
    rest = [a for a in names if a not in used]
    key = [names[x] for x in sorted(b["sigma0"][0][0])] if b["sigma0"] else names[:1]
    tabs.append({"table": "T0", "name": "T0", "attributes": sorted(set(rest) | set(key)), "key": key})
    if rnd.random() < 0.3:                                      # sometimes a construction error, to test repairs
        tabs[0]["attributes"].append("no_such_attribute")
    if agent == "diagnosis":
        return "<think>stub</think>\n" + json.dumps({"violations": [], "plan": tabs})
    return "<think>stub</think>\n" + json.dumps({"tables": [{"name": t["name"], "attributes": t["attributes"],
                                                            "key": t["key"], "foreign_keys": []} for t in tabs]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=sorted(AL.MODELS))
    ap.add_argument("--out", required=True)
    ap.add_argument("--datasets", default=",".join(AC.DATASETS))
    ap.add_argument("--runs", default="a,b,c")
    ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--max-share", type=float, default=AL.GPU_SHARE)
    ap.add_argument("--max-seqs", type=int, default=None, help="vLLM max_num_seqs, as auto_llm.py")
    ap.add_argument("--quantization", default=None,
                    help="vLLM quantization applied to the official weights at load time, as auto_llm.py (recorded)")
    ap.add_argument("--fake", action="store_true")
    a = ap.parse_args()
    cfg = AL.MODELS[a.model]
    done = set()
    if os.path.exists(a.out):
        with open(a.out, encoding="utf-8") as fh:
            done = {json.loads(line)["id"] for line in fh if line.strip()}
    runs = []
    for ds in a.datasets.split(","):
        b = AC.load(ds)
        with open(os.path.join(AC.SAMPLES, ds + ".json"), encoding="utf-8") as fh:
            sample = json.load(fh)
        runs += [Run(b, sample, r) for r in a.runs.split(",") if f"mars|{ds}|{r}" not in done]
    print(f"{len(runs)} runs to do, {len(done)} already done", flush=True)
    if not runs:
        return
    llm = None
    if not a.fake:
        share = AL.gpu_share(1, a.max_share)
        from vllm import LLM, SamplingParams
        llm = LLM(model=AL.local_snapshot(a.model, cfg["revision"]), tensor_parallel_size=cfg["tp"],
                  max_model_len=a.max_tokens + 4096, gpu_memory_utilization=share, seed=0, trust_remote_code=False,
                  **cfg.get("engine", {}), **({"max_num_seqs": a.max_seqs} if a.max_seqs else {}),
                  **({"quantization": a.quantization} if a.quantization else {}))
    step = 0
    while any(not r.done for r in runs):
        live = [r for r in runs if not r.done]
        calls = [r.next_call() for r in live]
        t0 = time.time()
        if a.fake:
            outs = [(fake_reply(r.b, c[0], c[2], c[3]), "stop", 0, 0) for r, c in zip(live, calls)]
        else:
            sps = [SamplingParams(max_tokens=a.max_tokens, seed=c[3], **cfg["sampling"]) for c in calls]
            res = llm.chat([[{"role": "user", "content": c[2]}] for c in calls], sps, use_tqdm=False)
            outs = [(o.outputs[0].text, o.outputs[0].finish_reason, len(o.prompt_token_ids), len(o.outputs[0].token_ids))
                    for o in res]
        for r, c, o in zip(live, calls, outs):
            r.take(*c, *o)
        step += 1
        print(f"step {step}: {len(live)} calls ({', '.join(sorted({c[0] for c in calls}))}), {time.time() - t0:.0f}s, "
              f"{sum(r.done for r in runs)}/{len(runs)} runs done", flush=True)
        with open(a.out, "a", encoding="utf-8") as fh:            # finished runs are written as they finish
            for r in live:
                if r.done:
                    fh.write(json.dumps({**r.record(a.model), "quantization": a.quantization,
                                         "max_tokens": a.max_tokens}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
