# Factual Data Collection Guide

## Principles
- All material claims must have a reliable source
- Source title and HTTPS URL are required
- Safety notes must be included where relevant
- Unknown polymer compatibility stays unknown – never infer
- Entries start as `draft`, move to `verified` after review

## Manual entry via UI
1. Open Materials → Add material
2. Fill resin code, name, common uses, melt temp, density, toxicity, recyclability, notes
3. Provide source_title and source_url starting with https://
4. Set review_status to draft or verified
5. Save – client validation enforces source requirements

## Bulk import from the command line
Use `scripts/collect_facts.py`

```sh
KB_DB_PATH=./data/dev.sqlite3 python scripts/collect_facts.py data/materials.csv --review-status draft
```

CSV columns: code,name,common_uses,melt_temp_c,density_g_cm3,toxicity_level,recyclability,notes,source_title,source_url,review_status

Validation rules:
- code uppercase alphanumeric/hyphen
- source_url must start with https://
- source_title required
- review_status draft|verified
- density numeric 0-100

Rows failing validation are skipped with error output.

## Bulk import via API
`POST /api/v1/materials/bulk` accepts a CSV document or a JSON array of row objects and applies **exactly the same rules** as `scripts/collect_facts.py`. Both entry points import the shared implementation in `app/curation.py`, so the rules cannot drift apart. The route is protected by the same Cloudflare Access gate as every other `/api/v1` route.

### Request
Send one of:

| Body | Content-Type | Notes |
| --- | --- | --- |
| CSV document (text) | `text/csv` | Header row required; must contain at least `code,name,source_title,source_url`. Optional columns: `common_uses,melt_temp_c,density_g_cm3,toxicity_level,recyclability,notes,review_status`. |
| JSON array of row objects | `application/json` | Same field names as the CSV columns; missing optional fields use the defaults below. |

If the content type is neither CSV nor JSON, the body is sniffed: a document starting with `[` or `{` is treated as JSON, anything else as CSV. Bodies must be UTF-8.

Defaults for omitted optional fields: `common_uses=""`, `melt_temp_c=""`, `density_g_cm3=NULL`, `toxicity_level="Not rated"`, `recyclability="Not recorded"`, `notes=""`, `review_status="draft"`.

### Validation rules (identical to the CLI importer)
| Field | Rule | Error message |
| --- | --- | --- |
| `code` | Required, letters/digits/hyphens only, normalised to upper case | `code must be alphanumeric/hyphen` |
| `name` | Required, at least 2 characters | `name too short` |
| `source_title` | Required, at least 2 characters | `source_title required` |
| `source_url` | Required, must start with `https://` | `source_url must start with https://` |
| `review_status` | `draft` or `verified` (default `draft`) | `review_status must be draft or verified` |
| `density_g_cm3` | Numeric within 0..100 when present | `density not numeric` / `density out of range` |

A row is reported as `duplicate code` when the code already exists or repeats earlier in the same batch. This endpoint only writes `materials`: it never creates compatibility rules, so an unknown polymer pair stays unknown.

### Response
`200 OK`

```json
{"inserted": 2, "skipped": 1, "errors": [{"row": 2, "field": "source_title", "message": "source_title required"}]}
```

- `row` is the 1-based index of the supplied data row (the CSV header is not counted; for JSON it is the array index + 1).
- Valid rows are inserted; invalid and duplicate rows are skipped and listed in `errors`. A partially valid batch still inserts the valid rows, and a row without a valid source is never inserted.
- Exactly one `kb_events` audit row is written per accepted batch: `event='bulk_import'`, `entity_type='material'`, `actor` set to the authenticated Cloudflare Access email (or `local-dev` when the gate is off, e.g. in dev/tests), and a JSON `details` value with `source_format`, `inserted`, `skipped`, `error_count` and the inserted `codes` (first 100).

Other status codes: `400` malformed document (invalid JSON, JSON that is not an array, empty CSV, missing required CSV header columns, non-UTF-8 body), `413` batch over the limits (10000 rows or 5000000 bytes), `401`/`403` Cloudflare Access denial.

### Examples
```sh
curl -X POST https://kb.konverta.eu/api/v1/materials/bulk \
  -H 'Content-Type: text/csv' \
  --data-binary $'code,name,source_title,source_url,review_status\nPC,Polycarbonate,Example technical handbook,https://example.org/pc,draft\n'

curl -X POST https://kb.konverta.eu/api/v1/materials/bulk \
  -H 'Content-Type: application/json' \
  -d '[{"code":"PC","name":"Polycarbonate","source_title":"Example technical handbook","source_url":"https://example.org/pc","review_status":"draft"}]'
```

## Admin endpoints (processes, compatibility, audit log)

All `/api/v1` writes are behind the Cloudflare Access gate and the write rate limiter (30 write requests per 60 seconds per authenticated email — or per client host when the gate is off — with `429` + `Retry-After`; tune via `KB_RATE_LIMIT_MAX` / `KB_RATE_LIMIT_WINDOW`). Every write records a `kb_events` audit row whose `actor` is the authenticated email (`local-dev` when the gate is off).

### Audit log read API
`GET /api/v1/events?entity_type=material&entity_id=<id>&limit=50` returns audit rows newest first as a JSON array with exactly `id`, `event`, `entity_type`, `entity_id`, `actor`, `details`, `created_at`. All query parameters are optional. The frontend history view consumes this shape.

### Processes
- `POST /api/v1/processes` → `201`. Body: `name` (required, 2–160 chars), `description`, `equipment_needed` (optional), `safety_precautions` (**required and non-empty** — safety-first; a missing or blank value fails with `422`). Writes a `kb_events` row (`created`/`process`).
- `PUT /api/v1/processes/{id}` → `200`, or `404` when the process does not exist. Same body rules. Writes a `kb_events` row (`updated`/`process`).

### Compatibility
`POST /api/v1/compatibility` → `201`. Body: `material_a`, `material_b` (resin codes), `status`, `description` (required, at least 10 characters).

- Both codes must exist in `materials`, otherwise `404` naming the unknown code(s). An unknown pair is **never** auto-created; compatibility stays unknown until a source-backed rule is recorded here.
- `status` is a controlled vocabulary: `Compatible`, `Incompatible`, `Blends with additives`, `Conditional`. Any other value fails with `400`.
- The pair is stored in canonical id order (smaller id first), so posting `A,B` and later `B,A` updates the **same row** (upsert). Response: `{"material_a", "material_b", "compatibility_status", "description"}`. Writes a `kb_events` row (`created` or `updated`/`compatibility`).

```sh
curl -X POST https://kb.konverta.eu/api/v1/compatibility \
  -H 'Content-Type: application/json' \
  -d '{"material_a":"HDPE","material_b":"PP","status":"Incompatible","description":"Phase separation reduces mechanical strength; see technical datasheet."}'
```


## Quality checklist
- [ ] Source is authoritative, not a blog post
- [ ] Safety notes present for high toxicity or hazardous processing
- [ ] Melting range and density sourced
- [ ] Review status set appropriately
- [ ] Compatibility not inferred; only recorded rules inserted via admin

## Mobile data collection
The mobile-first UI provides large tap targets, bottom navigation, and a simplified editor form optimized for field use. Always capture source URL at point of collection.
