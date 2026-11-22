#!/bin/bash
# Three supplementary experiments, run after the verdicts V1-V5 and reported only; no rule depends on them.  A rerun resumes.
#   STAGE=wrong     Cert3NF with a wrong advisor (v6f_wrong.py): inverted, permuted (three), all; exact designer, budget 1000
#   STAGE=find      the EC^2 order with the Find step of Cert3NF (ec2find.py, variant ec2find0) on the confirmatory
#                   relations, three seeds, budget 1000
#   STAGE=designer  the careful mode with a designer at the rates of the practitioners of the study, (eps, phi) = (0.10, 0.12)
#                   and (0.15, 0.18), through v6f_designer.py, three seeds, budget 1000
# SETS names the relations: dev (the 23 development relations), b2 (the 12 of batch 2), b3 (the 23 confirmatory relations).
# Every stage runs its controls first and stops on a difference.  The controls print counts of rows, never a result.
# The rows go to v6f_fresh3_extra/item82/, where scripts/item82_report.py reads them.
# Usage (in confirm/):  STAGE=wrong SETS="b3 dev b2" WORKERS=4 bash scripts/run_item82.sh > <log> 2>&1
set -u
cd "${CONFIRM_DIR:-.}" || exit 1
PY=${PY:-python}
CMP="$PY ${CMP:-scripts/cmp_rows69.py}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 CONFIRM_ORACLE=gold
STAGE=${STAGE:?STAGE} TRUTHS=${TRUTHS:-full sure} WK=${WORKERS:-4} SETS=${SETS:-b3 dev b2}
C=e2a6af907596
R='lc+hone+kf+rl'
MAIN="v6s|$R"
OUT=v6f_fresh3_extra/item82
DEV23=food,hospital,pricepaid,ssb_customer,ssb_date,ssb_lineorder,ssb_part,ssb_supplier,tpcds_core,tpch_lineitem_orders,tpch_orders_customer,tpch_partsupp_part_supplier,fresh_ldbc_comment,fresh_ldbc_study,fresh_gtfs_at,fresh_faa,fresh_abs_mb,fresh_sec_fsds,fresh_scorecard_fos,fresh_epa_aqs,fresh_pums_ca,fresh_chicago_crimes,fresh_usda_sr
B2=fresh_auctionmark,fresh_seats,fresh_tatp,fresh_simplewiki,fresh_chembl,fresh_musicbrainz,fresh_pluto,fresh_fhrs,fresh_geonames,fresh_eia860,fresh_stats19,fresh_ghcn
mkdir -p $OUT/wrong $OUT/ec2find $OUT/designer $OUT/controls
echo "== start $STAGE $(date) sets [$SETS] truths [$TRUTHS] workers $WK"
[ "$(md5sum v6f.py | cut -c1-12)" = $C ] || { echo "v6f.py is not $C"; exit 1; }

enter() {  # set, truth: CONFIRM_BATCH, the answers, the relations, two small relations, the rows of the paper
  S=$1; T=$2
  case $S in
    dev) unset CONFIRM_BATCH; A=llm_fresh_${T}_q35_ms; DS=$DEV23; CHK=ssb_supplier,ssb_customer
         MAINROWS=v6f_runs/main_${C}_dev_$T.jsonl; ERRROWS=v6f_runs/err_${C}_dev_$T.jsonl ;;
    b2) export CONFIRM_BATCH=2; A=llm_fresh2_${T}_q35; DS=$B2; CHK=fresh_tatp,fresh_ghcn
        MAINROWS=v6f_runs/main_${C}_b2_$T.jsonl; ERRROWS=v6f_runs/err_${C}_b2_$T.jsonl ;;
    b3) export CONFIRM_BATCH=3; A=llm_fresh3_${T}_q35; CHK=fresh3_twitter_tweets,fresh3_nppes_npidata
        DS=$($PY -c "import auto_common as AC; print(','.join(AC.FRESH))")
        [ "$(echo "$DS" | tr ',' '\n' | wc -l)" = 23 ] || { echo "not 23 relations: $DS"; exit 1; }
        MAINROWS=v6f_fresh3/main_$T.jsonl; ERRROWS=v6f_fresh3/err_$T.jsonl ;;
    *) echo "unknown set $S"; exit 1 ;;
  esac
  export CONFIRM_TRUTH=$T
  [ -s "$MAINROWS" ] && [ -s "$ERRROWS" ] || { echo "rows of the paper missing: $MAINROWS $ERRROWS"; exit 1; }
}

