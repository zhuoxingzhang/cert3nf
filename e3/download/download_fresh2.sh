#!/bin/bash
# Downloads the data of the second batch of confirmatory relations (downloaded on 2026-10-28) into $RAW/<source>/.  Nothing is unpacked or read here: item 33 fixes every
# relation from documentation before its data are opened.  Each file's HTTP status, size and sha256 go to
# fresh_raw2/MANIFEST.tsv.  The three BenchBase benchmarks come from gen_benchbase_linux.sh.
# Usage:  RAW=<dir> bash download_fresh2.sh small|chembl|musicbrainz
set -u
RAW=${RAW:-$PWD/fresh_raw2}
mkdir -p "$RAW" && cd "$RAW" || exit 1
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
[ -s MANIFEST.tsv ] || printf 'date\tsource\tfile\thttp\tbytes\tsha256\turl\n' > MANIFEST.tsv
get() {   # source, file, url; a file already downloaded (non-empty, recorded with 200) is kept
  mkdir -p "$1"
  if [ -s "$1/$2" ] && awk -F"	" -v s="$1" -v f="$2" '$2==s && $3==f && $4==200 {ok=1} END {exit !ok}' MANIFEST.tsv; then echo "$1/$2 kept"; return; fi
  code=$(curl -sSL -A "$UA" --retry 3 --max-time 14400 -o "$1/$2" -w "%{http_code}" "$3")
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$1" "$2" "$code" "$(stat -c %s "$1/$2" 2>/dev/null)" \
    "$(sha256sum "$1/$2" | cut -c1-64)" "$3" >> MANIFEST.tsv
  echo "$1/$2 $code $(stat -c %s "$1/$2" 2>/dev/null) $(date -u +%T)"
}
case "${1:-small}" in
small)
  # GeoNames (CC BY 4.0)
  for f in allCountries.zip countryInfo.txt timeZones.txt featureCodes_en.txt admin1CodesASCII.txt admin2Codes.txt hierarchy.zip; do
    get geonames "$f" "https://download.geonames.org/export/dump/$f"
  done
  # NOAA GHCN-Daily, year 2024
  get ghcn 2024.csv.gz https://www.ncei.noaa.gov/pub/data/ghcn/daily/by_year/2024.csv.gz
  for f in ghcnd-stations.txt ghcnd-states.txt ghcnd-countries.txt ghcnd-inventory.txt; do
    get ghcn "$f" "https://www.ncei.noaa.gov/pub/data/ghcn/daily/$f"
  done
  # UK FHRS, the publisher's all-authorities CSV (daily overwrite: the download date is the snapshot)
  get fhrs FHRS_All_en-GB.csv https://safhrsprodstorage.blob.core.windows.net/opendatafileblobstorage/FHRS_All_en-GB.csv
  # EIA-860, final 2025 release
  get eia eia8602025.zip https://www.eia.gov/electricity/data/eia860/xls/eia8602025.zip
  # STATS19 2024
  for t in collision vehicle casualty; do
    get stats19 "dft-road-casualty-statistics-$t-2024.csv" "https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-$t-2024.csv"
  done
  # simplewiki 2026-10-01 SQL table dumps
  for t in page categorylinks linktarget redirect; do
    get mediawiki "simplewiki-20261001-$t.sql.gz" "https://dumps.wikimedia.org/simplewiki/20261001/simplewiki-20261001-$t.sql.gz"
  done
  # NYC PLUTO 26v2, the Open Data CSV export (all columns; the projection is fixed by the spec later)
  get pluto pluto_26v2_export.csv "https://data.cityofnewyork.us/api/v3/views/64uk-42ks/export.csv?accessType=DOWNLOAD"
  echo "== small done $(date)";;
chembl)
  get chembl checksums.txt https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/chembl_37/checksums.txt
  get chembl chembl_37_sqlite.tar.gz https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/chembl_37/chembl_37_sqlite.tar.gz
  echo "== chembl done $(date)";;
musicbrainz)
  for f in MD5SUMS SHA256SUMS mbdump.tar.bz2; do
    get musicbrainz "$f" "https://data.metabrainz.org/pub/musicbrainz/data/fullexport/20261024-102842/$f"
  done
  echo "== musicbrainz done $(date)";;
big)
  # ChEMBL 37 SQLite release (CC BY-SA 3.0)
  get chembl checksums.txt https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/chembl_37/checksums.txt
  get chembl chembl_37_sqlite.tar.gz https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/chembl_37/chembl_37_sqlite.tar.gz
  # MusicBrainz full export 2026-10-24 (CC0 core data)
  for f in MD5SUMS SHA256SUMS mbdump.tar.bz2; do
    get musicbrainz "$f" "https://data.metabrainz.org/pub/musicbrainz/data/fullexport/20261024-102842/$f"
  done
  echo "== big done $(date)";;
esac
