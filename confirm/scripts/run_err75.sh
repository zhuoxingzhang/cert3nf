#!/bin/bash
# Design note item 75: a designer who errs at the rates of the practitioners in the study, eps 0.10 and 0.15, in the careful
# and the trusting mode, three seeds, budget 1000, the main form, both truths: the runs of items 66 and 67 for eps 0.02 and
# 0.05 at two more rates.  Report only, no rule depends on it.  A rerun resumes.
#   PART=b3   the 23 confirmatory relations (CONFIRM_BATCH=3)
#   PART=dev  the 23 development relations and the 12 of batch 2 (CONFIRM_BATCH=2)
# Control first, per directory and truth: eps 0.05 in the careful mode on two small relations equals the rows of the paper
# field by field but secs.
# Usage (in confirm/):  PART=b3 bash scripts/run_err75.sh > <log> 2>&1
set -u
export PY=${PY:-python}
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 CONFIRM_ORACLE=gold
PART=${PART:?PART} TRUTHS=${TRUTHS:-full sure} WK=${WORKERS:-12} EPS=${EPS:-0.10 0.15}
MAIN='v6s|lc+hone+kf+rl'
C=e2a6af907596
CMP=${CMP:-scripts/cmp_rows69.py}
DEV23=food,hospital,pricepaid,ssb_customer,ssb_date,ssb_lineorder,ssb_part,ssb_supplier,tpcds_core,tpch_lineitem_orders,tpch_orders_customer,tpch_partsupp_part_supplier,fresh_ldbc_comment,fresh_ldbc_study,fresh_gtfs_at,fresh_faa,fresh_abs_mb,fresh_sec_fsds,fresh_scorecard_fos,fresh_epa_aqs,fresh_pums_ca,fresh_chicago_crimes,fresh_usda_sr
B2=fresh_auctionmark,fresh_seats,fresh_tatp,fresh_simplewiki,fresh_chembl,fresh_musicbrainz,fresh_pluto,fresh_fhrs,fresh_geonames,fresh_eia860,fresh_stats19,fresh_ghcn
echo "== start $PART $(date) host $(hostname)"

one() {  # directory, CONFIRM_BATCH ('' unset), answers, datasets, rows of the paper, new rows, control datasets, truth
  D=$1; BATCH=$2; ANS=$3; DS=$4; OLD=$5; NEW=$6; CHK=$7; T=$8
  cd "${CONFIRM_DIR:-.}" || exit 1
  [ "$(md5sum v6f.py | cut -c1-12)" = $C ] || { echo "v6f.py in $D is not $C"; exit 1; }
  if [ -n "$BATCH" ]; then export CONFIRM_BATCH=$BATCH; else unset CONFIRM_BATCH; fi
  export CONFIRM_TRUTH=$T
  [ -s "$OLD" ] || { echo "no rows of the paper: $D/$OLD"; exit 1; }
  if [ -z "$DS" ]; then
    DS=$($PY -c "import auto_common as AC; print(','.join(AC.FRESH))")
    [ "$(echo "$DS" | tr ',' '\n' | wc -l)" = 23 ] || { echo "not 23 relations: $DS"; exit 1; }
  fi
  mkdir -p "$(dirname "$NEW")"
  if [ ! -s "$NEW.ok" ]; then
    rm -f "$NEW.check.jsonl"
    nice -n 19 $PY v6f.py --answers "$ANS" --datasets "$CHK" --variants "$MAIN" --eps 0.05 --seeds 3 --careful --budget 1000 --workers 6 --out "$NEW.check.jsonl" >> "$NEW.log" 2>&1 || { echo "control run failed $D $T"; exit 1; }
    $PY $CMP "$NEW.check.jsonl" "$OLD" variant,dataset,designer_err,careful,seed,theta --ignore secs || { echo "control differs $D $T"; exit 1; }
    echo "eps 0.05 careful reproduces the rows of the paper on $CHK" > "$NEW.ok"
    echo "== control $D $T passed $(date)"
  fi
  for E in $EPS; do
    echo "== $D $T eps $E $(date)"
    nice -n 19 $PY v6f.py --answers "$ANS" --datasets "$DS" --variants "$MAIN" --eps $E --seeds 3 --careful --budget 1000 --workers $WK --out "$NEW" >> "$NEW.log" 2>&1 || echo "failed careful $E $D $T"
    nice -n 19 $PY v6f.py --answers "$ANS" --datasets "$DS" --variants "$MAIN" --eps $E --seeds 3 --budget 1000 --workers $WK --out "$NEW" >> "$NEW.log" 2>&1 || echo "failed trusting $E $D $T"
  done
  echo "== $D $T rows $(wc -l < "$NEW") $(md5sum "$NEW" | cut -c1-12)"
}

for T in $TRUTHS; do
  if [ "$PART" = b3 ]; then
    one confirm 3 llm_fresh3_${T}_q35 "" v6f_fresh3/err_${T}.jsonl v6f_fresh3_extra/err75/err_b3_${T}.jsonl fresh3_twitter_tweets,fresh3_nppes_npidata $T
  elif [ "$PART" = dev ]; then
    one confirm "" llm_fresh_${T}_q35_ms "$DEV23" v6f_runs/err_${C}_dev_${T}.jsonl v6f_runs/err75_${C}_dev_${T}.jsonl ssb_supplier,ssb_customer $T
    one confirm 2 llm_fresh2_${T}_q35 "$B2" v6f_runs/err_${C}_b2_${T}.jsonl v6f_runs/err75_${C}_b2_${T}.jsonl fresh_tatp,fresh_ghcn $T
  fi
done
echo "== end $(date)"
