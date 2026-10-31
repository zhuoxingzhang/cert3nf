# Cert3NF

Code for *Confirming What Matters: Certified Third Normal Form Synthesis from Uncertain Functional Dependencies*.

Python 3.11 with numpy (`pip install -r requirements.txt`).
The LLM answers and the normalizer need vLLM and a GPU, and attribute exploration needs a C compiler.
The repository includes the mined relations and the results behind every table and figure, so the tables and reports regenerate without rerunning anything.
Raw data and LLM answers are not included; the scripts below download or recompute them.

## Layout

| path | content |
|---|---|
| `sensitivity_bruteforce.py`, `baselines.py` | single errors on random schemata (Table 2) |
| `e2/` | accidental FDs of TPC-H (Table 3) |
| `e3/` | the relations: downloads, mined candidates (`e3/data/`), ground truth (`e3/truth/`) |
| `confirm/v5.py` | Cert3NF and its ablations (Tables 4 and 7, Fig. 2) |
| `confirm/v5tol.py` | tolerant mode for a designer who errs (Table 6) |
| `confirm/v5tau.py` | tolerance θ for data that violate true FDs |
| `confirm/auto_confirm.py`, `confirm/auto_mars.py` | automatic methods and the posterior certificate (Table 5) |
| `confirm/aexp.c`, `confirm/aexp.py` | attribute exploration |
| `confirm/check_cert.py` | independent check of every certificate |
| `confirm/scripts/` | tables and reports |
| `confirm/v5_*/`, `confirm/v5tol_*/`, `confirm/paper_src/`, ... | results of the runs below |
| `study/`, `render.yaml` | the human-designer study: its web server, fixed question blocks and materials (`study/README.md`) |

## Reproduce

Damage of single errors:

```bash
python sensitivity_bruteforce.py 300 1     # Table 2, n <= 6
python sensitivity_bruteforce.py 150 3 7   # Table 2, n = 7
cd e2 && python e2_tpch.py                 # Table 3
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
python v5.py --answers llm_fresh2_full_q35 --datasets $DS --out v5_fresh2/v5_full.jsonl                      # Table 4
python v5.py --answers llm_fresh2_full_q35 --datasets $DS --budget 1000 --variants v5,v5s,v5n --out v5_unb/v5_full.jsonl   # Fig. 2
python v5tol.py --answers llm_fresh2_full_q35 --datasets $DS --mech c [--rho 0.25] --out v5tol_fresh2/v5tol_full.jsonl   # Table 6
CODES_DIR=../e3/codes python v5tau.py --answers llm_fresh2_full_q35 --datasets $DS --thetas 0,0.001,0.01,0.1 --budget 1000 --out tau.jsonl
python auto_confirm.py run --answers llm_fresh2_full_q35 --models q35 --datasets $DS --variants rbhyb,rbhyb0,trust,clf,L1,A5,A9,upper,hyfd --out auto.jsonl   # Table 5
python auto_mars.py --model Qwen/Qwen3.5-9B --datasets $DS --out mars.jsonl                                  # normalizer
gcc -O2 -o aexp aexp.c && python aexp.py --out aexp_full.jsonl [--max]                                       # attribute exploration
python check_cert.py --results v5_fresh2/v5_full.jsonl --truth
PRICE_FILE=price_min.json python scripts/paper_tables_v5.py                                                  # Tables 1 and 4-7
```

`v5tau.py` reads the records that `python ../e3/dump_codes.py ../e3/codes $DS` encodes.
The price of Thm. 4.4 comes from `cover_bounds.py`, `price_min.py` and `price_sets.py`, and every other number of the paper from a report in `confirm/scripts/`.
