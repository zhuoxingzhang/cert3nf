"""
Answer the prompts of auto_prompts.py with an open-weight model through vLLM (design notes, section 4).

Models and settings, pinned:
  deepseek-ai/DeepSeek-R1-Distill-Llama-70B   temperature 0.6, top-p 0.95 (model card: this range prevents endless
                                              repetition; no system prompt)
  Qwen/Qwen3-30B-A3B-Thinking-2507            temperature 0.6, top-p 0.95, top-k 20, min-p 0 (model card)
  Qwen/Qwen3.5-9B                             temperature 1.0, top-p 0.95, top-k 20, min-p 0, presence penalty 1.5
                                              (model card, thinking mode for general tasks; thinking is its default);
                                              text only, so vLLM does not load its vision encoder
  openai/gpt-oss-20b                          temperature 1.0, top-p 1.0 (model card), reasoning effort medium (the
                                              default of its chat template); the second expert from another family
                                              (design note, component selection item 18).  Its replies use the harmony format: the
                                              reasoning goes to the analysis channel and the reply to the final channel,
                                              whose markers are special tokens, so they are kept in the text; its chat
                                              template writes the current date into the system message, which is
                                              fixed to the day of the run's start so that a prompt does not depend
                                              on the day it is answered
The revisions are the commits on the Hugging Face Hub, read with HfApi().model_info on 2026-10-17 (Qwen3.5-9B:
2026-10-20; gpt-oss-20b: 2026-10-22).
Every request has its own seed (crc32 of its id), so an answer does not depend on the batch it ran in, up to the
numerics of batched kernels.  Each question is answered once; Confirm reads the recorded answer whenever it asks.
max_tokens caps the computation below the 32,768 of the model cards; truncated answers are recorded as such.

The output is appended in chunks, and a rerun skips the ids already answered, so the job can be resumed.
vLLM loads the model from the cached snapshot of the pinned revision (local_snapshot), not from the repository id.
It takes 90% of each GPU's memory, or less when other processes on the shared node hold memory there (gpu_share).
Its MoE kernels come from a patched copy when the wheel's library does not load on the server's glibc (load_moe_ops).

--shard K/N answers the prompts whose crc32(id) mod N is K, so that N machines share one run; their outputs are
concatenated afterwards.

Usage:  python auto_llm.py --model M --prompts P.jsonl --out A.jsonl [--kinds expert,design] [--tp 2] [--max-tokens 8192]
                           [--shard K/N]
"""
import argparse, ast, json, math, os, re, subprocess, sys, time, zlib

MODELS = {
    "deepseek-ai/DeepSeek-R1-Distill-Llama-70B": {
        "revision": "b1c0b44b4369b597ad119a196caf79a9c40e141e", "tp": 2,
        "sampling": dict(temperature=0.6, top_p=0.95)},
    "Qwen/Qwen3-30B-A3B-Thinking-2507": {
        "revision": "144afc2f379b542fdd4e85a1fcd5e1f79112d95d", "tp": 1,
        "sampling": dict(temperature=0.6, top_p=0.95, top_k=20, min_p=0.0)},
    "Qwen/Qwen3.5-9B": {
        "revision": "c202236235762e1c871ad0ccb60c8ee5ba337b9a", "tp": 1,
        "sampling": dict(temperature=1.0, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=1.5,
                         repetition_penalty=1.0),
        "engine": dict(language_model_only=True)},     # no image or video limit, so the vision tower is not loaded
    "openai/gpt-oss-20b": {
        "revision": "6cee5e81ee83917806bbde320786a8fb61efebee", "tp": 1,
        "sampling": dict(temperature=1.0, top_p=1.0),
        "decode": dict(skip_special_tokens=False),
        "chat": dict(reasoning_effort="medium"), "template_date": "2026-10-22"},
}
FINAL = "<|channel|>final<|message|>"      # harmony: the start of the reply in the final channel
ANSWER = re.compile(r"ANSWER:\s*\**\s*(YES|NO)\b", re.I)


def final_part(text):
    """the reply after the reasoning: what follows the last </think>, or the last final-channel marker of a harmony
    reply (none if a harmony reply has no final channel), or everything if there is neither"""
    i = text.rfind(FINAL)
    if i >= 0:
        return text[i + len(FINAL):]
    if "<|channel|>" in text:
        return ""
    i = text.rfind("</think>")
    return text[i + len("</think>"):] if i >= 0 else text


