#!/bin/bash
# Downloads the data of the first batch of confirmatory relations (downloaded on 2026-10-27) into $RAW/<source>/, and generates the TPC-DS customer tables with tpcds-kit.  Nothing is
# unpacked or read here: item 28 fixes every relation from documentation before its data are opened.  Each file's
# HTTP status, size and sha256 go to fresh_raw/MANIFEST.tsv.  SEC is not here: sec.gov refuses requests without a
# contact address in the User-Agent.
# Usage:  RAW=<dir> bash download_fresh.sh
set -u
RAW=${RAW:-$PWD/fresh_raw}
mkdir -p "$RAW" && cd "$RAW" || exit 1
UA="Mozilla/5.0 (compatible; academic research)"
echo -e "date\tsource\tfile\thttp\tbytes\tsha256\turl" > MANIFEST.tsv
get() {   # source, file, url
  mkdir -p "$1"
  code=$(curl -sSL -A "$UA" --retry 3 --max-time 7200 -o "$1/$2" -w "%{http_code}" "$3")
  echo -e "$(date -u +%FT%TZ)\t$1\t$2\t$code\t$(stat -c %s "$1/$2" 2>/dev/null)\t$(sha256sum "$1/$2" | cut -c1-64)\t$3" \
    >> MANIFEST.tsv
  echo "$1/$2 $code $(stat -c %s "$1/$2" 2>/dev/null)"
}
get faa ReleasableAircraft.zip https://registry.faa.gov/database/ReleasableAircraft.zip
get abs MB_2021_AUST.xlsx "https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs/edition-3-july-2021-june-2026/access-and-downloads/allocation-files/MB_2021_AUST.xlsx"
get scorecard Most-Recent-Cohorts-Field-of-Study_10152026.zip https://ed-public-download.scorecard.network/downloads/Most-Recent-Cohorts-Field-of-Study_10152026.zip
get epa daily_44201_2025.zip https://aqs.epa.gov/aqsweb/airdata/daily_44201_2025.zip
get pums csv_pca.zip https://www2.census.gov/programs-surveys/acs/data/pums/2024/1-Year/csv_pca.zip
get gtfs gtfs.zip https://gtfs.at.govt.nz/gtfs.zip
get chicago crimes_2024.csv 'https://data.cityofchicago.org/resource/ijzp-q8t2.csv?$where=year=2024&$order=id&$limit=2000000'
get chicago iucr.csv 'https://data.cityofchicago.org/resource/c7ck-438e.csv?$order=iucr&$limit=50000'
get usda FoodData_Central_sr_legacy_food_csv_2018-04.zip https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip
get ldbc social_network-sf1-CsvCompositeMergeForeign-LongDateFormatter.tar.zst https://datasets.ldbcouncil.org/snb-interactive-v1/social_network-sf1-CsvCompositeMergeForeign-LongDateFormatter.tar.zst

# TPC-DS SF 1 customer cluster: the dsdgen of gregrahn/tpcds-kit, as prior work used for tpcds_core
mkdir -p tpcds && cd tpcds || exit 1
if [ ! -d tpcds-kit ]; then git clone -q https://github.com/gregrahn/tpcds-kit.git; fi
(cd tpcds-kit && echo "tpcds-kit commit $(git rev-parse HEAD)") | tee -a ../MANIFEST.tsv
(cd tpcds-kit/tools && make -s OS=LINUX CC="gcc -fcommon" > ../../build.log 2>&1) || { echo "tpcds-kit build failed"; tail build.log; exit 1; }
mkdir -p sf1
for t in customer customer_address customer_demographics household_demographics income_band; do
  (cd tpcds-kit/tools && ./dsdgen -scale 1 -table $t -dir ../../sf1 -force y -quiet y) || echo "dsdgen $t failed"
done
for f in sf1/*.dat; do
  echo -e "$(date -u +%FT%TZ)\ttpcds\t$f\tgen\t$(stat -c %s "$f")\t$(sha256sum "$f" | cut -c1-64)\tdsdgen -scale 1" >> ../MANIFEST.tsv
done
echo "== download_fresh done $(date)"
