# Frontend – Mobile-First Professional UI

## Stack
* TypeScript source in `app/static/src/`
* Mobile-first CSS in `app/static/style-mobile-first.css`
* Build with `npm install -g typescript && tsc`
* Multi-stage Dockerfile builds frontend with Node and serves via Python/FastAPI

## Factual data
* All material entries require `source_title` and `source_url https://`
* Review status: `draft` → `verified`
* Safety notes are prominent in UI
* Bulk import via `scripts/collect_facts.py` with validation

## Development
Run `scripts/build-frontend.sh` to compile TypeScript.
UI changes require desktop + mobile checks.