def parse(kind, text, finish):
    """the answer of a finished reply, or None; a reply cut at max_tokens has none (design note, section 4), even when
    an "ANSWER:" line occurs inside its unfinished reasoning"""
    if finish == "length":
        return None
    tail = final_part(text)
    if kind.startswith("expert"):
        m = ANSWER.findall(tail)
        return (m[-1].upper() == "YES") if m else None
    j = tail.rfind("}")
    while j >= 0:                                   # the last balanced JSON object in the reply
        depth, i = 0, j
        while i >= 0:
            depth += {"}": 1, "{": -1}.get(tail[i], 0)
            if depth == 0:
                try:
                    return json.loads(tail[i:j + 1])
                except ValueError:
                    break
            i -= 1
        j = tail.rfind("}", 0, j)
    return None


TOPK = 5        # log-probabilities per generated token that vLLM returns for the expert prompts


def _word(lp):
    return (lp.decoded_token or "").strip().strip("*").upper()


def answer_prob(g):
    """The model's own probability of its final answer: at the last generated token that reads YES or NO with ANSWER
    among the six tokens before it, P(YES) / (P(YES) + P(NO)) from the top-TOPK log-probabilities of that position
    (raw model distribution).  A binary answer discards how sure the model was; this keeps it at no extra call.
    Returns {"p_yes", "lp_yes", "lp_no"} (a log-probability outside the top TOPK is None), or None."""
    try:
        lps, ids = g.logprobs, list(g.token_ids)
        if not lps:
            return None
        for i in range(len(ids) - 1, -1, -1):
            d = lps[i]
            if ids[i] not in d or _word(d[ids[i]]) not in ("YES", "NO"):
                continue
            ctx = "".join(lps[j][ids[j]].decoded_token or "" for j in range(max(0, i - 6), i) if ids[j] in lps[j])
            if "ANSWER" not in ctx.upper():
                continue
            ly = max((e.logprob for e in d.values() if _word(e) == "YES"), default=None)
            ln = max((e.logprob for e in d.values() if _word(e) == "NO"), default=None)
            py = math.exp(ly) if ly is not None else 0.0
            pn = math.exp(ln) if ln is not None else 0.0
            return {"p_yes": py / (py + pn) if py + pn > 0 else None, "lp_yes": ly, "lp_no": ln}
    except Exception as e:                       # never lose an answer over its confidence
        return {"error": f"{type(e).__name__}: {e}"[:200]}
    return None


