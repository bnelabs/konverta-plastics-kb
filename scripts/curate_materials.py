#!/usr/bin/env python3
"""Re-apply the curated material dataset to an existing KB database.

Single source of truth: ``scripts/materials_curated.csv`` (resolved relative to
this script's location, so it works regardless of the caller's cwd).

Rows are updated in place keyed by ``code`` (``UPDATE ... WHERE code=?``);
nothing is inserted and nothing is deleted, so this script is safe to re-run on
the live database. Validation rules are the same shared ones as the API and
``scripts/collect_facts.py`` (app/curation.py).

Usage on the host:
    cd /srv/plastics-kb
    KB_DB_PATH=/data/plastics-kb.sqlite3 python3 scripts/curate_materials.py

Standard library only (sqlite3, csv).
"""
import csv
import os
import sqlite3
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.curation import MATERIAL_COLUMNS, material_row_values, validate_material_row  # noqa: E402

CSV_PATH = SCRIPT_DIR / "materials_curated.csv"
DB_PATH = Path(os.getenv("KB_DB_PATH", "/data/plastics-kb.sqlite3"))

UPDATE_SQL = (
    "UPDATE materials SET "
    + ", ".join(f"{column}=?" for column in MATERIAL_COLUMNS if column != "code")
    + " WHERE code=?"
)


def main() -> int:
    if not CSV_PATH.exists():
        print(f"CSV not found: {CSV_PATH}", file=sys.stderr)
        return 1
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}", file=sys.stderr)
        return 1

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    updated = 0
    missing = 0
    invalid = 0
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for line_no, row in enumerate(csv.DictReader(f), start=2):
            errors = validate_material_row(row)
            if errors:
                print(f"CSV line {line_no}: INVALID ({'; '.join(e['message'] for e in errors)})", file=sys.stderr)
                invalid += 1
                continue
            values = material_row_values(row)
            params = [values[column] for column in MATERIAL_COLUMNS if column != "code"] + [values["code"]]
            cur = con.execute(UPDATE_SQL, params)
            if cur.rowcount:
                updated += 1
                print(f"CSV line {line_no}: UPDATED {values['code']} -> review_status={values['review_status']}, source={values['source_url']}")
            else:
                missing += 1
                print(f"CSV line {line_no}: NO EXISTING ROW for {values['code']} (not inserted)")
    con.commit()
    con.close()
    print(f"Done. {updated} updated, {missing} without existing row, {invalid} invalid.")
    return 0 if invalid == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
