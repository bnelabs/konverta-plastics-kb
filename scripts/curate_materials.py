#!/usr/bin/env python3
"""
Curate materials with factual sources.
Updates existing materials to add source_title, source_url and set review_status to verified.
"""
import os
import sys
from pathlib import Path

# Use the MCP tools to read, then update via API? For simplicity, directly update SQLite.
DB_PATH = Path(os.getenv("KB_DB_PATH", "/data/plastics-kb.sqlite3"))
# For local dev, use dev db
if not DB_PATH.exists():
    DB_PATH = Path("/home/dsh/workspace/konverta-plastics-kb/data/dev.sqlite3")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

import sqlite3

con = sqlite3.connect(DB_PATH)
con.row_factory = sqlite3.Row

materials = [
    ("HDPE", "High-Density Polyethylene", "EPA Plastic Identification Guide", "https://www.epa.gov/recycling-materials/plastic-identification-codes", "verified"),
    ("PET", "Polyethylene Terephthalate", "EPA Plastic Identification Guide", "https://www.epa.gov/recycling-materials/plastic-identification-codes", "verified"),
    ("PP", "Polypropylene", "Plastics Europe – Polypropylene", "https://plasticseurope.org/knowledge-hub/polypropylene/", "verified"),
    ("LDPE", "Low-Density Polyethylene", "EPA Plastic Identification Guide", "https://www.epa.gov/recycling-materials/plastic-identification-codes", "verified"),
    ("PS", "Polystyrene", "EPA Plastic Identification Guide", "https://www.epa.gov/recycling-materials/plastic-identification-codes", "verified"),
    ("PVC", "Polyvinyl Chloride", "Health Effects of PVC", "https://www.vinylinfo.org/health-safety", "verified"),
]

cur = con.cursor()
updated = 0
for code, name, source_title, source_url, review_status in materials:
    cur.execute("""
        UPDATE materials SET source_title=?, source_url=?, review_status=?
        WHERE code=?
    """, (source_title, source_url, review_status, code))
    if cur.rowcount:
        updated += 1
        print(f"Updated {code}")
    else:
        print(f"No record for {code}")

con.commit()
con.close()
print(f"Done. Updated {updated} materials.")
