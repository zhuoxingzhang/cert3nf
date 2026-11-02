# Cert3NF

[![Full version of the paper (PDF)](https://img.shields.io/badge/Full%20version%20of%20the%20paper-Cert3NF--full.pdf-b31b1b?style=for-the-badge)](Cert3NF-full.pdf)

> **Full version of the paper: [Cert3NF-full.pdf](Cert3NF-full.pdf)**, with all proofs (Appendix A) and the details of the experiments (Appendix B).

Code for *Confirming What Matters: Certified Third Normal Form Synthesis from Uncertain Functional Dependencies*.

Python 3.11 with numpy (`pip install -r requirements.txt`).
The LLM answers and the normalizer need vLLM and a GPU, and attribute exploration needs a C compiler.
The repository includes the mined relations and the results behind every table and figure, so the tables and reports regenerate without rerunning anything.
Raw data and LLM answers are not included; the scripts below download or recompute them.

## Layout

| path | content |
|---|---|
| `sensitivity_bruteforce.py`, `baselines.py` | single errors on random schemata (Table 1) |
| `e2/` | accidental FDs of TPC-H (Table 2) |
| `e3/` | the relations: downloads, mined candidates (`e3/data/`), ground truth (`e3/truth/`) |
| `confirm/v5.py` | Cert3NF and its ablations (Tables 3 and 9, Fig. 2) |
| `confirm/v5tol.py` | careful mode for a designer who errs: every premise asked twice (Table 6) |
| `confirm/v5tau.py` | tolerance θ for data that violate true FDs |
| `confirm/auto_confirm.py`, `confirm/auto_mars.py` | automatic methods and the posterior certificate (Table 4) |
| `confirm/ec2hyb.py` | the posterior certificate with the questions of EC² (Table 4, rule C6) |
| `confirm/aexp.c`, `confirm/aexp.py` | attribute exploration |
| `e3/scale.py`, `confirm/scale_run.py` | synthetic relations with up to a million candidates (Table 5, rules S1-S3) |
| `confirm/check_cert.py` | independent check of every certificate |
| `confirm/scripts/` | tables and reports |
| `confirm/v5_*/`, `confirm/v5tol_*/`, `confirm/paper_src/`, ... | results of the runs below |
| `study/`, `render.yaml` | the human-designer study: its web server, fixed question blocks and materials (`study/README.md`) |

## Reproduce

Damage of single errors:

```bash
python sensitivity_bruteforce.py 300 1     # Table 1, n <= 6
python sensitivity_bruteforce.py 150 3 7   # Table 1, n = 7
cd e2 && python e2_tpch.py                 # Table 2
```

Relations, in `e3/`: TPC-H and SSB come from dbgen (`python build.py <dir with the .tbl files>`), the confirmatory relations from the scripts in `e3/download/` and `unpack_fresh2.py`.
Each relation is then mined and written to `e3/data/`:

```bash
python build.py none --stage mine --only <relation>
python build.py none --stage json --only <relations>
python dump_samples.py none samples <relations>
```

LLM answers, in `confirm/`:

```bash
python auto_prompts.py prompts.jsonl --kinds expert,design,rules
python auto_llm.py --model Qwen/Qwen3.5-9B --prompts prompts.jsonl --out llm_fresh2_full_q35/answers_q35.jsonl \
    --kinds expert,design,rules --quantization fp8_per_block --max-tokens 16384
CONFIRM_TRUTH=full python auto_confirm.py rates --answers llm_fresh2_full_q35 --models q35
```

Experiments, in `confirm/`, with `CONFIRM_ORACLE=gold`, `CONFIRM_TRUTH=full` or `sure`, and `CONFIRM_BATCH=2` for the twelve confirmatory relations (unset for the development relations):

```bash
DS=$(python -c "import auto_common as AC; print(','.join(AC.FRESH))")
python v5.py --answers llm_fresh2_full_q35 --datasets $DS --out v5_fresh2/v5_full.jsonl                      # Table 3
python v5.py --answers llm_fresh2_full_q35 --datasets $DS --budget 1000 --variants v5,v5s,v5n --out v5_unb/v5_full.jsonl   # Fig. 2
python v5tol.py --answers llm_fresh2_full_q35 --datasets $DS --mech c [--rho 0.25] --out v5tol_fresh2/v5tol_full.jsonl   # Table 6
CODES_DIR=../e3/codes python v5tau.py --answers llm_fresh2_full_q35 --datasets $DS --thetas 0,0.001,0.01,0.1 --budget 1000 --out tau.jsonl
python auto_confirm.py run --answers llm_fresh2_full_q35 --models q35 --datasets $DS --variants rbhyb,rbhyb0,trust,clf,L1,A5,A9,upper,hyfd --out auto.jsonl   # Table 4
python ec2hyb.py run --answers llm_fresh2_full_q35 --models q35 --datasets $DS --variants ec2hyb,ec2hyb0 --out ec2_results/results_ec2_full.jsonl   # Table 4
python scripts/ec2_report.py > ec2_results/report.txt                                                          # rule C6
python auto_mars.py --model Qwen/Qwen3.5-9B --datasets $DS --out mars.jsonl                                  # normalizer
gcc -O2 -o aexp aexp.c && python aexp.py --out aexp_full.jsonl [--max]                                       # attribute exploration
python check_cert.py --results v5_fresh2/v5_full.jsonl --truth
PRICE_FILE=price_min.json python scripts/paper_tables_v5.py                                                  # Tables 3, 4, 6, 8 and 9
```

Synthetic relations (Table 5): `e3/scale.py` generates them deterministically and writes their ground truth to `e3/truth/scale.json`; their mined candidates (up to 2 GB per relation) are not included.
Mining stops after two hours per relation; the relations with 40 and 50 attributes have no runs, since they are not mined within that limit or their millions of candidates do not fit into 60 GB of memory.

```bash
cd e3 && python scale.py gen && python scale.py mine --only <relation> && python scale.py json --only <relation>
cd ../confirm   # with CONFIRM_TRUTH=full CONFIRM_ORACLE=gold CONFIRM_BATCH=2
python scale_run.py v5 --answers llm_fresh2_full_q35 --variants v5s,v5n --budget 1000 --workers 8 --out scale/v5.jsonl
python scale_run.py price --results scale/v5.jsonl --out scale/price.json
python scale_run.py check --results scale/v5.jsonl --out scale/check.jsonl
python scale_run.py report --results scale/v5.jsonl --price scale/price.json --check scale/check.jsonl > scale/report.txt   # S1-S3
```

`v5tau.py` reads the records that `python ../e3/dump_codes.py ../e3/codes $DS` encodes.
The price of Thm. 4.4 comes from `cover_bounds.py`, `price_min.py` and `price_sets.py`, and every other number of the paper from a report in `confirm/scripts/`.
