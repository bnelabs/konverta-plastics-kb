"""Shared factual-row rules and bulk import mechanics for the Konverta plastics KB.

This module is standard-library only on purpose: it is imported both by the API
(``app.main``) and by the CSV importer (``scripts/collect_facts.py``), so the two
entry points cannot drift apart. Importing ``app.main`` from the script would
drag in FastAPI, MCP, PyJWT and uvicorn, so the shared rules live here instead.

Factual rules (identical for every entry point):
- code normalised to upper case, letters/digits/hyphens only
- name at least 2 characters
- source_title required (at least 2 characters)
- source_url must start with https://
- review_status must be draft or verified
- density_g_cm3 numeric and within 0..100 when present
- unknown polymer compatibility is never inferred or written here
"""
from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
from collections.abc import Iterable, Mapping
from typing import Any

CODE_RE = re.compile(r"^[A-Z0-9-]+$")
REVIEW_STATUSES = ("draft", "verified")

# Columns written to materials, in a stable insert order.
MATERIAL_COLUMNS = (
    "code",
    "name",
    "common_uses",
    "melt_temp_c",
    "density_g_cm3",
    "toxicity_level",
    "recyclability",
    "notes",
    "glass_transition_temp_c",
    "additives_common",
    "thermal_conductivity_w_m_k",
    "source_title",
    "source_url",
    "review_status",
)

# Optional text columns and the defaults scripts/collect_facts.py already used.
TEXT_DEFAULTS = {
    "common_uses": "",
    "melt_temp_c": "",
    "toxicity_level": "Not rated",
    "recyclability": "Not recorded",
    "notes": "",
    "glass_transition_temp_c": "",
    "additives_common": "",
    "thermal_conductivity_w_m_k": "",
}

# A CSV import may omit optional columns, but never the source columns.
REQUIRED_CSV_COLUMNS = ("code", "name", "source_title", "source_url")


def text(value: Any) -> str:
    """Return a trimmed string for any cell value (None becomes "")."""
    return "" if value is None else str(value).strip()


def normalize_code(value: Any) -> str:
    """Canonical resin code: trimmed and upper-cased."""
    return text(value).upper()


def validate_material_row(row: Mapping[str, Any]) -> list[dict[str, str]]:
    """Validate one material row and return ``[{"field", "message"}]`` errors.

    An empty list means the row is insertable. The rules and messages match
    ``scripts/collect_facts.py`` exactly; a row that fails here is never inserted.
    """
    errors: list[dict[str, str]] = []
    code = normalize_code(row.get("code"))
    if not code or not CODE_RE.match(code):
        errors.append({"field": "code", "message": "code must be alphanumeric/hyphen"})
    if len(text(row.get("name"))) < 2:
        errors.append({"field": "name", "message": "name too short"})
    if len(text(row.get("source_title"))) < 2:
        errors.append({"field": "source_title", "message": "source_title required"})
    if not text(row.get("source_url")).startswith("https://"):
        errors.append({"field": "source_url", "message": "source_url must start with https://"})
    review_status = (text(row.get("review_status")) or "draft").lower()
    if review_status not in REVIEW_STATUSES:
        errors.append({"field": "review_status", "message": "review_status must be draft or verified"})
    # Falsy density (None/""/0) skips the numeric check, as in collect_facts.py.
    density = row.get("density_g_cm3")
    if density:
        try:
            density_value = float(density)
        except (TypeError, ValueError):
            errors.append({"field": "density_g_cm3", "message": "density not numeric"})
        else:
            if not 0 <= density_value <= 100:
                errors.append({"field": "density_g_cm3", "message": "density out of range"})
    return errors


