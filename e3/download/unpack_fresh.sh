#!/bin/bash
# Unpacks the downloads of download_fresh.sh in place without reading any
# value: archives are extracted, the ABS workbook becomes abs/MB_2021_AUST.csv (its first sheet, header as is), and each
# TPC-DS .dat file gets a header line with its column names in the order of tpcds-kit/tools/tpcds.sql.  It lists the
# resulting file names only.
# Usage:  RAW=<dir of download_fresh.sh> bash unpack_fresh.sh
set -eu
cd "${RAW:-$PWD/fresh_raw}"
for z in faa/ReleasableAircraft.zip scorecard/*.zip epa/daily_44201_2025.zip pums/csv_pca.zip gtfs/gtfs.zip \
         usda/*.zip sec/2026q3.zip; do
  unzip -oq "$z" -d "$(dirname "$z")"
done
tar --zstd -xf ldbc/*.tar.zst -C ldbc
python3 - <<'EOF'
import csv, os, re
import openpyxl
wb = openpyxl.load_workbook("abs/MB_2021_AUST.xlsx", read_only=True)
ws = wb.worksheets[0]
with open("abs/MB_2021_AUST.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    for row in ws.iter_rows(values_only=True):
        if any(v is not None for v in row):
            w.writerow(["" if v is None else v for v in row])
print("abs sheet", ws.title, "of", wb.sheetnames)
ddl = open("tpcds/tpcds-kit/tools/tpcds.sql", encoding="latin-1").read()
for t in ("customer", "customer_address", "customer_demographics", "household_demographics", "income_band"):
    body = re.search(r"create table %s\s*\((.*?)\n\);" % t, ddl, re.S).group(1)
    cols = [ln.split()[0] for ln in body.splitlines() if ln.strip() and not ln.strip().startswith("primary key")]
    src, dst = f"tpcds/sf1/{t}.dat", f"tpcds/sf1/{t}.csv"
    with open(src, encoding="latin-1") as fi, open(dst, "w", encoding="latin-1") as fo:
        fo.write("|".join(cols) + "\n")
        for line in fi:
            fo.write(line)
    print("tpcds", t, len(cols), "columns")
EOF
find . -path ./tpcds/tpcds-kit -prune -o -type f -print | sort
