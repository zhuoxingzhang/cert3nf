#!/bin/bash
# Downloads the documentation of the third batch of confirmatory relations into e3/truth/docs/fresh3/: data
# dictionaries, readme files, schema pages, DDL files pinned to a commit, download-page snapshots, item metadata.  No
# data file is fetched here (see download_fresh3.sh).  Each file's HTTP status, size and sha256 go to MANIFEST.tsv; a
# file already recorded with status 200 is kept on a rerun; SHA256SUMS is written at the end.  Only MANIFEST.tsv is in
# this repository, since the documents belong to their publishers.
# Usage (in the repository root):  bash e3/download/download_docs3.sh [group]   groups: all (default), op (Open Payments only)
set -u
D=e3/truth/docs/fresh3
cd "$D" || exit 1
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
[ -s MANIFEST.tsv ] || printf 'date\tfile\thttp\tbytes\tsha256\turl\n' > MANIFEST.tsv
get() {   # file, url
  if [ -s "$1" ] && awk -F'\t' -v f="$1" '$2==f && $3==200 {ok=1} END {exit !ok}' MANIFEST.tsv; then echo "$1 kept"; return; fi
  code=$(curl -sSL --compressed -A "$UA" --retry 3 --max-time 600 -o "$1" -w "%{http_code}" "$2")
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$1" "$code" "$(stat -c %s "$1" 2>/dev/null)" "$(sha256sum "$1" | cut -c1-64)" "$2" >> MANIFEST.tsv
  echo "$1 $code $(stat -c %s "$1" 2>/dev/null)"
}
G=${1:-all}
BB=33c00473807ebd49304d114a6d769d2d2b2bbb34      # BenchBase: the commit of the batch-2 build (docs/fresh2/PINNED_COMMITS.txt)
SYN=v4.0.0                                       # Synthea: the latest numbered release on 2026-11-04
if [ "$G" = all ]; then
SYNSHA=$(curl -sSL -A "$UA" "https://api.github.com/repos/synthetichealth/synthea/git/refs/tags/$SYN" | python -c "import json,sys; print(json.load(sys.stdin)['object']['sha'])")
printf 'benchbase main %s (the build of batch 2)\nsynthea tag %s %s\nsynthea wiki (no commit api) retrieved %s\n' "$BB" "$SYN" "$SYNSHA" "$(date -u +%F)" > PINNED_COMMITS.txt
# --- 1 HGNC
get hgnc_download_archive.html https://www.genenames.org/download/archive/
get hgnc_statistics_and_files.html https://www.genenames.org/download/statistics-and-files/
get hgnc_help_symbol_report.html https://www.genenames.org/help/symbol-report/
get hgnc_about_guidelines.html https://www.genenames.org/about/guidelines/
get hgnc_about_license.html https://www.genenames.org/about/license/
# --- 2 GLEIF
get gleif_level1_lei_cdf_3_1.html https://www.gleif.org/en/lei-data/access-and-use-lei-data/level-1-data-lei-cdf-3-1-format
get gleif_2021-03-04_lei-cdf-v3-1.xsd https://www.gleif.org/lei-data/access-and-use-lei-data/level-1-data-lei-cdf-3-1-format/2021-03-04_lei-cdf-v3-1.xsd
get gleif_2025-07-03_state-transition-validation-rules_2.8.5_final.pdf https://www.gleif.org/lei-data/access-and-use-lei-data/level-1-data-lei-cdf-3-1-format/2025-07-03_state-transition-validation-rules_2.8.5_final.pdf
get gleif_data_dictionary.html https://www.gleif.org/en/lei-data/access-and-use-lei-data/gleif-data-dictionary
get gleif_2025-11-18_gleif-data-dictionary_v1.2_final.pdf https://www.gleif.org/lei-data/access-and-use-lei-data/gleif-data-dictionary/2025-11-18_gleif-data-dictionary_v1.2_final.pdf
get gleif_golden_copy_download.html https://www.gleif.org/en/lei-data/gleif-golden-copy/download-the-golden-copy
get gleif_golden_copy.html https://www.gleif.org/en/lei-data/gleif-golden-copy
get gleif_golden_copy_api_latest.json https://goldencopy.gleif.org/api/v2/golden-copies/publishes/lei2/latest
get gleif_ra_list.html https://www.gleif.org/en/about-lei/code-lists/gleif-registration-authorities-list
get gleif_elf_code_list.html https://www.gleif.org/en/about-lei/code-lists/iso-20275-entity-legal-forms-code-list
get gleif_lei_data_terms.html https://www.gleif.org/en/lei-data/gleif-lei-look-up-api/lei-data-terms-of-use
# --- 3 ONSPD (August 2026, the latest on the Open Geography Portal on 2026-11-04)
get onspd_item_aug2026.json "https://www.arcgis.com/sharing/rest/content/items/9e5a92a3cfb14dc7ad43d6ea7a7b8c7f?f=json"
get onspd_user_guide_item_aug2026.json "https://www.arcgis.com/sharing/rest/content/items/920df475305b4b6baa9c3cab10813ca7?f=json"
get ONSPD_User_Guide_August_2026.zip https://www.arcgis.com/sharing/rest/content/items/920df475305b4b6baa9c3cab10813ca7/data
get onspd_datagovuk_user_guide_may2026.html https://www.data.gov.uk/dataset/cdc556b2-2c8a-4b02-9641-db923d8134af/ons-postcode-directory-may-2026-user-guide
# --- 4 FEC (2023-2024 cycle)
get fec_candidate_master_description.html https://www.fec.gov/campaign-finance-data/candidate-master-file-description/
get fec_committee_master_description.html https://www.fec.gov/campaign-finance-data/committee-master-file-description/
get fec_candidate_committee_linkage_description.html https://www.fec.gov/campaign-finance-data/candidate-committee-linkage-file-description/
get fec_cn_header_file.csv https://www.fec.gov/files/bulk-downloads/data_dictionaries/cn_header_file.csv
get fec_cm_header_file.csv https://www.fec.gov/files/bulk-downloads/data_dictionaries/cm_header_file.csv
get fec_ccl_header_file.csv https://www.fec.gov/files/bulk-downloads/data_dictionaries/ccl_header_file.csv
get fec_bulk_data_page.html "https://www.fec.gov/data/browse-data/?tab=bulk-data"
# --- 5 OpenFlights
get openflights_data.html https://openflights.org/data
# --- 6 OurAirports
get ourairports_data_dictionary.html https://ourairports.com/help/data-dictionary.html
get ourairports_data.html https://ourairports.com/data/
# --- 7 NPPES
get nppes_NPI_Files.html https://download.cms.gov/nppes/NPI_Files.html
get nppes_data_dissemination_page.html https://www.cms.gov/medicare/regulations-guidance/administrative-simplification/data-dissemination
get nppes_data_dissemination_file-readme.pdf https://www.cms.gov/regulations-and-guidance/administrative-simplification/nationalprovidentstand/downloads/data_dissemination_file-readme.pdf
get nppes_data_dissemination_file-code_values.pdf https://www.cms.gov/regulations-and-guidance/administrative-simplification/nationalprovidentstand/downloads/data_dissemination_file-code_values.pdf
get nppes_datadisseminationnpi.pdf https://www.cms.gov/regulations-and-guidance/administrative-simplification/nationalprovidentstand/downloads/datadisseminationnpi.pdf
# --- 8 Companies House
get companieshouse_en_output.html http://download.companieshouse.gov.uk/en_output.html
get companieshouse_freeDataProductDataset.pdf http://resources.companieshouse.gov.uk/toolsToHelp/pdf/freeDataProductDataset.pdf
# --- 10 Stack Exchange (site 3dprinting; the archive readme and the schema post of meta.stackexchange.com via the public API)
get stackexchange_archive_readme.txt https://archive.org/download/stackexchange/readme.txt
get stackexchange_archive_metadata.json https://archive.org/metadata/stackexchange
get stackexchange_meta_2677_question.json "https://api.stackexchange.com/2.3/questions/2677?site=meta&filter=withbody"
get stackexchange_meta_2677_answers.json "https://api.stackexchange.com/2.3/questions/2677/answers?site=meta&filter=withbody&pagesize=10&order=desc&sort=votes"
# --- 11, 12 BenchBase TPC-C, Epinions, Twitter (the pinned commit of the batch-2 build) + the TPC-C specification
for b in tpcc epinions twitter; do
  get benchbase_${b}_ddl-generic.sql https://raw.githubusercontent.com/cmu-db/benchbase/$BB/src/main/resources/benchmarks/$b/ddl-generic.sql
  get benchbase_${b}_ddl-postgres.sql https://raw.githubusercontent.com/cmu-db/benchbase/$BB/src/main/resources/benchmarks/$b/ddl-postgres.sql
  get benchbase_${b}_sample_sqlite_config.xml https://raw.githubusercontent.com/cmu-db/benchbase/$BB/config/sqlite/sample_${b}_config.xml
