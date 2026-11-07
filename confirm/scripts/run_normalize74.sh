#!/bin/bash
# Design note item 74: Normalize on batch 3.  Report only, no rule depends on it.  A rerun resumes.
#   STAGE=base   (the host with the raw files of batch 3): the unit test, the 23 instances (checked against e3/data),
#                the automatic Normalize under both truths, and the scores of the candidates (prior/<ds>.json)
#   STAGE=order  (any host with prior/ in place; TRUTHS selects the truths): Normalize order, v6n|lc+hone+kf+rl, budget 1000
#                and 100.  Control first, on two small relations: v6s|lc+hone+kf+rl run through v6f_norm.py equals the rows of
#                v6f_fresh3/main_<T>.jsonl field by field but secs, and v6n changes at least one of them.
# Usage:  STAGE=base FRESH_RAW=<raw files of batch 3> setsid nohup bash scripts/run_normalize74.sh > <log> 2>&1 < /dev/null &
#         STAGE=order TRUTHS=full setsid nohup bash scripts/run_normalize74.sh > <log> 2>&1 < /dev/null &
set -u
cd "${CONFIRM_DIR:-.}" || exit 1
export PY=${PY:-python}
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 CONFIRM_ORACLE=gold CONFIRM_BATCH=3
STAGE=${STAGE:?STAGE} TRUTHS=${TRUTHS:-full sure} WK=${WORKERS:-12}
OUT=v6f_fresh3_extra/normalize
mkdir -p $OUT
DS=$($PY -c "import auto_common as AC; print(','.join(AC.FRESH))")
[ "$(echo "$DS" | tr ',' '\n' | wc -l)" = 23 ] || { echo "not 23 relations: $DS"; exit 1; }
echo "== start $STAGE $(date) host $(hostname)"
md5sum normalize.py normalize_inst.py v6f_norm.py v6f.py auto_common.py auto_confirm.py bench.py ../e3/build.py ../e3/fresh.py ../e3/truth/fresh3.json | cut -c1-12,33-
if [ "$STAGE" = base ]; then
  $PY normalize.py test || exit 1
  todo=$(for d in ${DS//,/ }; do [ -s $OUT/inst/$d.npz ] || echo $d; done | paste -sd,)
  [ -z "$todo" ] || nice -n 19 $PY normalize_inst.py "$todo" || { echo "instances failed"; exit 1; }
  for T in $TRUTHS; do
    CONFIRM_TRUTH=$T nice -n 19 $PY normalize.py run --out $OUT/normalize_$T.jsonl || { echo "normalize failed $T"; exit 1; }
    echo "== normalize $T rows $(wc -l < $OUT/normalize_$T.jsonl)"
  done
  nice -n 19 $PY normalize.py prior || { echo "prior failed"; exit 1; }
  (cd $OUT && md5sum normalize_*.jsonl prior/*.json inst/*.npz) > $OUT/base_manifest.txt
elif [ "$STAGE" = order ]; then
  [ "$(ls $OUT/prior/*.json | wc -l)" = 23 ] || { echo "prior files missing"; exit 1; }
  MAIN='v6s|lc+hone+kf+rl' NV='v6n|lc+hone+kf+rl'
  CHK=fresh3_twitter_tweets,fresh3_nppes_npidata
  for T in $TRUTHS; do
    [ -s $OUT/check_$T.ok ] && continue
    F0=$OUT/check_${T}_default.jsonl F1=$OUT/check_${T}_norm.jsonl
    rm -f $F0 $F1
    CONFIRM_TRUTH=$T nice -n 19 $PY v6f_norm.py --answers llm_fresh3_${T}_q35 --datasets "$CHK" --variants "$MAIN" --budget 1000 --workers 2 --out $F0 >> $OUT/check_$T.log 2>&1 || { echo "control run failed $T"; exit 1; }
    $PY scripts/cmp_rows69.py $F0 v6f_fresh3/main_$T.jsonl variant,dataset --ignore secs || { echo "control differs $T"; exit 1; }
    CONFIRM_TRUTH=$T nice -n 19 $PY v6f_norm.py --answers llm_fresh3_${T}_q35 --datasets "$CHK" --variants "$NV" --budget 1000 --workers 2 --out $F1 >> $OUT/check_$T.log 2>&1 || { echo "norm run failed $T"; exit 1; }
    sed "s/\"variant\": \"v6n|/\"variant\": \"v6s|/; s/\"prior_kind\": \"normalize\"/\"prior_kind\": \"learned\"/" $F1 > $F1.as_main
    $PY scripts/cmp_rows69.py $F1.as_main v6f_fresh3/main_$T.jsonl variant,dataset --ignore secs --differ || { echo "the Normalize prior changed no row of $T"; exit 1; }
    echo "the wrapper reproduces the main rows, and the Normalize prior reaches the run" > $OUT/check_$T.ok
    echo "== control $T passed $(date)"
  done
  for T in $TRUTHS; do
    for B in 1000 100; do
      for try in 1 2 3; do
        echo "== $T budget $B try $try $(date)"
        CONFIRM_TRUTH=$T nice -n 19 $PY v6f_norm.py --answers llm_fresh3_${T}_q35 --datasets "$DS" --variants "$NV" --budget $B --workers $WK --out $OUT/order_${T}_b$B.jsonl >> $OUT/order_${T}_b$B.log 2>&1 && break
      done
      echo "== $T budget $B rows $(wc -l < $OUT/order_${T}_b$B.jsonl)"
    done
  done
  (cd $OUT && md5sum $(for T in $TRUTHS; do echo order_${T}_b1000.jsonl order_${T}_b100.jsonl; done)) > $OUT/order_${TRUTHS// /_}_manifest.txt
fi
echo "== end $(date)"