def material_row_values(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return canonical insert values for a row that passed validation."""
    density = row.get("density_g_cm3")
    density_value = None
    if density is not None and text(density) != "":
        density_value = float(density)
    values: dict[str, Any] = {
        "code": normalize_code(row.get("code")),
        "name": text(row.get("name")),
        "density_g_cm3": density_value,
        "source_title": text(row.get("source_title")),
        "source_url": text(row.get("source_url")),
    }
    for column, default in TEXT_DEFAULTS.items():
        values[column] = text(row.get(column)) or default
    values["review_status"] = (text(row.get("review_status")) or "draft").lower()
    return {column: values[column] for column in MATERIAL_COLUMNS}


def parse_json_rows(document: str) -> list[tuple[int, Any]]:
    """Parse a JSON array of row objects into 1-based ``(row, value)`` pairs.

    Raises ``ValueError`` when the document is not JSON or not an array. Rows
    that are not objects stay in the list so they can be reported per row.
    """
    try:
        payload = json.loads(document)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON body: {exc.msg}") from exc
    if not isinstance(payload, list):
        raise ValueError("JSON body must be an array of row objects")
    return list(enumerate(payload, start=1))


def parse_csv_rows(document: str) -> list[tuple[int, dict[str, Any]]]:
    """Parse a CSV document into 1-based ``(row, values)`` pairs.

    The first non-empty line is the header. Raises ``ValueError`` when the
    document is empty or the header lacks code/name/source_title/source_url.
    """
    text_document = document.lstrip("\ufeff")
    if not text_document.strip():
        raise ValueError("CSV document is empty")
    reader = csv.DictReader(io.StringIO(text_document))
    header = [(name or "").strip() for name in (reader.fieldnames or [])]
    if not header:
        raise ValueError("CSV document must include a header row")
    missing = [column for column in REQUIRED_CSV_COLUMNS if column not in header]
    if missing:
        raise ValueError(f"CSV header is missing required columns: {', '.join(missing)}")
    rows: list[tuple[int, dict[str, Any]]] = []
    for row_number, row in enumerate(reader, start=1):
        rows.append((row_number, {(key or "").strip(): value for key, value in row.items()}))
    return rows


def import_material_rows(
    con: sqlite3.Connection,
    rows: Iterable[tuple[int, Any]],
    *,
    source_format: str,
    actor: str = "baris",
) -> dict[str, Any]:
    """Validate and insert a batch inside the caller's transaction.

    Valid rows are inserted, invalid and duplicate codes are skipped and
    reported. One ``kb_events`` audit row describes the batch. The caller owns
    the commit; a row without a valid source is never inserted.
    """
    errors: list[dict[str, Any]] = []
    inserted_codes: list[str] = []
    total = 0
    # tuple unpacking keeps this working with or without a sqlite3.Row factory.
    existing = {code for (code,) in con.execute("SELECT code FROM materials")}
    statement = (
        f"INSERT INTO materials ({','.join(MATERIAL_COLUMNS)}) "
        f"VALUES ({','.join('?' for _ in MATERIAL_COLUMNS)})"
    )
    for row_number, row in rows:
        total += 1
        if not isinstance(row, Mapping):
            errors.append({"row": row_number, "field": "row", "message": "row must be an object with named fields"})
            continue
        row_errors = validate_material_row(row)
        if row_errors:
            errors.extend(
                {"row": row_number, "field": error["field"], "message": error["message"]}
                for error in row_errors
            )
            continue
        values = material_row_values(row)
        code = values["code"]
        if code in existing:
            errors.append({"row": row_number, "field": "code", "message": "duplicate code"})
            continue
        try:
            con.execute(statement, [values[column] for column in MATERIAL_COLUMNS])
        except sqlite3.IntegrityError:
            # Another writer inserted the code between SELECT and INSERT.
            existing.add(code)
            errors.append({"row": row_number, "field": "code", "message": "duplicate code"})
            continue
        existing.add(code)
        inserted_codes.append(code)
    inserted = len(inserted_codes)
    details = {
        "source_format": source_format,
        "inserted": inserted,
        "skipped": total - inserted,
        "error_count": len(errors),
        "codes": inserted_codes[:100],
    }
    con.execute(
        "INSERT INTO kb_events(event,entity_type,entity_id,actor,details) VALUES('bulk_import','material',NULL,?,?)",
        (actor, json.dumps(details)),
    )
    return {"inserted": inserted, "skipped": total - inserted, "errors": errors}
