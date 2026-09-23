# Changelog

## [0.2.1] - 2026-09-23

### Fixed
- Ship the compiled UI bundle. The web UI requested `/assets/dist/app.js`, but the frontend build excluded the entry source, so the image contained no bundle and the UI could not load. The TypeScript source had also drifted from the previously shipped script (missing the Review Queue view and bulk-import handler).
- Frontend CI now typechecks, builds and asserts that `app/static/dist/app.js` exists, so a missing bundle fails the pipeline instead of reaching production.

### Changed
- Pin the frontend toolchain to TypeScript 7.0.2 and build the frontend stage on Debian bookworm, because TypeScript 7 resolves platform-native binaries.
- Stop committing generated bundles; `app/static/dist` and `node_modules` are ignored and excluded from the image build context. The image build compiles the bundle and fails fast if it is missing.
- Remove the duplicate legacy `app/static/app.js` so the TypeScript entry point is the single source of truth.
- `scripts/build-frontend.sh` installs devDependencies explicitly (environments with `NODE_ENV=production` skip TypeScript) and verifies its outputs.

### Added
- Review Queue view backed by `GET /api/v1/materials/needs_review` for factual curation.
- Mobile-first stylesheet with professional transitions plus accessibility roles on dialogs.
- Curated material sources with safety notes (`docs/CURATED_MATERIALS.md`) and bulk factual import tooling (`scripts/collect_facts.py`).

## [0.2.0] - 2026-09-23
- Mobile-first UI work, TypeScript scaffolding and factual data collection tooling. The tag was created but CI failed, so no release image was published; superseded by 0.2.1.

## [0.1.2] - 2026-09-23
- Add Cloudflare Access app audience for kb.konverta.eu.
- Allow the DSH Kubernetes service host through the MCP DNS-rebinding protection check.

## [0.1.1] - 2026-09-23

### Added
- Searchable responsive web library for plastics, processes, and upcycling concepts.
- Source-backed material editor with draft/verified states and audit events.
- REST API and read-only DSH MCP tools on a DSH-only service port.
- Cloudflare Access JWT validation restricted to `baris@konverta.eu`.
- Single-pod MicroK8s deployment, persistent SQLite PVC, host release sync, and daily verified backups.
- CI tests, SemVer release workflow, and pinned runtime dependencies.

### Migrated
- Preserved the prototype dataset: 6 materials, 4 processes, 3 compatibility rules, and 2 projects. Existing entries are marked for source review.
