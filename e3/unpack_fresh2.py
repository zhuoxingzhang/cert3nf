"""
Unpacks the raw files of the second batch of confirmatory relations (design notes, item 33) into the
delimited files that truth/fresh2.json names, and nothing more: it is driven by the spec, runs after the spec is
fixed, and only turns containers into tables (archives, SQLite databases, SQL dumps, COPY files, workbooks,
fixed-width and header-less text).  Column names come from the publisher's documentation (readme field lists, DDL,
the dump's CREATE TABLE, the workbook's header row); no value is changed.  Afterwards it checks that every column a
spec uses exists in the produced header and prints the mismatches.

Usage (in e3):  python unpack_fresh2.py truth/fresh2.json <dir of download_fresh2.sh> docs/fresh2
"""
import csv, gzip, io, json, os, re, shutil, sqlite3, subprocess, sys, tarfile, zipfile

csv.field_size_limit(1 << 30)


def log(*a):
    print(*a, flush=True)


# ---------------- generic converters ----------------
def sqlite_to_csv(db, table, out, upper=False):
    """one table as CSV; upper=True writes the column names in upper case (ChEMBL's schema documentation)"""
    if not os.path.exists(db):                                # sqlite3.connect would create an empty file
        raise FileNotFoundError(2, "not generated yet", db)
    con = sqlite3.connect(db)
    cur = con.execute(f'SELECT * FROM "{table}"')
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([d[0].upper() if upper else d[0] for d in cur.description])
        for row in cur:
            w.writerow(["" if v is None else v for v in row])
    con.close()


def sql_values(s, i):
    """parse one MySQL tuple '(...)' starting at s[i] == '('; returns (values, index after ')')"""
    assert s[i] == "("
    i += 1
    vals = []
    n = len(s)
    while i < n:
        c = s[i]
        if c in " ,":
            i += 1
            continue
        if c == ")":
            return vals, i + 1
        if s[i:i + 8].upper() == "_BINARY ":
            i += 8
            continue
        if c == "'":
            i += 1
            buf = []
            while True:
                c = s[i]
                if c == "\\":
                    d = s[i + 1]
                    # MySQL never writes \x: it is a byte that is not UTF-8, kept as the \xNN escape of the decoder
                    buf.append({"n": "\n", "r": "\r", "t": "\t", "0": "\0", "Z": "\x1a"}.get(d, "\\x" if d == "x" else d))
                    i += 2
                elif c == "'":
                    if s[i + 1] == "'":
                        buf.append("'")
                        i += 2
                    else:
                        i += 1
                        break
                else:
                    buf.append(c)
                    i += 1
            vals.append("".join(buf))
        else:
            j = i
            while s[j] not in ",)":
                j += 1
            tok = s[i:j].strip()
            if tok.upper().startswith("X'") or tok.upper().startswith("0X"):
                h = tok[2:].rstrip("'")
                vals.append(bytes.fromhex(h).decode("utf-8", "replace"))
            else:
                vals.append("" if tok.upper() == "NULL" else tok)
            i = j
    raise ValueError("unterminated tuple")


def sqldump_to_csv(dump_gz, table, out):
    """a MySQL dump of one table (CREATE TABLE + INSERT INTO `t` VALUES (...),(...);, the tuples usually starting on
    the next line) to csv with the dump's columns; bytes that are not UTF-8 (binary sort keys) are kept distinct as
    \\xNN escapes"""
    with gzip.open(dump_gz, "rt", encoding="utf-8", errors="backslashreplace", newline="") as fh:
        txt = fh.read()
    m = re.search(r"CREATE TABLE `" + re.escape(table) + r"` \((.*?)\n\)", txt, re.S)
    cols = re.findall(r"^\s*`([^`]+)`", m.group(1), re.M)
    n = len(txt)
    with open(out, "w", encoding="utf-8", newline="") as fo:
        w = csv.writer(fo)
        w.writerow(cols)
        for s in re.finditer(r"INSERT INTO `" + re.escape(table) + r"` VALUES", txt):
            i = s.end()
            while True:
                while i < n and txt[i] in " \n\r\t,":
                    i += 1
                if i >= n or txt[i] != "(":
                    break
                vals, i = sql_values(txt, i)
                w.writerow(vals)
    return cols


