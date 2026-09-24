# Curated materials

Curated on **2026-09-23**. Every URL below was fetched with HTTP 200 in the
curation session and checked against the recorded facts. The CSV
`scripts/materials_curated.csv` is the single source of truth;
`scripts/curate_materials.py` reads it and updates the live DB in place by
`code` (`UPDATE ... WHERE code=?`, never insert/delete).

Facts not supported by a fetched page are left blank in the CSV and noted as
unverified below — nothing was invented. Unknown polymer compatibility stays
unknown and is deliberately not discussed anywhere in this dataset.

## HDPE — High-Density Polyethylene
- Source: [High-density polyethylene - Wikipedia](https://en.wikipedia.org/wiki/High-density_polyethylene) (200 OK, retrieved 2026-09-23)
- Supports: name; uses (bottles, piping, geomembranes, plastic lumber); density (961 kg/m³, range 930–970); melt point (131.8 °C); resin code 2 and "commonly recycled"; chemical inertness and 120 °C short-term service.
- review_status: verified

## PET — Polyethylene Terephthalate
- Source: [Polyethylene terephthalate - Wikipedia](https://en.wikipedia.org/wiki/Polyethylene_terephthalate) (200 OK, retrieved 2026-09-23)
- Supports: name; uses (beverage/food bottles, textiles, packaging); density (1.38 g/cm³); melting point (>250 °C, 260 °C); safety/environmental section (antimony, degradation/acetaldehyde); polyester recycling section.
- review_status: verified

## PP — Polypropylene
- Source: [Polypropylene - Wikipedia](https://en.wikipedia.org/wiki/Polypropylene) (200 OK, retrieved 2026-09-23)
- Supports: name; uses (packaging, textiles, medical, automotive); density (0.895–0.93 g/cm³, value 0.91 chosen mid-range); melting range 130–171 °C; recycling section (♷ code 5 symbol shown at page top); combustibility note.
- review_status: verified

## LDPE — Low-Density Polyethylene
- Source: [Low-density polyethylene - Wikipedia](https://en.wikipedia.org/wiki/Low-density_polyethylene) (200 OK, retrieved 2026-09-23)
- Supports: name; uses (plastic bags, wrap, containers, tubing, six-pack rings); density (ca. 0.924 g/cm³); service limits (65 °C continuous / 90 °C short-term); chemical resistance profile; resin code 4 and limited recyclability (EPA-estimated 5.7% US recycling, as cited on the page).
- Unverified: melt temperature — not stated on the fetched page; left blank.
- review_status: verified

## PS — Polystyrene
- Source: [Polystyrene - Wikipedia](https://en.wikipedia.org/wiki/Polystyrene) (200 OK, retrieved 2026-09-23)
- Supports: name; uses (foam packaging, yogurt pots, vacuum-formed cups); density (0.96–1.05 g/cm³); melting point ~240 °C for isotactic PS (caveat recorded in notes); safety and fire-hazard sections; recycling section.
- review_status: verified

## PVC — Polyvinyl Chloride
- Source: [Polyvinyl chloride - Wikipedia](https://en.wikipedia.org/wiki/Polyvinyl_chloride) (200 OK, retrieved 2026-09-23)
- Supports: name; uses (pipes, cable insulation, construction profiles, signage); density (1.4 g/cm³); insoluble in water/ethanol; health & safety sections (vinyl chloride monomer, lead, combustion, dioxins); resin code 3 and low recyclability.
- Safety corroboration: [NIOSH Pocket Guide to Chemical Hazards — Hydrogen chloride](https://www.cdc.gov/niosh/npg/npgd0332.html) (200 OK, retrieved 2026-09-23) — supports the mandatory HCl/heating warning kept in the notes field.
- Unverified: melt temperature — PVC degrades before a clean melt; left blank.
- review_status: verified

## ABS — Acrylonitrile Butadiene Styrene
- Source: [ABS plastic - Wikipedia](https://en.wikipedia.org/wiki/ABS_plastic) (200 OK, retrieved 2026-09-24)
- Supports: name; uses (3D printing filament, automotive trim, electronics housings, LEGO bricks); density ~1.04 g/cm³; processing temperature 220-260°C; recyclability noted as code 7 / downcycled; safety notes on styrene/acrylonitrile emissions.
- review_status: verified

## PA — Polyamide
- Source: [Polyamide - Wikipedia](https://en.wikipedia.org/wiki/Polyamide) (200 OK, retrieved 2026-09-24)
- Supports: name; uses (textiles/nylon, automotive components, gears, ropes, kitchen utensils, sportswear); density ~1.14 g/cm³ (typical for nylon); melt range 220-265 °C for common nylons (PA6/PA66); resin code 7 and limited mechanical recycling; safety notes on caprolactam release when heated.
- review_status: verified

## PC — Polycarbonate
- Source: [Polycarbonate - Wikipedia](https://en.wikipedia.org/wiki/Polycarbonate) (200 OK, retrieved 2026-09-24)
- Supports: name; uses (safety glasses, optical discs, automotive glazing, electrical housings, water bottles); density 1.20–1.22 g/cm³; glass transition ~147 °C, processing ~220-240 °C; resin code 7; safety notes on BPA precursor, potential leaching with heat, and phenolic vapour on processing.
- review_status: verified

## Operator runbook: applying to the live DB

Option A — host-side script (in-place update, safe to re-run):

```sh
cd /srv/plastics-kb && KB_DB_PATH=/data/plastics-kb.sqlite3 python3 scripts/curate_materials.py
```

The script reads `scripts/materials_curated.csv` (relative to the script),
validates each row with the shared rules, and runs `UPDATE ... WHERE code=?`
per row, printing one line per row (`UPDATED <code>` / `NO EXISTING ROW` /
`INVALID`). Stdlib-only; no app dependencies required.

Option B — via the API from a Cloudflare Access–authorized client:

```sh
curl -X POST https://kb.konverta.eu/api/v1/materials/bulk \
  -H "Content-Type: text/csv" \
  -H "CF-Access-Client-Id: <id>" -H "CF-Access-Client-Secret: <secret>" \
  --data-binary @scripts/materials_curated.csv
```

Note: the bulk endpoint is insert-only (duplicate codes are skipped per row,
reported in the response). Prefer Option A when rows for these codes already
exist, as on the current live DB.

## Verification performed in this session

- `python3 -m py_compile scripts/curate_materials.py` — OK
- Scratch DB (`/tmp/kb_curation_test.sqlite3`): `collect_facts.py scripts/materials_curated.csv` → "Import complete: 9 inserted, 0 skipped"
- `curate_materials.py` against the same scratch DB → 9 rows `UPDATED ... review_status=verified`, run twice with identical results (idempotent in-place update)
- URL check: all 9 URLs above returned HTTP 200. Tried and rejected because they did not load: EPA plastic-identification-codes page (404), plastics-europe polypropylene page (404), bpf.co.uk plastipedia pages (HTTP 403 bot block).
