# Frontend – Mobile-First Professional UI

## Stack
* TypeScript source in `app/static/src/` (`app.ts` is the app entry point, `curation.ts` holds typed factual-data validation)
* Mobile-first CSS in `app/static/style-mobile-first.css`
* Compiled with TypeScript 7.0.2 (`package.json` pins the version)
* `index.html` loads the compiled bundle at `/assets/dist/app.js`
* Multi-stage `Dockerfile` compiles the frontend in a Node stage and copies `app/static/dist` into the runtime image

## Build
```sh
./scripts/build-frontend.sh          # install deps (if needed) + compile
npm run typecheck                    # strict type check (CI gate)
npm run build                        # compile only
npm run test:frontend                # smoke test the built bundle (CI gate)
```

Generated output in `app/static/dist/` is not committed. The container build compiles it and fails fast if `app/static/dist/app.js` is missing (`test -f` in the Dockerfile).

### Why the smoke test exists
The server polls private releases and deploys automatically, so a bundle that is missing or throws at startup reaches production without a human in the loop. `tests/frontend/smoke.test.js` boots the built bundle in jsdom against a stubbed API and asserts the UI contract: every `/assets/...` reference resolves, the bundle renders materials and stats, review badges reflect `review_status`, the Review Queue hides verified materials, a verified material links its source, and an unverified material says no source is recorded. A release image is only produced after these checks pass.

> Note: environments with `NODE_ENV=production` skip devDependencies. Use `npm ci --include=dev`, which `scripts/build-frontend.sh` already does.

## TypeScript migration status
`app.ts` is a work in progress and still carries `// @ts-nocheck`; it is excluded from strict checking because it has many untyped DOM accesses. New modules such as `curation.ts` are written under `strict` and must pass `npm run typecheck`.

## Factual data
* All material entries require `source_title` and an `https://` `source_url`
* Review status: `draft` → `verified`
* Safety notes are prominent in the UI
* Bulk import via `scripts/collect_facts.py` with per-row validation
* Curation queue at `GET /api/v1/materials/needs_review`

## Development
UI changes require desktop + mobile checks before merge.
