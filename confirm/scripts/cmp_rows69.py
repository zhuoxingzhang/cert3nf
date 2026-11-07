"""Design note item 69: the controls compare result rows and print counts only, never a value of a result.
  python cmp_rows69.py NEW OLD KEYS [--fields F1,F2 | --ignore F1,F2] [--differ]
KEYS names the fields that identify a row.  Every row of NEW must have its row in OLD.  Without --fields, all fields of the NEW row
but those in --ignore are compared, and OLD must not hold other fields beyond them.  Exit 1 on a difference; with --differ, exit 1
when no row differs (the check that a replacement reached the run)."""
import argparse, json, sys


def rows(f):
    with open(f, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


ap = argparse.ArgumentParser()
ap.add_argument("new")
ap.add_argument("old")
ap.add_argument("keys")
ap.add_argument("--fields")
ap.add_argument("--ignore", default="secs")
ap.add_argument("--differ", action="store_true")
a = ap.parse_args()
keys = a.keys.split(",")
ign = set(a.ignore.split(","))
key = lambda r: tuple(r[k] for k in keys)
new, old = rows(a.new), {key(r): r for r in rows(a.old)}
assert len({key(r) for r in new}) == len(new), "NEW holds a key twice"
missing = [key(r) for r in new if key(r) not in old]
diff = fields = 0
names = set()
for r in new:
    o = old.get(key(r))
    if o is None:
        continue
    cols = a.fields.split(",") if a.fields else sorted((set(r) | set(o)) - ign)
    bad = [c for c in cols if r.get(c, "<none>") != o.get(c, "<none>")]
    fields += len(cols)
    diff += bool(bad)
    names |= set(bad)
print(f"{a.new}: {len(new)} rows against {a.old}, {fields} fields compared, {len(missing)} without a row, {diff} rows differ"
      + (f" in {sorted(names)}" if names else ""))
if not new or missing:
    sys.exit(1)
sys.exit((0 if diff else 1) if a.differ else (1 if diff else 0))