done
get benchbase_twitter_ddl-sqlite.sql https://raw.githubusercontent.com/cmu-db/benchbase/$BB/src/main/resources/benchmarks/twitter/ddl-sqlite.sql
get benchbase_wiki_TPC-C.md https://raw.githubusercontent.com/wiki/cmu-db/benchbase/TPC-C.md
get benchbase_wiki_epinions.md https://raw.githubusercontent.com/wiki/cmu-db/benchbase/epinions.md
get benchbase_wiki_Twitter.md https://raw.githubusercontent.com/wiki/cmu-db/benchbase/Twitter.md
get benchbase_README.md https://raw.githubusercontent.com/cmu-db/benchbase/$BB/README.md
get tpcc_v5.11.0.pdf https://www.tpc.org/tpc_documents_current_versions/pdf/tpc-c_v5.11.0.pdf
get oltpbench_pvldb_p277-difallah.pdf http://www.vldb.org/pvldb/vol7/p277-difallah.pdf
# --- 13 Synthea
get synthea_wiki_CSV-File-Data-Dictionary.md https://raw.githubusercontent.com/wiki/synthetichealth/synthea/CSV-File-Data-Dictionary.md
get synthea_release_$SYN.json https://api.github.com/repos/synthetichealth/synthea/releases/tags/$SYN
get synthea_README_$SYN.md https://raw.githubusercontent.com/synthetichealth/synthea/$SYN/README.md
get synthea_properties_$SYN.properties https://raw.githubusercontent.com/synthetichealth/synthea/$SYN/src/main/resources/synthea.properties
get synthea_LICENSE_$SYN https://raw.githubusercontent.com/synthetichealth/synthea/$SYN/LICENSE
get synthea_wiki_Basic-Setup-and-Running.md https://raw.githubusercontent.com/wiki/synthetichealth/synthea/Basic-Setup-and-Running.md
get synthea_wiki_Common-Configuration.md https://raw.githubusercontent.com/wiki/synthetichealth/synthea/Common-Configuration.md
fi
if [ "$G" = op ] || [ "$G" = all ]; then
  [ -s op_urls.txt ] && while read -r f u; do get "$f" "$u"; done < op_urls.txt
fi
sha256sum $(cut -f2 MANIFEST.tsv | tail -n +2 | sort -u) > SHA256SUMS
echo "== docs done $(date)"; awk -F'\t' 'NR>1 && $3 != 200 {print "NOT 200:", $2, $3}' MANIFEST.tsv
