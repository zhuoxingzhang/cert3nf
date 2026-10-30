#!/bin/bash
# Downloads the documentation of the second batch of confirmatory relations (on 2026-10-28) into
# e3/truth/docs/fresh2/: specifications, data dictionaries, readme files,
# DDL files pinned to a commit, download-page snapshots.  No data file is fetched here (see download_fresh2.sh).
# Each file's HTTP status, size and sha256 go to MANIFEST.tsv; SHA256SUMS is written at the end.
# Usage (in the repository root):  bash e3/download/download_docs2.sh
set -u
D=e3/truth/docs/fresh2
cd "$D" || exit 1
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
printf 'date\tfile\thttp\tbytes\tsha256\turl\n' > MANIFEST.tsv
get() {   # file, url
  code=$(curl -sSL -A "$UA" --retry 3 --max-time 600 -o "$1" -w "%{http_code}" "$2")
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$1" "$code" "$(stat -c %s "$1" 2>/dev/null)" "$(sha256sum "$1" | cut -c1-64)" "$2" >> MANIFEST.tsv
  echo "$1 $code $(stat -c %s "$1" 2>/dev/null)"
}
sha() { python -c "import json,sys; print(json.load(sys.stdin)['sha'])"; }
# pinned commits of the two source repositories whose DDL is the documentation
BB=$(curl -sSL -A "$UA" https://api.github.com/repos/cmu-db/benchbase/commits/main | sha)
MB=$(curl -sSL -A "$UA" https://api.github.com/repos/metabrainz/musicbrainz-server/commits/master | sha)
MW=$(curl -sSL -A "$UA" https://api.github.com/repos/wikimedia/mediawiki/commits/master | sha)
printf 'benchbase main %s\nmusicbrainz-server master %s\nmediawiki master %s\n' "$BB" "$MB" "$MW" > PINNED_COMMITS.txt
# --- BenchBase benchmarks (AuctionMark, SEATS, TATP)
for b in auctionmark seats tatp; do
  get benchbase_${b}_ddl-generic.sql https://raw.githubusercontent.com/cmu-db/benchbase/$BB/src/main/resources/benchmarks/$b/ddl-generic.sql
  get benchbase_${b}_ddl-postgres.sql https://raw.githubusercontent.com/cmu-db/benchbase/$BB/src/main/resources/benchmarks/$b/ddl-postgres.sql
  get benchbase_${b}_sample_sqlite_config.xml https://raw.githubusercontent.com/cmu-db/benchbase/$BB/config/sqlite/sample_${b}_config.xml
done
get benchbase_wiki_AuctionMark.md https://raw.githubusercontent.com/wiki/cmu-db/benchbase/AuctionMark.md
get benchbase_wiki_SEATS.md https://raw.githubusercontent.com/wiki/cmu-db/benchbase/SEATS.md
get benchbase_wiki_TATP.md https://raw.githubusercontent.com/wiki/cmu-db/benchbase/TATP.md
get benchbase_README.md https://raw.githubusercontent.com/cmu-db/benchbase/$BB/README.md
get benchbase_pom.xml https://raw.githubusercontent.com/cmu-db/benchbase/$BB/pom.xml
get hstore_projects_auctionmark.html https://hstore.cs.brown.edu/projects/auctionmark/
get hstore_projects_seats.html https://hstore.cs.brown.edu/projects/seats/
get oltpbench_pvldb_p277-difallah.pdf http://www.vldb.org/pvldb/vol7/p277-difallah.pdf
get tatp_TATP_Description.pdf https://tatpbenchmark.sourceforge.net/TATP_Description.pdf
get tatp_relnotes.txt https://tatpbenchmark.sourceforge.net/tatp_relnotes.txt
get tatp_home.html https://tatpbenchmark.sourceforge.net/
# --- MediaWiki + simplewiki
for t in Database_layout Page_table Categorylinks_table Linktarget_table Redirect_table; do
  get "mediawiki_Manual_${t}.wiki" "https://www.mediawiki.org/w/index.php?title=Manual:${t}&action=raw"
  get "mediawiki_Manual_${t}.html" "https://www.mediawiki.org/wiki/Manual:${t}"
done
get mediawiki_tables-generated.sql https://raw.githubusercontent.com/wikimedia/mediawiki/$MW/sql/mysql/tables-generated.sql
get mediawiki_tables.json https://raw.githubusercontent.com/wikimedia/mediawiki/$MW/sql/tables.json
get simplewiki_Special_Version.html https://simple.wikipedia.org/wiki/Special:Version
get simplewiki_20261001_index.html https://dumps.wikimedia.org/simplewiki/20261001/
get simplewiki_20261001_sha1sums.txt https://dumps.wikimedia.org/simplewiki/20261001/simplewiki-20261001-sha1sums.txt
get wikimedia_dumps_legal.html https://dumps.wikimedia.org/legal.html
get wikimedia_whats_available.html "https://meta.wikimedia.org/wiki/Data_dumps/What%27s_available_for_download"
# --- ChEMBL 37
for f in README LICENSE REQUIRED.ATTRIBUTION chembl_37_release_notes.txt schema_documentation.txt schema_documentation.html chembl_37_schema.png checksums.txt; do
  get "chembl37_$f" "https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/chembl_37/$f"
done
get chembl_downloads_page.html https://chembl.gitbook.io/chembl-interface-documentation/downloads
# --- MusicBrainz
for f in CreateTables.sql CreatePrimaryKeys.sql CreateFKConstraints.sql CreateIndexes.sql; do
  get "musicbrainz_$f" "https://raw.githubusercontent.com/metabrainz/musicbrainz-server/$MB/admin/sql/$f"
done
get musicbrainz_MBImport.pl https://raw.githubusercontent.com/metabrainz/musicbrainz-server/$MB/admin/MBImport.pl
get musicbrainz_Default.pm https://raw.githubusercontent.com/metabrainz/musicbrainz-server/$MB/lib/DBDefs/Default.pm
get musicbrainz_Schema.html https://musicbrainz.org/doc/MusicBrainz_Database/Schema
get musicbrainz_Download.html https://musicbrainz.org/doc/MusicBrainz_Database/Download
get musicbrainz_Data_License.html https://musicbrainz.org/doc/About/Data_License
get musicbrainz_datasets_postgres-dumps.html https://metabrainz.org/datasets/postgres-dumps
get musicbrainz_fullexport_20261024_index.html https://data.metabrainz.org/pub/musicbrainz/data/fullexport/20261024-102842/
get musicbrainz_fullexport_20261024_MD5SUMS https://data.metabrainz.org/pub/musicbrainz/data/fullexport/20261024-102842/MD5SUMS
get musicbrainz_fullexport_20261024_SHA256SUMS https://data.metabrainz.org/pub/musicbrainz/data/fullexport/20261024-102842/SHA256SUMS
get musicbrainz_fullexport_LATEST https://data.metabrainz.org/pub/musicbrainz/data/fullexport/LATEST
# --- NYC PLUTO 26v2
get pluto_datadictionary_26v2.pdf "https://data.cityofnewyork.us/api/views/64uk-42ks/files/153f6ffb-8789-450e-9266-774cb9cd2b77?download=true&filename=pluto_datadictionary.pdf"
get pluto_readme_26v2.pdf "https://data.cityofnewyork.us/api/views/64uk-42ks/files/b1acde6a-307f-4050-a2d3-301fe9bfb1f0?download=true&filename=pluto_readme.pdf"
get pluto_opendata_metadata.json https://data.cityofnewyork.us/api/views/64uk-42ks.json
get pluto_PLUTODD_bytes.pdf https://s-media.nyc.gov/agencies/dcp/assets/files/pdf/data-tools/bytes/PLUTODD.pdf
# --- UK FHRS
get fhrs_APIv1_guidance_april24.pdf https://ratings.food.gov.uk/open-data-resources/documents/FHRS_APIv1_guidance_april24.pdf
get fhrs_open-data.html https://ratings.food.gov.uk/open-data
get fhrs_terms-and-conditions.html https://ratings.food.gov.uk/terms-and-conditions
get fhrs_api_help.html https://api.ratings.food.gov.uk/help
for t in business-types ratings scheme-types authorities; do
  get "fhrs_api_$t.xml" "https://api1-ratings.food.gov.uk/$t/xml"
done
# --- GeoNames
get geonames_readme.txt https://download.geonames.org/export/dump/readme.txt
get geonames_codes.html https://www.geonames.org/export/codes.html
get geonames_about.html https://www.geonames.org/about.html
get geonames_export.html https://www.geonames.org/export/
get geonames_dump_index.html https://download.geonames.org/export/dump/
# --- EIA-860
get eia860_instructions.pdf https://www.eia.gov/survey/form/eia_860/instructions.pdf
get eia860_page.html https://www.eia.gov/electricity/data/eia860/
get eia_copyrights_reuse.html https://www.eia.gov/about/copyrights_reuse.php
# --- STATS19
get stats19_data-guide-2025.xlsx https://assets.publishing.service.gov.uk/media/6ab2a71d997a4b2950cced58/dft-road-casualty-statistics-road-safety-open-dataset-data-guide-2025.xlsx
get stats19_road-safety-data.html https://www.gov.uk/government/statistics/road-safety-data
get stats19_guidance.html https://www.gov.uk/government/publications/road-accident-and-safety-statistics-guidance
get stats19_datagovuk.html https://www.data.gov.uk/dataset/cb7ae6f0-4be6-4935-9277-47e5ce24a11f/road-safety-data
# --- GHCN-Daily
get ghcnd_readme.txt https://www.ncei.noaa.gov/pub/data/ghcn/daily/readme.txt
get ghcnd_doc_readme.txt https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/doc/readme.txt
get ghcnd_readme-by_year.txt https://www.ncei.noaa.gov/pub/data/ghcn/daily/by_year/readme-by_year.txt
get ghcnd_readme-by_station.txt https://www.ncei.noaa.gov/pub/data/ghcn/daily/readme-by_station.txt
get ghcnd_version.txt https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-version.txt
get ghcnd_product_page.html https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily
get ghcnd_iso_metadata.html "https://www.ncei.noaa.gov/access/metadata/landing-page/bin/iso?id=gov.noaa.ncdc:C00861"
sha256sum $(cut -f2 MANIFEST.tsv | tail -n +2) > SHA256SUMS
echo "== docs done $(date)"; awk -F'\t' 'NR>1 && $3 != 200 {print "NOT 200:", $2, $3}' MANIFEST.tsv
