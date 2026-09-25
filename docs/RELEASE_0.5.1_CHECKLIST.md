# v0.5.1 Release Checklist

Branch: `dsh/release-0.5.1`
Head commit: `cfb9b1c0fb732f73ab9077ebb8321a521c84e75`
CI: success on commit `cfb9b1c` – CI workflow run 36061393873, conclusion success

## Pre-merge verification

- [x] `APP_VERSION` default bumped to `0.5.1` in `app/main.py`
- [x] `CHANGELOG.md` updated with `## [0.5.0] - 2026-09-24` and Unreleased note for 0.5.1
- [x] Materials library 12 resins curated, `scripts/materials_curated.csv` validated, `docs/CURATED_MATERIALS.md` updated
- [x] Contamination scaffold implemented, MCP tools `search_contamination_risks` functional
- [x] Missing `scripts/seed_contamination.py` created and tested for syntax
- [x] `scripts/contamination_seed.csv` CSV quoting fixed for rows with commas in `impact_description`
- [x] Mobile-first UI enhancements present: sticky search, 44px tap targets, bottom tab bar, safe-area insets
- [x] Contamination guide panel and severity badges styled in `style-mobile-first.css`
- [x] Contamination cards styled: `.contamination-grid`, `.contamination-card` added for mobile/tablet/desktop
- [x] UI_SPEC.md requirements checked: single column mobile, sticky search, 44px min tap targets, progressive disclosure
- [x] Frontend build succeeds: `scripts/build-frontend.sh`, `npm run typecheck`
- [x] Python syntax check passes: `python3 -m py_compile app/main.py`
- [x] GitHub Actions CI green for branch

## Merge steps (maintainer only)

1. Open PR from `dsh/release-0.5.1` → `main`
2. Review diff: version bump, changelog, UI CSS additions, seed script addition, CSV fixes
3. Merge PR to `main` after approval
4. Push SemVer tag `v0.5.1` on the merged commit in `main`
   - Tag must match `vMAJOR.MINOR.PATCH` and be an ancestor of `main`
5. Release workflow will build `plastics-kb-0.5.1.tar.gz` and create private GitHub Release
6. Host auto-deploy timer will pick up release within 5 minutes and deploy to `kb.konverta.eu`

## Post-deploy validation

- [ ] `GET https://kb.konverta.eu/healthz` returns `{"status":"ok","version":"0.5.1"}`
- [ ] Metrics endpoint shows correct record counts
- [ ] Contamination view loads guide panel and severity badges
- [ ] Mobile 390×844 layout: bottom tab bar visible, sticky search, cards fit
- [ ] Desktop 1440×900 layout: 240px sidebar, 3-column material grid

## Notes

- Do not create/push release tags unless explicitly asked by maintainer
- Runtime DB import of contamination seed requires host access: `KB_DB_PATH=/data/plastics-kb.sqlite3 python3 scripts/seed_contamination.py scripts/contamination_seed.csv`
- Seed script inserts with `review_status=needs_review`; manual source verification required before promoting to `verified`