def local_snapshot(model, revision):
    """The directory of the pinned revision in the Hugging Face cache.  Given a repository id, vLLM calls
    snapshot_download, which in offline mode (huggingface_hub 2.2) refuses a cached snapshot that lacks the repository's
    .gitattributes and LICENSE, files that setup_llm.sh does not download; job 24902 failed so.  The weights are the
    same either way."""
    hub = os.environ.get("HF_HUB_CACHE") or os.path.join(
        os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface")), "hub")
    path = os.path.join(hub, "models--" + model.replace("/", "--"), "snapshots", revision)
    if not os.path.isfile(os.path.join(path, "config.json")):
        sys.exit(f"no cached snapshot of {model} at revision {revision}: {path}")
    return path


def load_moe_ops():
    """vLLM's MoE kernels (the library _moe_C) from the copy that MOE_C_PATCHED names, when the wheel's library does not
    load here: it asks for glibc 2.29 where the server has 2.28, and vLLM skips an extension that fails to load without
    a message, so job 24925 failed at the first MoE layer of the model.  The copy differs in that one version
    requirement (slurm/patch_moe_glibc.sh).  Called on import, so that vLLM's engine process has the kernels too,
    whether it is forked or spawned (a spawned process imports this module again)."""
    path = os.environ.get("MOE_C_PATCHED")
    if not path:
        return
    import torch
    try:
        import vllm._moe_C  # noqa: F401
    except ImportError:
        torch.ops.load_library(path)


load_moe_ops()


GPU_SHARE = 0.90    # the share of each GPU's memory that vLLM takes for the weights, activations and KV cache


def gpu_share(tp, cap=GPU_SHARE):
    """cap (GPU_SHARE), or less when other processes hold memory on the GPUs of the job: the node's GPUs are shared, and
    vLLM refuses to start when less than its share of a GPU's memory is free.  The free memory is read in a child
    process, so that this process does not initialise CUDA before vLLM does, and 1 GiB is left as a margin.  A smaller
    share only shrinks the KV cache, hence the batch, not the answers.  Falls back to cap if the reading fails.
    A smoke test run outside SLURM on a card that another job holds passes a smaller cap."""
    code = f"import torch; print([torch.cuda.mem_get_info(i) for i in range({tp})])"
    try:
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=600, check=True)
        info = ast.literal_eval(out.stdout.strip().splitlines()[-1])
        share = min((free - 2 ** 30) / total for free, total in info)
    except Exception as e:
        print(f"free GPU memory not read ({type(e).__name__}); share {cap}", flush=True)
        return cap
    share = min(cap, math.floor(share * 1000) / 1000)
    print("free/total GiB per GPU:", [(round(f / 2 ** 30, 1), round(t / 2 ** 30, 1)) for f, t in info],
          "-> share", share, flush=True)
    return share


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=sorted(MODELS))
    ap.add_argument("--prompts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--kinds", default="expert,expert_names,design,rules")
    ap.add_argument("--tp", type=int, default=None)
    ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--chunk", type=int, default=512)
    ap.add_argument("--limit", type=int, default=0, help="answer at most this many prompts (for a smoke test)")
    ap.add_argument("--max-share", type=float, default=GPU_SHARE, help="cap on the share of GPU memory (gpu_share)")
    ap.add_argument("--shard", default="0/1", help="K/N: the prompts whose crc32(id) mod N is K")
    ap.add_argument("--max-seqs", type=int, default=None,
                    help="cap on the sequences decoded at once (vLLM max_num_seqs); on a 24 GB card the default "
                         "reserves the recurrent state of Qwen3.5's linear-attention layers for more than fit")
    ap.add_argument("--quantization", default=None,
                    help="vLLM quantization applied to the official weights at load time, e.g. fp8 (recorded with "
                         "every answer)")
    a = ap.parse_args()
    k, n = map(int, a.shard.split("/"))
    cfg = MODELS[a.model]
    kinds = set(a.kinds.split(","))
    done = set()
    if os.path.exists(a.out):
        with open(a.out, encoding="utf-8") as fh:
            done = {json.loads(line)["id"] for line in fh if line.strip()}
    todo = []
    with open(a.prompts, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r["kind"] in kinds and r["id"] not in done and zlib.crc32(r["id"].encode()) % n == k:
                todo.append(r)
    order = a.kinds.split(",")
    todo.sort(key=lambda r: order.index(r["kind"]))     # the kinds in the order given, so the main ones finish first
    if a.limit:
        todo = todo[:a.limit]
    print(f"{len(todo)} prompts to answer, {len(done)} already done", flush=True)
    if not todo:
        return
    tp = a.tp or cfg["tp"]
    share = gpu_share(tp, a.max_share)
    from vllm import LLM, SamplingParams
    llm = LLM(model=local_snapshot(a.model, cfg["revision"]), tensor_parallel_size=tp,
              max_model_len=a.max_tokens + 4096, gpu_memory_utilization=share, seed=0, trust_remote_code=False,
              **cfg.get("engine", {}), **({"max_num_seqs": a.max_seqs} if a.max_seqs else {}),
              **({"quantization": a.quantization} if a.quantization else {}))
    chat = dict(chat_template_kwargs=cfg["chat"]) if "chat" in cfg else {}
    if "template_date" in cfg:
        with open(os.path.join(local_snapshot(a.model, cfg["revision"]), "chat_template.jinja"), encoding="utf-8") as fh:
            tpl = fh.read()
        assert tpl.count('strftime_now("%Y-%m-%d")') == 1
        chat["chat_template"] = tpl.replace('strftime_now("%Y-%m-%d")', '"%s"' % cfg["template_date"])
    for c in range(0, len(todo), a.chunk):
        part = todo[c:c + a.chunk]
        msgs = [[{"role": "user", "content": r["prompt"]}] for r in part]
        sps = [SamplingParams(max_tokens=a.max_tokens, seed=zlib.crc32(r["id"].encode()),
                              logprobs=TOPK if r["kind"].startswith("expert") else None, **cfg["sampling"],
                              **cfg.get("decode", {}))
               for r in part]
        t0 = time.time()
        outs = llm.chat(msgs, sps, use_tqdm=False, **chat)
        secs = time.time() - t0
        with open(a.out, "a", encoding="utf-8") as fh:
            for r, o in zip(part, outs):
                g = o.outputs[0]
                fh.write(json.dumps({"id": r["id"], "kind": r["kind"], "dataset": r["dataset"], "model": a.model,
                                     "revision": cfg["revision"], "quantization": a.quantization,
                                     "sampling": cfg["sampling"], "chat": cfg.get("chat"),
                                     "template_date": cfg.get("template_date"),
                                     "max_tokens": a.max_tokens, "seed": zlib.crc32(r["id"].encode()),
                                     "finish": g.finish_reason, "prompt_tokens": len(o.prompt_token_ids),
                                     "output_tokens": len(g.token_ids), "text": g.text,
                                     "answer": parse(r["kind"], g.text, g.finish_reason),
                                     "confidence": answer_prob(g) if r["kind"].startswith("expert")
                                     and g.finish_reason != "length" else None},
                                    ensure_ascii=False) + "\n")
        print(f"{c + len(part)}/{len(todo)} answered, chunk {secs:.0f}s", flush=True)


if __name__ == "__main__":
    main()