case "$STAGE" in
wrong)
  WV="v6i|$R,v6p0|$R,v6p1|$R,v6p2|$R,v6a|$R"
  for S in $SETS; do
    for T in $TRUTHS; do
      enter $S $T
      K=$OUT/controls/wrong_check_${S}_$T
      if [ ! -s $K.ok ]; then
        $PY v6f_wrong.py test || { echo "unit test failed"; exit 1; }
        rm -f $K.main.jsonl $K.wrong.jsonl $K.*.as_main
        # 1 the wrapper is v6f.py for the main form: the rows of the paper, field by field but secs
        nice -n 19 $PY v6f_wrong.py --answers $A --datasets $CHK --variants "$MAIN" --budget 1000 --workers 2 --out $K.main.jsonl >> $K.log 2>&1 || { echo "control run failed $S $T"; exit 1; }
        $CMP $K.main.jsonl $MAINROWS variant,dataset --ignore secs || { echo "control differs $S $T"; exit 1; }
        # 2 every replacement reaches the run (prior_kind), and at least one changes the questions of a control relation
        nice -n 19 $PY v6f_wrong.py --answers $A --datasets $CHK --variants "$WV" --budget 1000 --workers $WK --out $K.wrong.jsonl >> $K.log 2>&1 || { echo "wrong control run failed $S $T"; exit 1; }
        moved=0
        for V in v6i v6p0 v6p1 v6p2 v6a; do
          grep "\"variant\": \"$V|" $K.wrong.jsonl | sed "s/\"variant\": \"$V|/\"variant\": \"v6s|/" > $K.$V.as_main
          $CMP $K.$V.as_main $MAINROWS variant,dataset --fields prior_kind --differ || { echo "$V did not reach the run $S $T"; exit 1; }
          $CMP $K.$V.as_main $MAINROWS variant,dataset --fields questions,certificate --differ > /dev/null && moved=$((moved + 1))
        done
        [ $moved -ge 1 ] || { echo "no wrong prior changed a control run $S $T"; exit 1; }
        echo "the wrapper reproduces the main rows; $moved of 5 wrong priors change a control run" > $K.ok
        echo "== control wrong $S $T passed $(date)"
      fi
      F=$OUT/wrong/wrong_${S}_$T
      nice -n 19 $PY v6f_wrong.py --answers $A --datasets "$DS" --variants "$WV" --budget 1000 --workers $WK --out $F.jsonl >> $F.log 2>&1 || echo "failed: wrong $S $T"
      nice -n 19 $PY check_cert.py --results $F.jsonl --truth > $F.check.txt 2>&1
      st=$?
      echo "== wrong $S $T rows $(wc -l < $F.jsonl) check_cert exit $st $(date)"
    done
  done
  ;;
