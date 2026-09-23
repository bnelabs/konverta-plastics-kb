# Build Plan – Konverta Plastics KB

## Repository Review Summary

**Architecture**
- Single-container FastAPI + FastMCP app in `app/main.py`
- SQLite on PVC at `KB_DB_PATH` default `/data/plastics-kb.sqlite3`, WAL mode, schema auto-created
- Static SPA UI in `app/static/`: `index.html`, `style-mobile-first.css`; TypeScript source in `app/static/src/app.ts`, built to `app/static/dist/app.js`
- Read-only MCP tools on port 8001, Streamable HTTP, DNS-rebinding protection
- REST API `/api/v1/*` with Cloudflare Access JWT gate for public routes
- Docker slim image, non-root uid 10001, read-only rootfs
- Kubernetes deployment in `deploy/k8s.yaml` : namespace plastics-kb, PVC 1Gi, NetworkPolicy for ingress + DSH, Ingress host kb.konverta.eu
- CI builds per branch/PR, SemVer tag releases auto-deploy via host poller

**Key tables**
materials, processes, material_processes, compatibility, projects, kb_events
Materials now have source_title, source_url, review_status columns. Unknown compatibility must remain unknown.

**Tests**
`tests/test_api.py` covers health/metrics, search/detail, processes/projects/compatibility, source-backed editor + duplicate guard, frontend served.

**Contributor constraints**
- Branch naming `dsh/<short-topic>`, no direct main commits
- Run `pytest` before push, UI changes need desktop + mobile checks
- Technical claims require reliable source title + URL, safety notes where relevant
- Never commit secrets, DB, backups, generated caches
- Runtime data stays in PVC

## Build Plan – UI/UX & Mobile Layout Priority

User priority: all improvements, prioritize UI/UX and mobile layout.

### Phase 1 – Setup
1. Create feature branch `dsh/ui-mobile-layout`
2. Local dev: `KB_DB_PATH=./data/dev.sqlite3 uvicorn app.main:app --reload`
3. Run `pytest` locally or rely on GitHub Actions CI
4. Baseline UI audit on desktop 1440px and mobile 390px

### Phase 2 – Mobile Navigation
- Convert ≤700px sidebar to bottom tab bar, hide horizontal scroll nav
- Keep mini brand header, make nav items 44px tap targets
- Add safe-area-inset-bottom padding for iOS home indicator
- Make search row sticky under topbar, keep hint visible

### Phase 3 – Layout & Readability
- Material/process/project grids: ensure single column, card foot stacks cleanly
- Increase spacing, keep code-pill and risk badge on same line
- Dialogs: max-height 84vh, inner scroll, larger close button hit area, ESC to close
- Editor form: sticky form-actions on mobile, inline validation messages, required source fields first

### Phase 4 – Accessibility & UX polish
- Focus outlines, aria-labels on icon buttons, focus trap in dialogs
- Loading state and toast feedback
- Keep prototype/review banners and safety notes prominent
- Do not add new technical claims without source_title + source_url + safety note

### Phase 5 – Verification & Release
- Desktop check: stats 4-col, grids 3/2-col, sidebar sticky
- Mobile check: bottom nav, tap targets ≥44px, dialogs readable
- Run `pytest`, commit changes, push branch to origin
- Open PR for maintainer review, merge to main
- No release tag unless maintainer requests

## Deliverables
- Improved responsive UI with bottom navigation on mobile
- Better dialog and form usability on touch devices
- Accessibility improvements and safe-area handling
- No changes to data model or API contracts

## Risks
- CSS is currently in single-line minified form; edits should preserve existing breakpoints and design tokens
- Do not modify MCP tools or compatibility logic; unknown pairs must stay unknown
