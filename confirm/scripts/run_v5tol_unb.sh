#!/bin/bash
# Design note item 57: the careful mode of v5tol.py (v5t, v5st: mechanism c, eps_m 0.02, a designer who never errs)
# without a budget (1000 answers, a guard only), with the trusting v5, v5s of the same code as the implementation
# check, on the 35 relations with answers, both truths, under the settings of item 39 (23 development relations as
# v5_dev: CONFIRM_BATCH unset, llm_fresh_<T>_q35_ms; 12 confirmatory ones as item 33: CONFIRM_BATCH=2,
# llm_fresh2_<T>_q35).  v5tol.py is not changed (the driver scripts/run_v5tol_unb.py sets the budget).  A rerun resumes.
# Usage (in confirm, whose v5tol.py is the frozen f3ec39c04c59):
#   bash scripts/run_v5tol_unb.sh > v5tol_unb.log 2>&1
set -u
cd "${CONFIRM_DIR:-.}" || exit 1
export PY=${PY:-python}
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 CONFIRM_ORACLE=gold CONFIRM_BATCH=2
[ "$(md5sum v5tol.py | cut -c1-12)" = f3ec39c04c59 ] || { echo "v5tol.py is not the frozen f3ec39c04c59"; exit 1; }
[ "$(md5sum v5.py | cut -c1-12)" = 8e0e04aeb2ce ] || { echo "v5.py is not the frozen 8e0e04aeb2ce"; exit 1; }
# under CONFIRM_BATCH=2, AC.DATASETS are the 24 development relations (item 39)
DEV=$($PY -c "import auto_common as AC; print(','.join(d for d in AC.DATASETS if d != 'fresh_tpcds_customer'))")
CONF=$($PY -c "import auto_common as AC; print(','.join(AC.FRESH))")
[ "$(echo "$DEV" | tr ',' '\n' | wc -l)" = 23 ] || { echo "not 23 development relations: $DEV"; exit 1; }
[ "$(echo "$CONF" | tr ',' '\n' | wc -l)" = 12 ] || { echo "not 12 confirmatory relations: $CONF"; exit 1; }
mkdir -p v5tol_unb
echo "== start $(date) on $(hostname) in $(pwd)"
md5sum v5tol.py v5.py price.py auto_common.py auto_confirm.py auto_answer.py drd.py bench.py scripts/run_v5tol_unb.py \
  llm_fresh_full_q35_ms/answers_q35.jsonl llm_fresh_sure_q35_ms/answers_q35.jsonl \
  llm_fresh2_full_q35/answers_q35.jsonl llm_fresh2_sure_q35/answers_q35.jsonl \
  llm_fresh_full_q35_ms/answer_models_q35.json llm_fresh_sure_q35_ms/answer_models_q35.json \
  llm_fresh2_full_q35/answer_models_q35.json llm_fresh2_sure_q35/answer_models_q35.json | cut -c1-12,34-
for T in full sure; do
  echo "== $T development $(date)"
  CONFIRM_BATCH= CONFIRM_TRUTH=$T nice -n 19 $PY scripts/run_v5tol_unb.py --answers llm_fresh_${T}_q35_ms --datasets "$DEV" \
    --budget 1000 --workers ${WORKERS:-6} --out v5tol_unb/v5tol_$T.jsonl >> v5tol_unb/v5tol_$T.log 2>&1 \
    || { echo "$T development failed"; tail -20 v5tol_unb/v5tol_$T.log; exit 1; }
  echo "== $T confirmatory $(date)"
  CONFIRM_TRUTH=$T nice -n 19 $PY scripts/run_v5tol_unb.py --answers llm_fresh2_${T}_q35 --datasets "$CONF" \
    --budget 1000 --workers ${WORKERS:-6} --out v5tol_unb/v5tol_$T.jsonl >> v5tol_unb/v5tol_$T.log 2>&1 \
    || { echo "$T confirmatory failed"; tail -20 v5tol_unb/v5tol_$T.log; exit 1; }
done
md5sum v5tol_unb/*.jsonl | cut -c1-12,34-
echo "== done $(date)"
