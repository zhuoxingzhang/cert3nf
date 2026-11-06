"""
Unpacks the raw files of the third batch of confirmatory relations (design notes, item 61) into the
delimited files that truth/fresh3.json names, and nothing more: it is driven by the spec, runs after the spec is
fixed, and only turns containers into tables (zip and 7z archives, SQLite databases, XML row files, header-less
text).  Column names come from the publisher (a published header, the DDL, the readme field list); no value is
changed.  Afterwards it checks that every column a spec uses exists in the produced header and prints the mismatches
(the same procedure as unpack_fresh2.py of item 33).

Usage (in e3):  python unpack_fresh3.py truth/fresh3.json <dir of download_fresh3.sh> docs/fresh3
"""
import csv, glob, io, json, os, re, shutil, sqlite3, subprocess, sys, zipfile
import xml.etree.ElementTree as ET

csv.field_size_limit(1 << 30)


def log(*a):
    print(*a, flush=True)


# ---------------- generic converters ----------------
def sqlite_to_csv(db, table, out):
    """one table as CSV with the column names of the database (the DDL's names)"""
    if not os.path.exists(db):                                # sqlite3.connect would create an empty file
        raise FileNotFoundError(2, "not generated yet", db)
    con = sqlite3.connect(db)
    cur = con.execute(f'SELECT * FROM "{table}"')
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([d[0] for d in cur.description])
        for row in cur:
            w.writerow(["" if v is None else v for v in row])
    con.close()


def add_header(src, cols, out, delimiter=","):
    """the published header-less file with the documentation's column names prepended; bytes otherwise unchanged"""
    with open(src, encoding="utf-8", errors="replace", newline="") as fh, open(out, "w", encoding="utf-8", newline="") as fo:
        fo.write(delimiter.join(cols) + "\n")
        for line in fh:
            fo.write(line)


def strip_bom_copy(src, out):
    """a copy without a UTF-8 byte-order mark (a published CSV whose first column name would otherwise carry it)"""
    with open(src, "rb") as fh, open(out, "wb") as fo:
        head = fh.read(3)
        if head != b"\xef\xbb\xbf":
            fo.write(head)
        shutil.copyfileobj(fh, fo)


def unzip_member(archive, member, out):
    """one member of a zip archive written to out (streamed; the member name is taken from FILES.txt)"""
    with zipfile.ZipFile(archive) as z, z.open(member) as src, open(out, "wb") as fo:
        shutil.copyfileobj(src, fo, 1 << 24)


def xml_rows_to_csv(src, out):
    """a Stack Exchange dump file (<rows><row attr="..."/>...</rows>) to CSV; the columns are the attribute names in
    the order of their first appearance, the values the attribute strings"""
    cols, rows = [], []
    seen = set()
    for _, el in ET.iterparse(src, events=("end",)):
        if el.tag != "row":
            continue
        for k in el.attrib:
            if k not in seen:
                seen.add(k)
                cols.append(k)
        rows.append(dict(el.attrib))
        el.clear()
    with open(out, "w", encoding="utf-8", newline="") as fo:
        w = csv.writer(fo)
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c, "") for c in cols])
    return cols


def header_names(path):
    """the column names of a one-line header file of the FEC data dictionaries (comma separated)"""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return [c.strip() for c in next(csv.reader(fh))]


# ---------------- the sources ----------------
OPENFLIGHTS_AIRPORTS = ["Airport ID", "Name", "City", "Country", "IATA", "ICAO", "Latitude", "Longitude", "Altitude",
                        "Timezone", "DST", "Tz database timezone", "Type", "Source"]     # openflights.org/data, airports.dat
OPENFLIGHTS_COUNTRIES = ["name", "iso_code", "dafif_code"]                                 # openflights.org/data, countries.dat
GLEIF_ZIP = "20261103-1600-gleif-goldencopy-lei2-golden-copy.csv.zip"
GLEIF_RA, GLEIF_ELF = "2026-09-30_ra-list-v1.9.csv", "2026-02-19-elf-code-list-v1.6.csv"
ONSPD_ZIP, ONSPD_DATA = "ONSPD_AUG_2026.zip", "Data/ONSPD_AUG_2026_UK.csv"
NPPES_ZIP = "NPPES_Data_Dissemination_November_2026_V2.zip"
CH_ZIP = "BasicCompanyData-2026-11-01-part1_7.zip"
OP_FILES = {"OP_DTL_GNRL_PGYR2024.csv": "OP_DTL_GNRL_PGYR2024_P06302026_06032026.csv",
            "OP_CVRD_RCPNT_PRFL_SPLMTL.csv": "OP_CVRD_RCPNT_PRFL_SPLMTL_P06302026_06032026.csv"}
SE_7Z = "3dprinting.stackexchange.com.7z"


def produce(path, raw, docs):
    """produce RAW/path from the raw downloads; returns True when something was written"""
    out = os.path.join(raw, path)
    if os.path.exists(out + ".done"):                         # converted by an earlier run
        return False
    made = _produce(path, out, raw, docs)
    if made:
        open(out + ".done", "w").close()
    return made