find)
  for T in $TRUTHS; do
    enter b3 $T
    K=$OUT/controls/find_check_$T
    KEY=variant,dataset,seed,budget
    if [ ! -s $K.ok ]; then
      rm -f $K.full0.jsonl $K.find0.jsonl $K.find0.as_full0
      # 1 the variant ec2full0 of ec2find.py is ec2full.py: the rows of the paper, field by field but secs and the fields added
      nice -n 19 $PY ec2find.py --answers $A --datasets $CHK,fresh3_synthea_claims,fresh3_synthea_claims_transactions --variants ec2full0 --seeds 3 --budget 1000 --workers $WK --out $K.full0.jsonl >> $K.log 2>&1 || { echo "control run failed $T"; exit 1; }
      $CMP $K.full0.jsonl v6f_fresh3/ec2_$T.jsonl $KEY --ignore secs,find,code_find,code_ec2full,code_v6f || { echo "control differs $T"; exit 1; }
      # 2 the Find step of Cert3NF reaches the run: on two relations with FDs found through maximal sets, a row changes
      nice -n 19 $PY ec2find.py --answers $A --datasets fresh3_synthea_claims,fresh3_synthea_claims_transactions --variants ec2find0 --seeds 3 --budget 1000 --workers $WK --out $K.find0.jsonl >> $K.log 2>&1 || { echo "find control run failed $T"; exit 1; }
      sed 's/"variant": "ec2find0"/"variant": "ec2full0"/' $K.find0.jsonl > $K.find0.as_full0
      $CMP $K.find0.as_full0 v6f_fresh3/ec2_$T.jsonl $KEY --fields questions,qx_questions,certificate --differ || { echo "the Find step changed no control run $T"; exit 1; }
      echo "ec2full0 through ec2find.py reproduces the rows of the paper, and the Find step reaches the run" > $K.ok
      echo "== control find $T passed $(date)"
    fi
    F=$OUT/ec2find/ec2find_$T
    nice -n 19 $PY ec2find.py --answers $A --datasets "$DS" --variants ec2find0 --seeds 3 --budget 1000 --workers $WK --out $F.jsonl >> $F.log 2>&1 || echo "failed: find $T"
    nice -n 19 $PY check_cert.py --results $F.jsonl --truth > $F.check.txt 2>&1
    st=$?
    echo "== find $T rows $(wc -l < $F.jsonl) check_cert exit $st $(date)"
  done
  ;;
designer)
  nice -n 19 $PY scripts/test_v6f_designer.py > $OUT/controls/designer_test.txt 2>&1 || { echo "the flips differ from v5tol.py"; exit 1; }
  KEY=variant,dataset,designer_err,careful,seed,theta
  for S in $SETS; do
    for T in $TRUTHS; do
      enter $S $T
      K=$OUT/controls/designer_check_${S}_$T
      if [ ! -s $K.ok ]; then
        rm -f $K.rho0.jsonl $K.rho.jsonl
        # 1 without a correlation the wrapper is v6f.py: the rows of the paper at eps 0.05, careful, field by field
        nice -n 19 $PY v6f_designer.py --answers $A --datasets $CHK --variants "$MAIN" --budget 1000 --eps 0.05 --seeds 3 --careful --workers 6 --out $K.rho0.jsonl >> $K.log 2>&1 || { echo "control run failed $S $T"; exit 1; }
        $CMP $K.rho0.jsonl $ERRROWS $KEY --ignore secs,rho,repeated,designer_code || { echo "control differs $S $T"; exit 1; }
        # 2 the correlated designer is not the independent one
        nice -n 19 $PY v6f_designer.py --rho 0.12 --answers $A --datasets $CHK --variants "$MAIN" --budget 1000 --eps 0.05 --seeds 3 --careful --workers 6 --out $K.rho.jsonl >> $K.log 2>&1 || { echo "rho control run failed $S $T"; exit 1; }
        $CMP $K.rho.jsonl $K.rho0.jsonl $KEY --fields questions,certificate,designer_wrong --differ || { echo "rho 0.12 changed no control run $S $T"; exit 1; }
        echo "rho 0 reproduces the rows of the paper at eps 0.05; rho 0.12 changes a control run" > $K.ok
        echo "== control designer $S $T passed $(date)"
      fi
      for pair in 0.10:0.12 0.15:0.18; do
        E=${pair%%:*}; RHO=${pair##*:}
        F=$OUT/designer/designer_rho${RHO}_${S}_$T
        nice -n 19 $PY v6f_designer.py --rho $RHO --answers $A --datasets "$DS" --variants "$MAIN" --budget 1000 --eps $E --seeds 3 --careful --workers $WK --out $F.jsonl >> $F.log 2>&1 || echo "failed: designer $S $T $E $RHO"
        echo "== designer $S $T eps $E rho $RHO rows $(wc -l < $F.jsonl) $(date)"
      done
    done
  done
  ;;
*)
  echo "unknown stage $STAGE"; exit 1
  ;;
esac
echo "== end $STAGE $(date)"
