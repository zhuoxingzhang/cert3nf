# Cert3NF

[![Full version of the paper (PDF)](https://img.shields.io/badge/Full%20version%20of%20the%20paper-Cert3NF--full.pdf-b31b1b?style=for-the-badge)](Cert3NF-full.pdf)
[![Live demo](https://img.shields.io/badge/Live%20demo-cert3nf.onrender.com-2ea44f?style=for-the-badge)](https://cert3nf.onrender.com)

> **Full version of the paper: [Cert3NF-full.pdf](Cert3NF-full.pdf)**, with all proofs (Appendix A) and the details of the experiments (Appendix B).
>
> **Live demo: [cert3nf.onrender.com](https://cert3nf.onrender.com)**, the web app of the human-designer study (`study/`). *Try it* on the start page opens a session of your own, in which you answer the questions that Cert3NF asks about one of the study's relations. You can also upload a CSV of your own and download the certified design as SQL. The free server sleeps when idle, so the first page may take up to a minute to load.

Code for *Confirming What Matters: Certified Third Normal Form Synthesis from Uncertain Functional Dependencies*.

Python 3.11 with numpy (`pip install -r requirements.txt`).
The LLM answers and the normalizer need vLLM and a GPU, and attribute exploration needs a C compiler.
The repository includes the 59 mined relations with their ground truth and the results behind every table and figure, so the tables and reports regenerate without rerunning anything.
Raw data, the publishers' documents behind the ground truth and the LLM answers are not included; the scripts below download or recompute them.

## Layout

| path | content |
|---|---|
| `sensitivity_bruteforce.py`, `baselines.py` | single errors on random schemata (Table 1) |
| `e2/` | accidental FDs of TPC-H (Table 2) |
| `e3/` | the relations (Table 8): downloads (`e3/download/`), mined candidates (`e3/data/`), ground truth (`e3/truth/`) |
| `confirm/v6f.py` | Cert3NF, its parts, its careful mode and its tolerance θ (Tables 3, 4, 6 and 9, Fig. 2); the live demo runs it |
| `confirm/v5.py` | the two phases and Cert3NF without an advisor (rule V1, Tables 4 and 9) |
| `confirm/ec2full.py` | the EC² order: Cert3NF with the order of questions of EC² (rule V3, Tables 3 and 4, Fig. 2) |
| `confirm/ec2hyb.py` | EC², which asks about candidates alone (Tables 3 and 4) |
| `confirm/auto_confirm.py`, `confirm/auto_mars.py` | automatic methods, the normalizer and the posterior certificate (Tables 3 and 4) |
| `confirm/v6f_designer.py` | the careful mode under a designer whose errors repeat or correlate (Sec. 6.5) |
| `confirm/aexp.c`, `confirm/aexp.py` | attribute exploration |
| `e3/scale.py`, `confirm/v6f_scale.py`, `confirm/scale_run.py` | synthetic relations with up to a million candidates (Table 5, rules S1-S3) |
| `confirm/check_cert.py` | independent check of every certificate |
| `confirm/v6f_fresh3_rules.md` | the rules V1-V5, written before any method ran on the confirmatory relations |
| `confirm/scripts/` | tables and reports: `paper_tables_v6f.py` writes Tables 3 to 6, 8 and 9 and the curves of Fig. 2 |
| `confirm/v6f_fresh3/`, `confirm/v6f_fresh3_extra/`, `confirm/v6f_fresh3_gptoss/` | results on the 23 confirmatory relations; `v6f_fresh3/report.txt` holds the verdicts of V1-V5 |
| `confirm/v6f_runs/` | results on the 35 development relations with answers of the model, and on the synthetic relations |
| `confirm/paper_src/`, `confirm/v5_*/`, `confirm/v5tol_*/`, ... | the posterior certificate and the automatic methods on the development relations, and the runs of the version before Cert3NF |
| `study/`, `render.yaml` | the human-designer study: its web server, fixed question blocks and materials (`study/README.md`) |

The runs record the md5 of the code they ran; `e2a6af907596` is that of `confirm/v6f.py`, which differs from the file here only in its docstring.

## Reproduce

Damage of single errors:

```bash
python sensitivity_bruteforce.py 300 1     # Table 1, n <= 6
python sensitivity_bruteforce.py 150 3 7   # Table 1, n = 7
cd e2 && python e2_tpch.py                 # Table 2
```

Relations, in `e3/`: TPC-H and SSB come from dbgen (`python build.py <dir with the .tbl files>`), the other development relations from the scripts in `e3/download/` and `unpack_fresh2.py`.
The 23 confirmatory relations come from `download_fresh3.sh` and `gen_fresh3.sh` and are unpacked by `unpack_fresh3.py`; their ground truth (`e3/truth/fresh3.json`) quotes the documentation that `download_docs3.sh` fetches, listed with its sha256 sums in `e3/truth/docs/fresh3/MANIFEST.tsv`.
Each relation is then mined and written to `e3/data/`:

```bash
python build.py none --stage mine --only <relation>
python build.py none --stage json --only <relations>
python dump_samples.py none samples <relations>
```

LLM answers, in `confirm/`, for the relations that `CONFIRM_BATCH` selects (unset: the first development relations; `2`: the second twelve; `3`: the confirmatory relations):

```bash
python auto_prompts.py prompts.jsonl --kinds expert,design,rules
python auto_llm.py --model Qwen/Qwen3.5-9B --prompts prompts.jsonl --out llm_fresh3_full_q35/answers_q35.jsonl \
    --kinds expert,design,rules --quantization fp8_per_block --max-tokens 16384
CONFIRM_TRUTH=full python auto_confirm.py rates --answers llm_fresh3_full_q35 --models q35
```

Experiments on the confirmatory relations, in `confirm/`, with `CONFIRM_BATCH=3`, `CONFIRM_ORACLE=gold` and `CONFIRM_TRUTH=full` (or `sure`, with the files of that truth):

```bash
DS=$(python -c "import auto_common as AC; print(','.join(AC.FRESH))"); A=llm_fresh3_full_q35; M='v6s|lc+hone+kf+rl'
python v6f.py --answers $A --datasets $DS --variants "$M,v6s,v6|lc+hone+kf+rl" --budget 1000 --out v6f_fresh3/main_full.jsonl   # Table 4, Fig. 2
python v6f.py --answers $A --datasets $DS --variants "$M" --budget 100 --out v6f_fresh3/b100_full.jsonl                          # Table 3
python v6f.py --answers $A --datasets $DS --budget 1000 --out v6f_fresh3/abl_full.jsonl \
    --variants 'v6s|lc,v6s|hone,v6s|kf,v6s|rl,v6s|hone+kf+rl,v6s|lc+kf+rl,v6s|lc+hone+rl,v6s|lc+hone+kf'                      # its parts (Sec. 6.4)
python v6f.py --answers $A --datasets $DS --variants "$M" --careful --budget 1000 --out v6f_fresh3/err_full.jsonl             # careful mode, Fig. 2
python v6f.py --answers $A --datasets $DS --variants "$M" --eps 0.02 --seeds 3 [--careful] --budget 1000 --out v6f_fresh3/err_full.jsonl   # Table 6, also --eps 0.05
python v5.py --answers $A --datasets $DS --variants v5,v5s,v5n --budget 1000 --out v6f_fresh3/v5_full.jsonl                  # two phases, without an advisor
python ec2full.py --answers $A --datasets $DS --variants ec2full,ec2full0 --budget 1000 --seeds 3 --out v6f_fresh3/ec2_full.jsonl   # EC2 order
python auto_confirm.py run --answers $A --models q35 --datasets $DS --variants rbhyb,rbhyb0 --out v6f_fresh3/rbhyb_full.jsonl       # posterior certificate
python ec2hyb.py run --answers $A --models q35 --datasets $DS --variants ec2hyb,ec2hyb0 --out v6f_fresh3_extra/ec2hyb_full.jsonl   # EC2
python auto_confirm.py run --answers $A --models q35 --datasets $DS --variants ours,trust,clf,L1,A5,A9,upper,hyfd --out v6f_fresh3/auto_full.jsonl   # Table 3
python auto_confirm.py run --answers $A --models q35 --datasets $DS --variants L3 --out v6f_fresh3/L3_full.jsonl              # normalizer
python check_cert.py --results v6f_fresh3/main_full.jsonl --truth > v6f_fresh3/check_main_full.txt
python scripts/price_exact.py v6f_fresh3/price_gold.json <dir for the covers>                                              # the price of Thm. 4.4
python scripts/v6f_fresh3_report.py > v6f_fresh3/report.txt                                                                 # rules V1-V5
```

The tolerance θ runs on the codes of the data that `python ../e3/dump_codes.py <dir> $DS` writes, before the repair with `FRESH_NO_REPAIR=1` set for `build.py` and `dump_codes.py`, and `scripts/witness_fresh3.py` lists the documented FDs that the data violate:

```bash
CODES_DIR=<dir> python v6f.py --answers $A --datasets $DS --variants "$M" --theta 0.1 --budget 1000 --out v6f_fresh3_extra/theta_rep_full.jsonl   # Table 4, also 0.01 and 0.001
```

A designer whose errors repeat or correlate, attribute exploration and the second model (gpt-oss-20b, answers with `--model gptoss`, results in `v6f_fresh3_gptoss/`):

```bash
python v6f_designer.py --answers $A --datasets $DS --variants "$M" --budget 1000 --eps 0.05 --seeds 3 --careful --repeated --out v6f_fresh3_extra/designer69/b3/designer_rep_full.jsonl   # also --rho 0.25 and 0.5
gcc -O2 -o aexp aexp.c && python aexp.py [--max] --datasets <relation> --out v6f_fresh3_extra/ae69/parts/max_full_<relation>.jsonl
```

On the development relations, the same commands run with `CONFIRM_BATCH` unset and the answers `llm_fresh_full_q35_ms` on the 23 relations of the first pools, and with `CONFIRM_BATCH=2` and `llm_fresh2_full_q35` on the second twelve; the results are `v6f_runs/<stem>_e2a6af907596_{dev,b2}_<truth>.jsonl`, with the variants `"$M,v6s|lc+hone+kf,v6s,v5s,v5n,v6|lc+hone+kf+rl"` for `main`.

Synthetic relations (Table 5): `e3/scale.py` generates them deterministically and writes their ground truth to `e3/truth/scale.json`; their mined candidates (up to 2 GB per relation) are not included.
Mining stops after two hours per relation; the relations with 40 and 50 attributes have no runs, since they are not mined within that limit or their millions of candidates do not fit into 60 GB of memory.

```bash
cd e3 && python scale.py gen && python scale.py mine --only <relation> && python scale.py json --only <relation>
cd ../confirm   # with CONFIRM_TRUTH=full CONFIRM_ORACLE=gold CONFIRM_BATCH=2
python v6f_scale.py --answers llm_fresh2_full_q35 --variants 'v6s|lc+hone+kf+rl,v5s' --budget 1000 --datasets <relations> --out v6f_runs/scale66/rows.jsonl
python scale_run.py check --results v6f_runs/scale66/rows.jsonl --out v6f_runs/scale66/check.jsonl
```

Tables, in `confirm/`:

```bash
python scripts/paper_tables_v6f.py > tables.out   # Tables 3 to 6, 8 and 9, Fig. 2 and the numbers of Sec. 6
```

The price of Thm. 4.4 comes from `price_gold.py`, which takes the FDs the simulated designer answers from, and from `cover_milp.py`, which finds a smallest cover exactly and needs `scipy`.
The runs of the version before Cert3NF (`v5.py`, `v5tol.py`, `v5tau.py`, with the reports `scripts/paper_tables_v5.py` and `scripts/*_report.py`) are kept with their results in `confirm/v5_*/`, `confirm/v5tol_*/` and `confirm/tau43/`.
