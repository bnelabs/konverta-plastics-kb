# Changelog

## [0.5.0] - 2026-09-24

### Added
- Materials library expanded from 6 → 12 curated resins: HDPE, ABS, PET, PP, LDPE, PS, PVC, PA, PC, PMMA, PETG, TPU with verified Wikipedia sources, density, melt range, toxicity, recyclability, safety notes, and `review_status=verified`.
- Contamination section scaffold: `contamination` table with full schema, MCP tool `search_contamination_risks`, REST `GET /api/v1/contamination`, UI Contamination tab with discrimination guide.
- Contamination scenarios doc `docs/CONTAMINATION_SCENARIOS.md` documenting 6 realistic mixed-bulk scenarios with source-backed recommendations, safety notes, and discrimination matrix.
- Contamination seed data `scripts/contamination_seed.csv` with 7 source-backed rows ready for import; runbook in `docs/CONTAMINATION_SEEDING.md`.

### Changed
- UI enhancements: severity badges in contamination cards, `contamination-guide` panel with quick tips, 44 px tap targets, safe-area insets, sticky search, mobile-first CSS.

## [Unreleased]

### Changed
- APP_VERSION default bumped to 0.5.1; UI polish verification pending.

## [0.3.0] - 2026-09-23

### Added
- `POST /api/v1/materials/bulk` imports CSV or JSON material rows with per-row validation. Only rows carrying a source title and an `https://` source URL are inserted; invalid and duplicate rows are reported, and each batch writes one `kb_events` audit row. Limits: 10 000 rows / 5 MB.
- `app/curation.py` holds one standard-library-only rule set shared by the API and `scripts/collect_facts.py`, so the two entry points cannot drift apart.
- Dialog focus trap and focus restore, `aria-current` on the active nav item, the detail dialog labelled by the rendered material name, and keyboard-operable project cards (`role="button"`, `Enter`/`Space`).
- `docs/RELEASE.md` documents the git → release → host-poll → kubectl chain, rollback and the running-version check.
- Tests for the `needs_review` queue and the materials contract, plus `tests/test_curation.py` for bulk import.
- `tests/frontend/smoke.test.js` boots the built bundle in jsdom against a stubbed API and asserts the UI contract. Frontend CI runs it after the bundle build, and the release workflow builds and smoke tests the bundle before `docker build`, so a missing or crashing bundle cannot reach a release image.

### Changed
- `app/static/src/app.ts` is fully typed and the `@ts-nocheck` suppression is gone; frontend CI fails if `ts-nocheck`/`ts-ignore`/`ts-expect-error` reappears.
- `style-mobile-first.css` is the self-sufficient primary sheet; `mobile.css` is reduced to a small enhancement layer and the legacy `style.css` remains only as a fallback.
- Accessibility: skip link, labelled landmarks and icon buttons, AA contrast tokens, visible focus rings, skeleton and error states, and reduced-motion support.

### Fixed
- Pin the smoke-test dependency to `jsdom` 26.1.0 and declare `engines.node >=20.19`. jsdom 30 requires Node `^22.22.2`, so its `undici` dependency failed on the Node 20 runners with `webidl.util.markAsUncloneable is not a function`; the image build stage still uses Node 20.
- The curation suite no longer re-runs the app lifespan, which raised `RuntimeError: StreamableHTTPSessionManager .run() can only be called once per instance` because the MCP session manager is a once-per-process singleton already owned by `tests/test_api.py`.

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
