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

## Bulk import
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

## Quality checklist
- [ ] Source is authoritative, not a blog post
- [ ] Safety notes present for high toxicity or hazardous processing
- [ ] Melting range and density sourced
- [ ] Review status set appropriately
- [ ] Compatibility not inferred; only recorded rules inserted via admin

## Mobile data collection
The mobile-first UI provides large tap targets, bottom navigation, and a simplified editor form optimized for field use. Always capture source URL at point of collection.