def ddl_columns(create_sql, table):
    """the columns of CREATE TABLE <table> ( ... ) in a PostgreSQL DDL file (MusicBrainz admin/sql/CreateTables.sql):
    the parts of the outer parentheses split at depth 0, without comments, constraints and check clauses"""
    txt = open(create_sql, encoding="utf-8").read()
    txt = re.sub(r"--[^\n]*", "", txt)
    m = re.search(r"CREATE TABLE\s+" + re.escape(table) + r"\s*\(", txt)
    if not m:
        raise KeyError(table)
    i, depth, start, parts = m.end(), 1, m.end(), []
    while depth:
        c = txt[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                parts.append(txt[start:i])
        elif c == "," and depth == 1:
            parts.append(txt[start:i])
            start = i + 1
        i += 1
    cols = []
    for part in parts:
        tok = part.split()
        if tok and tok[0].upper() not in ("CONSTRAINT", "CHECK", "PRIMARY", "UNIQUE", "FOREIGN"):
            cols.append(tok[0])
    return cols


def copy_to_tsv(copy_file, cols, out):
    """a PostgreSQL COPY text file (tab, \\N for null, backslash escapes) to a tab-separated csv with a header"""
    esc = {"N": None, "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v", "\\": "\\"}
    with open(copy_file, encoding="utf-8", newline="") as fh, open(out, "w", encoding="utf-8", newline="") as fo:
        w = csv.writer(fo, delimiter="\t")
        w.writerow(cols)
        for line in fh:
            line = line.rstrip("\n")
            fields, buf, i, n = [], [], 0, len(line)
            null = False
            while i <= n:
                if i == n or line[i] == "\t":
                    fields.append("" if null else "".join(buf))
                    buf, null = [], False
                    i += 1
                    continue
                c = line[i]
                if c == "\\" and i + 1 < n:
                    d = line[i + 1]
                    if d == "N" and not buf:
                        null = True
                    else:
                        buf.append(esc.get(d, d))
                    i += 2
                else:
                    buf.append(c)
                    i += 1
            w.writerow(fields)


def fixed_width_to_csv(src, layout, out):
    """layout: [(name, first column (1-based), last column)] from the GHCN readme"""
    with open(src, encoding="utf-8", errors="replace") as fh, open(out, "w", encoding="utf-8", newline="") as fo:
        w = csv.writer(fo)
        w.writerow([n for n, _, _ in layout])
        for line in fh:
            if line.strip():
                w.writerow([line[a - 1:b].strip() for _, a, b in layout])


def ghcn_layout(readme, filename):
    """the 'Variable Columns Type' table of FORMAT OF "<filename>" in the GHCN-Daily readme"""
    txt = open(readme, encoding="utf-8", errors="replace").read()
    m = re.search(r'FORMAT OF "' + re.escape(filename) + r'"\s*\n-+\nVariable\s+Columns\s+Type\n-+\n(.*?)\n-+', txt, re.S)
    if not m:
        raise KeyError(filename)
    layout = []
    for line in m.group(1).split("\n"):
        mm = re.match(r"(.+?)\s+(\d+)-(\d+)\s+\w+", line)
        if mm:
            layout.append((mm.group(1).strip(), int(mm.group(2)), int(mm.group(3))))
    return layout


def xlsx_to_csv(xlsx, sheet, out):
    """one worksheet to csv; the header is the first row in which at least 80% of the cells are filled"""
    import pandas as pd
    raw = pd.read_excel(xlsx, sheet_name=sheet, header=None, dtype=str)
    hdr = next(i for i in range(min(10, len(raw))) if raw.iloc[i].notna().mean() >= 0.8)
    df = raw.iloc[hdr + 1:]
    df.columns = [str(c).strip() for c in raw.iloc[hdr]]
    df.to_csv(out, index=False)


def add_header(src, cols, out, delimiter="\t", comment=None):
    with open(src, encoding="utf-8", errors="replace", newline="") as fh, open(out, "w", encoding="utf-8", newline="") as fo:
        fo.write(delimiter.join(cols) + "\n")
        for line in fh:
            if comment and line.startswith(comment):
                continue
            fo.write(line)


# ---------------- the sources ----------------
GEONAMES_MAIN = ["geonameid", "name", "asciiname", "alternatenames", "latitude", "longitude", "feature class",
                 "feature code", "country code", "cc2", "admin1 code", "admin2 code", "admin3 code", "admin4 code",
                 "population", "elevation", "dem", "timezone", "modification date"]       # readme, "main 'geoname' table"
GEONAMES_ADMIN = ["code", "name", "name ascii", "geonameid"]                               # readme, admin1CodesASCII
GEONAMES_FEATURE = ["feature code", "name", "description"]                                 # readme, featureCodes
GEONAMES_TZ = ["countryCode", "timezoneId", "gmt offset on 1st of January",                 # readme, timeZones.txt
               "dst offset to gmt on 1st of July (of the current year)", "rawOffset without DST"]
GHCN_BY_YEAR = ["ID", "YEAR/MONTH/DAY", "ELEMENT", "DATA VALUE", "M-FLAG", "Q-FLAG", "S-FLAG", "OBS-TIME"]  # readme-by_year


def verified(archive):
    """a large archive is opened only after its checksum was verified (marker file <archive>.verified)"""
    if not os.path.exists(archive + ".verified"):
        raise FileNotFoundError(2, "download not verified yet", archive + ".verified")


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
    if src == "geonames":
        if name == "allCountries.txt":
            with zipfile.ZipFile(os.path.join(d, "allCountries.zip")) as z:
                z.extract("allCountries.txt", os.path.join(d, "unzipped"))
            add_header(os.path.join(d, "unzipped", "allCountries.txt"), GEONAMES_MAIN, out)
        elif name == "countryInfo.txt":
            raw_file = os.path.join(d, "countryInfo.raw")
            if not os.path.exists(raw_file):
                os.rename(out, raw_file)
            lines = open(raw_file, encoding="utf-8").read().split("\n")
            hdr = [l for l in lines if l.startswith("#ISO")][-1][1:]
            with open(out, "w", encoding="utf-8", newline="") as fo:
                fo.write(hdr + "\n" + "\n".join(l for l in lines if l and not l.startswith("#")) + "\n")
        elif name == "featureCodes_en.txt":
            raw_file = os.path.join(d, "featureCodes_en.raw")
            if not os.path.exists(raw_file):
                os.rename(out, raw_file)
            add_header(raw_file, GEONAMES_FEATURE, out)
        elif name in ("admin1CodesASCII.txt", "admin2Codes.txt"):
            raw_file = os.path.join(d, name + ".raw")
            if not os.path.exists(raw_file):
                os.rename(out, raw_file)
            add_header(raw_file, GEONAMES_ADMIN, out)
        elif name == "timeZones.txt":                         # the file's own header carries the current year
            raw_file = os.path.join(d, "timeZones.raw")
            if not os.path.exists(raw_file):
                os.rename(out, raw_file)
            lines = open(raw_file, encoding="utf-8").read().split("\n")
            assert len(lines[0].split("\t")) == len(GEONAMES_TZ), lines[0]
            with open(out, "w", encoding="utf-8", newline="") as fo:
                fo.write("\t".join(GEONAMES_TZ) + "\n" + "\n".join(l for l in lines[1:] if l) + "\n")
        else:
            return False
    elif src == "ghcn":
        readme = os.path.join(docs, "ghcnd_readme.txt")
        if name == "2024.csv":
            with gzip.open(os.path.join(d, "2024.csv.gz"), "rt", encoding="utf-8", newline="") as fh, \
                    open(out, "w", encoding="utf-8", newline="") as fo:
                fo.write(",".join(GHCN_BY_YEAR) + "\n")
                for line in fh:
                    fo.write(line)
        elif name.endswith(".csv"):
            txt = name[:-4] + ".txt"
            fixed_width_to_csv(os.path.join(d, txt), ghcn_layout(readme, txt), out)
        else:
            return False
    elif src == "eia":
        z = os.path.join(d, "eia8602025.zip")
        if not os.path.exists(os.path.join(d, "unzipped")):
            with zipfile.ZipFile(z) as zf:
                zf.extractall(os.path.join(d, "unzipped"))
        wb, sheet = name[:-4].rsplit("__", 1)
        xlsx = next(os.path.join(r, f) for r, _, fs in os.walk(os.path.join(d, "unzipped")) for f in fs
                    if f.lower() == wb.lower() + ".xlsx")
        xlsx_to_csv(xlsx, sheet, out)
    elif src == "mediawiki":
        table = name[:-4]
        sqldump_to_csv(os.path.join(d, f"simplewiki-20261001-{table}.sql.gz"), table, out)
    elif src == "chembl":
        db = next((os.path.join(r, f) for r, _, fs in os.walk(d) for f in fs if f.endswith(".db")), None)
        if db is None:
            verified(os.path.join(d, "chembl_37_sqlite.tar.gz"))
            with tarfile.open(os.path.join(d, "chembl_37_sqlite.tar.gz")) as t:
                t.extractall(os.path.join(d, "untar"), filter="data")
            db = next(os.path.join(r, f) for r, _, fs in os.walk(d) for f in fs if f.endswith(".db"))
        sqlite_to_csv(db, name[:-4], out, upper=True)
    elif src == "musicbrainz":
        table = name[:-4]
        member = os.path.join(d, "mbdump", table)
        if not os.path.exists(member):                        # one pass over the archive extracts every table
            verified(os.path.join(d, "mbdump.tar.bz2"))
            bz = "lbzip2" if shutil.which("lbzip2") else "pbzip2" if shutil.which("pbzip2") else "bzip2"
            subprocess.run(["nice", "-n", "19", "tar", "-I", bz, "-xf", os.path.join(d, "mbdump.tar.bz2"), "-C", d, "mbdump"], check=True)
        copy_to_tsv(member, ddl_columns(os.path.join(docs, "musicbrainz_CreateTables.sql"), table), out)
    elif src == "benchbase":
        bench, table = name[:-4].split("/")
        sqlite_to_csv(os.path.join(d, bench + ".db"), table, out)
    elif src == "pluto":                                      # the Open Data export carries display names; the spec uses fieldName
        raw_file = os.path.join(d, name + ".raw")
        if not os.path.exists(raw_file):
            os.rename(out, raw_file)
        meta = json.load(open(os.path.join(docs, "pluto_opendata_metadata.json"), encoding="utf-8"))
        field = {c["name"]: c["fieldName"] for c in meta["columns"]}
        with open(raw_file, encoding="utf-8-sig", newline="") as fh, open(out, "w", encoding="utf-8", newline="") as fo:
            r, w = csv.reader(fh), csv.writer(fo)
            w.writerow([field[h] for h in next(r)])
            w.writerows(r)
    else:
        return False                                          # fhrs, stats19: the download is the table
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
