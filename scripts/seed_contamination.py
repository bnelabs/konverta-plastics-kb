#!/usr/bin/env python3
"""Seed contamination risks into the live KB contamination table.

Reads a CSV with columns:
contaminant_name,material_code,impact_description,safety_notes,source_title,source_url,review_status

Mapping is performed material_code -> materials.id.
Rows are inserted with review_status defaulting to needs_review when missing.
Validation mirrors the API requirements: https source_url, non-empty safety_notes
and impact_description, material must exist.

Usage on host:
    cd /srv/plastics-kb
    KB_DB_PATH=/data/plastics-kb.sqlite3 python3 scripts/seed_contamination.py scripts/contamination_seed.csv
"""

import csv
import os
import sqlite3
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

DB_PATH = Path(os.getenv("KB_DB_PATH", "/data/plastics-kb.sqlite3"))

REQUIRED_COLUMNS = [
    "contaminant_name",
    "material_code",
    "impact_description",
    "safety_notes",
    "source_title",
    "source_url",
    "review_status",
]

def text(v):
    return "" if v is None else str(v).strip()

def validate_row(row, line_no):
    errors = []
    if not text(row.get("contaminant_name")):
        errors.append("contaminant_name required")
    if not text(row.get("material_code")):
        errors.append("material_code required")
    impact = text(row.get("impact_description"))
    if not impact:
        errors.append("impact_description required")
    safety = text(row.get("safety_notes"))
    if not safety:
        errors.append("safety_notes required")
    source_title = text(row.get("source_title"))
    if len(source_title) < 2:
        errors.append("source_title required")
    source_url = text(row.get("source_url"))
    if not source_url.startswith("https://"):
        errors.append("source_url must start with https://")
    # review_status optional, will default
    return errors

def main():
    if len(sys.argv) < 2:
        print("Usage: seed_contamination.py <csv_path>", file=sys.stderr)
        return 1
    csv_path = Path(sys.argv[1])
    if not csv_path.is_file():
        print(f"CSV not found: {csv_path}", file=sys.stderr)
        return 1
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}", file=sys.stderr)
        return 1

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")

    # cache material codes
    materials = {r["code"].upper(): r["id"] for r in con.execute("SELECT id,code FROM materials")}
    
    inserted = 0
    skipped = 0
    invalid = 0

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # normalize headers
        headers = [ (h or "").strip() for h in (reader.fieldnames or []) ]
        missing = [c for c in REQUIRED_COLUMNS if c not in headers]
        if missing:
            # allow review_status missing? We'll require all
            # but treat missing review_status as optional
            pass
        line_no = 1
        for row in reader:
            line_no += 1
            errors = validate_row(row, line_no)
            material_code = text(row.get("material_code")).upper()
            if material_code not in materials:
                errors.append(f"unknown material_code {material_code}")
            if errors:
                print(f"CSV line {line_no}: INVALID ({'; '.join(errors)})", file=sys.stderr)
                invalid += 1
                continue
            material_id = materials[material_code]
            contaminant_name = text(row.get("contaminant_name"))
            impact_description = text(row.get("impact_description"))
            safety_notes = text(row.get("safety_notes"))
            source_title = text(row.get("source_title"))
            source_url = text(row.get("source_url"))
            review_status = text(row.get("review_status")) or "needs_review"
            
            # avoid duplicate insertion on same contaminant+material+source
            exists = con.execute(
                "SELECT 1 FROM contamination WHERE material_id=? AND contaminant_name=? AND source_url=?",
                (material_id, contaminant_name, source_url)
            ).fetchone()
            if exists:
                print(f"CSV line {line_no}: SKIPPED duplicate for {material_code}/{contaminant_name}")
                skipped += 1
                continue
            try:
                con.execute(
                    """INSERT INTO contamination
                       (contaminant_name, material_id, impact_description, safety_notes, source_title, source_url, review_status)
                       VALUES (?,?,?,?,?,?,?)""",
                    (contaminant_name, material_id, impact_description, safety_notes, source_title, source_url, review_status)
                )
                inserted += 1
                print(f"CSV line {line_no}: INSERTED {material_code} / {contaminant_name}")
            except sqlite3.IntegrityError as e:
                print(f"CSV line {line_no}: DB ERROR {e}", file=sys.stderr)
                invalid += 1
                continue

    con.commit()
    con.execute(
        "INSERT INTO kb_events(event,entity_type,actor,details) VALUES('seeded','contamination','system',?)",
        (f'contamination seed from {csv_path.name}: inserted={inserted}, skipped={skipped}, invalid={invalid}',)
    )
    con.commit()
    con.close()
    print(f"Done. {inserted} inserted, {skipped} skipped, {invalid} invalid.")
    return 0 if invalid == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