def _produce(path, out, raw, docs):
    src, name = path.split("/", 1)
    d = os.path.join(raw, src)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if src == "hgnc" or src == "ourairports":
        return False                                          # the download is the table
    if src == "gleif":
        if name == "lei2-golden-copy.csv":
            unzip_member(os.path.join(d, GLEIF_ZIP), GLEIF_ZIP[:-4], out)
        elif name == "ra-list.csv":
            strip_bom_copy(os.path.join(d, GLEIF_RA), out)
        elif name == "elf-code-list.csv":
            strip_bom_copy(os.path.join(d, GLEIF_ELF), out)
        else:
            return False
    elif src == "onspd":
        if name == "ONSPD_AUG_2026_UK.csv":
            unzip_member(os.path.join(d, ONSPD_ZIP), ONSPD_DATA, out)
        elif name.startswith("Documents/"):
            tmp = out + ".raw"
            unzip_member(os.path.join(d, ONSPD_ZIP), name, tmp)
            strip_bom_copy(tmp, out)
            os.remove(tmp)
        else:
            return False
    elif src == "fec":
        base = name[:-4]                                      # cn, cm, ccl
        with zipfile.ZipFile(os.path.join(d, base + "24.zip")) as z:
            z.extract(base + ".txt", os.path.join(d, "unzipped"))
        add_header(os.path.join(d, "unzipped", base + ".txt"), header_names(os.path.join(docs, f"fec_{base}_header_file.csv")), out, "|")
    elif src == "openflights":
        if name == "airports.csv":
            add_header(os.path.join(d, "airports.dat"), OPENFLIGHTS_AIRPORTS, out)
        elif name == "countries.csv":
            add_header(os.path.join(d, "countries.dat"), OPENFLIGHTS_COUNTRIES, out)
        else:
            return False
    elif src == "nppes":
        stem = name[:-4]                                      # npidata_pfile, pl_pfile, othername_pfile, endpoint_pfile
        with zipfile.ZipFile(os.path.join(d, NPPES_ZIP)) as z:
            member = [m for m in z.namelist() if re.fullmatch(stem + r"_\d{8}-\d{8}\.csv", m)]
        assert len(member) == 1, (stem, member)
        unzip_member(os.path.join(d, NPPES_ZIP), member[0], out)
    elif src == "companieshouse":
        unzip_member(os.path.join(d, CH_ZIP), name, out)
    elif src == "openpayments":
        if name not in OP_FILES:
            return False
        if os.path.lexists(out):
            os.remove(out)
        os.symlink(OP_FILES[name], out)
    elif src == "stackexchange":
        site, fn = name.split("/", 1)                         # 3dprinting/Posts.csv
        xml = os.path.join(d, site, fn[:-4] + ".xml")
        if not os.path.exists(xml):                           # one pass extracts every XML file of the site
            subprocess.run(["7z", "x", "-y", "-o" + os.path.join(d, site), os.path.join(d, SE_7Z)], check=True,
                           stdout=subprocess.DEVNULL)
        xml_rows_to_csv(xml, out)
    elif src == "benchbase":
        bench, table = name[:-4].split("/")
        sqlite_to_csv(os.path.join(d, bench + ".db"), table, out)
    elif src == "synthea":
        csvf = os.path.join(d, "output", "csv", name)
        if not os.path.exists(csvf):
            raise FileNotFoundError(2, "not generated yet", csvf)
        if os.path.lexists(out):
            os.remove(out)
        os.symlink(os.path.join("output", "csv", name), out)
    else:
        return False
    return True


def main(spec_file, raw, docs):
    doc = json.load(open(spec_file, encoding="utf-8"))
    problems = []
    for ds, e in doc["datasets"].items():
        spec = e["spec"]
        for t, tab in spec["tables"].items():
            try:
                made = produce(tab["file"], raw, docs)
                path = os.path.join(raw, tab["file"])
                with open(path, encoding=tab.get("encoding", "utf-8"), errors="replace", newline="") as fh:
                    hdr = next(csv.reader(fh, delimiter=tab.get("delimiter", ",")))
            except FileNotFoundError as exc:                  # raw input not downloaded yet: run again later
                log(f"{ds:22s} {t:28s} SKIPPED, raw input missing: {exc.filename}")
                problems.append(f"{ds}.{t}: skipped ({exc.filename} missing)")
                continue
            used = {c.split(".", 1)[1] for c in spec["columns"] if c.split(".", 1)[0] == t}
            used |= {c.split(".", 1)[1] for j in spec["joins"] for c in j["left"] if c.split(".", 1)[0] == t}
            used |= {c for j in spec["joins"] if j["right"] == t for c in j["key"]}
            used |= set(tab.get("filter", {}))
            missing = sorted(c for c in used if c not in hdr)
            log(f"{ds:22s} {t:28s} {'made' if made else 'kept'} {len(hdr):3d} columns; missing {missing}")
            for c in missing:
                near = [h for h in hdr if re.sub(r"[^a-z0-9]", "", h.lower()) == re.sub(r"[^a-z0-9]", "", c.lower())]
                problems.append(f"{ds}.{t}: column {c!r} not in header; near {near}")
    log("\n".join(problems) or "all columns found")


if __name__ == "__main__":
    main(*sys.argv[1:4])
