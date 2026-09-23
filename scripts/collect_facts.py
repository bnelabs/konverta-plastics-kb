#!/usr/bin/env python3
"""
Bulk factual data collector for Konverta Plastics KB.

Usage:
  KB_DB_PATH=./data/dev.sqlite3 python scripts/collect_facts.py data/materials.csv --review-status draft

The CSV must contain columns:
code,name,common_uses,melt_temp_c,density_g_cm3,toxicity_level,recyclability,notes,source_title,source_url,review_status

Rules:
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
import re
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(os.getenv("KB_DB_PATH", "/data/plastics-kb.sqlite3"))

CODE_RE = re.compile(r"^[A-Z0-9-]+$")

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def validate_row(row, line_no):
    errors = []
    code = (row.get("code") or "").strip().upper()
    if not code or not CODE_RE.match(code):
        errors.append("code must be alphanumeric/hyphen")
    name = (row.get("name") or "").strip()
    if len(name) < 2:
        errors.append("name too short")
    source_title = (row.get("source_title") or "").strip()
    if len(source_title) < 2:
        errors.append("source_title required")
    source_url = (row.get("source_url") or "").strip()
    if not source_url.startswith("https://"):
        errors.append("source_url must start with https://")
    review_status = (row.get("review_status") or "draft").strip().lower()
    if review_status not in ("draft", "verified"):
        errors.append("review_status must be draft or verified")
    # density check
    density = row.get("density_g_cm3")
    if density:
        try:
            d = float(density)
            if not 0 <= d <= 100:
                errors.append("density out of range")
        except ValueError:
            errors.append("density not numeric")
    return errors

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
            try:
                con.execute("""
                    INSERT INTO materials(code,name,common_uses,melt_temp_c,density_g_cm3,toxicity_level,recyclability,notes,source_title,source_url,review_status)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    row["code"].strip().upper(),
                    row["name"].strip(),
                    row.get("common_uses",""),
                    row.get("melt_temp_c",""),
                    float(row["density_g_cm3"]) if row.get("density_g_cm3") else None,
                    row.get("toxicity_level","Not rated"),
                    row.get("recyclability","Not recorded"),
                    row.get("notes",""),
                    row["source_title"].strip(),
                    row["source_url"].strip(),
                    row["review_status"].strip().lower()
                ))
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
