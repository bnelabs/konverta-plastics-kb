#!/usr/bin/env python3
"""
Bulk factual data collector for Konverta Plastics KB.

Usage:
  KB_DB_PATH=./data/dev.sqlite3 python scripts/collect_facts.py data/materials.csv --review-status draft

The CSV must contain columns:
code,name,common_uses,melt_temp_c,density_g_cm3,toxicity_level,recyclability,notes,source_title,source_url,review_status

Rules (shared with POST /api/v1/materials/bulk via app/curation.py):
- code normalized to upper case, alphanumeric/hyphen
- source_url must start with https://
- review_status must be draft or verified
- source_title and source_url are required
- safety notes should be included in notes field
- unknown compatibility is never inferred
"""
import argparse
import csv
import os
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(os.getenv("KB_DB_PATH", "/data/plastics-kb.sqlite3"))

# The shared rules live in app/curation.py (standard library only). Importing
# app.main from here would pull in FastAPI/MCP/uvicorn, so keep the path bootstrap.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.curation import MATERIAL_COLUMNS, material_row_values, validate_material_row  # noqa: E402

INSERT_SQL = f"INSERT INTO materials ({','.join(MATERIAL_COLUMNS)}) VALUES ({','.join('?' for _ in MATERIAL_COLUMNS)})"

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def validate_row(row, line_no=None):
    """Human-readable messages for one CSV row; rules are shared with the API."""
    return [error["message"] for error in validate_material_row(row)]

def main():
    parser = argparse.ArgumentParser(description="Import factual material records")
    parser.add_argument("csv_path", help="CSV file path")
    parser.add_argument("--review-status", default="draft", choices=["draft","verified"])
    args = parser.parse_args()

    if not Path(args.csv_path).exists():
        print(f"File not found: {args.csv_path}", file=sys.stderr)
        sys.exit(1)

    con = connect()
    # ensure tables exist
    # Minimal schema check omitted for brevity

    inserted = 0
    skipped = 0
    with open(args.csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            # override review status if provided
            if not row.get("review_status"):
                row["review_status"] = args.review_status
            errors = validate_row(row, i)
            if errors:
                print(f"Line {i} SKIPPED: {'; '.join(errors)}", file=sys.stderr)
                skipped += 1
                continue
            values = material_row_values(row)
            try:
                con.execute(INSERT_SQL, [values[column] for column in MATERIAL_COLUMNS])
                con.commit()
                inserted += 1
            except sqlite3.IntegrityError:
                print(f"Line {i} SKIPPED: duplicate code", file=sys.stderr)
                skipped += 1
            except Exception as e:
                print(f"Line {i} ERROR: {e}", file=sys.stderr)
                skipped += 1

    print(f"Import complete: {inserted} inserted, {skipped} skipped")
    con.close()

if __name__ == "__main__":
    main()
