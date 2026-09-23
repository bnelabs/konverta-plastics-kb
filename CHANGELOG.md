# Changelog

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
