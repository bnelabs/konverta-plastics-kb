# Contamination Seeding Runbook

## Purpose
Seed source-backed contamination risks from `docs/CONTAMINATION_SCENARIOS.md` into the live KB `contamination` table.

## Seed file
`scripts/contamination_seed.csv` contains columns:
`contaminant_name,material_code,impact_description,safety_notes,source_title,source_url,review_status`

## Host import
The contamination table requires `material_id` FK. Import script maps `material_code` → `materials.id` and inserts rows with `review_status` as-is.

Example host run:
```sh
cd /srv/plastics-kb
KB_DB_PATH=/data/plastics-kb.sqlite3 python3 scripts/seed_contamination.py scripts/contamination_seed.csv
```

## Validation
* Every row must have a valid https `source_url` and non-empty `safety_notes`.
* Unknown compatibility must remain unknown; do not invent risks.
* After import, verify via `GET /api/v1/contamination` and MCP `search_contamination_risks`.

## Review
Rows are seeded with `review_status=needs_review`. Promote to `verified` after manual source check.
