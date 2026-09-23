# Konverta Plastics Knowledge Base

Small, single-container knowledge library for recycled polymers. The API and web UI share one Python/FastAPI process; SQLite resides on a persistent Kubernetes volume. DSH connects to the internal Streamable HTTP MCP endpoint and receives read-only lookup tools.

## Local development

```sh
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest
KB_DB_PATH=./data/dev.sqlite3 pytest
KB_DB_PATH=./data/dev.sqlite3 uvicorn app.main:app --reload
```

The app initializes a new database from `seed/legacy-seed.sqlite3` only when it is empty. Runtime data is never part of the container image or Git history. Set `KB_DB_PATH` to a writable path to use another database.

## HTTP and MCP

- `/` web interface
- `/healthz` readiness/liveness check
- `/api/v1/materials`, `/api/v1/materials/{code}`
- `/api/v1/processes`, `/api/v1/projects`
- `/api/v1/compatibility?material_a=PET&material_b=PVC`
- `/api/v1/metrics` counts, database size, and app version
- `http://plastics-kb-mcp.plastics-kb.svc.cluster.local:8001/mcp` MCP Streamable HTTP endpoint, reachable only from the DSH namespace

MCP tools: `search_plastics_knowledge`, `get_plastic_material`, `list_recycling_processes`, and `check_polymer_compatibility`. These are read-only. Unknown compatibility pairs remain explicitly unknown. Seed facts are prototype material and must be checked against authoritative sources before operational use.

## Deployment and resources

`deploy/k8s.yaml` installs one pod in `plastics-kb`, a 1 GiB PVC, separate public and DSH-only ClusterIP services, ingress, probes, and a port-specific network policy. Resource request: 100m CPU / 192 MiB RAM; limit: 1 CPU / 768 MiB. Root filesystem is read-only; DB and SQLite WAL live on the PVC; `/tmp` is capped at 32 MiB. Image uses a slim Python base, non-root runtime, a single process, and no compiler/build cache. Public pages and APIs validate the Cloudflare Access JWT, audience, issuer, and the allowed `baris@konverta.eu` email in the app itself. The health probe reveals only service health and version.

Build a release image on the server with `scripts/build-release.sh 0.1.1`. It creates and removes an isolated BuildKit builder so it does not grow the host's shared build cache. Deploy with `scripts/deploy-release.sh 0.1.1`.

Use SemVer tags (`vMAJOR.MINOR.PATCH`). GitHub Actions runs tests and builds the production container for branch/PR changes. A release tag must point to a commit already on `main`; the release workflow reruns tests, creates a private GitHub Release, and attaches the immutable OCI image archive. A five-minute host timer downloads completed release assets, pushes the image into the local registry, and rolls MicroK8s forward; it runs on the host, so it adds no pod. Kubernetes retains the last five revisions.

SQLite is suitable for the current small, single-writer library. Do not mount this database into DSH; use the API/MCP service. A host systemd timer runs SQLite's online backup API daily, copies the snapshot to `/srv/backups/plastics-kb`, verifies `PRAGMA integrity_check`, and retains 35 days. Include a restore drill before relying on the KB as the only copy of important research.

The initial dataset is migrated from the prototype workspace. Add source records and licensing before expanding or publishing technical claims.
