# Release and deployment

Git and production are directly connected: a SemVer tag builds a release image, and a
host timer deploys the newest published release without a human in the loop. This
document describes that chain as the files actually implement it, plus what to verify
and how to roll back.

Contributor rules (feature branch, pull request, no direct `main` commits, no tags
unless the maintainer asks) are in [AGENTS.md](../AGENTS.md).

## The chain

```
feature branch dsh/<topic>
  │
  ├─ CI           .github/workflows/ci.yml            pytest + docker build
  └─ Frontend CI  .github/workflows/frontend-ci.yml   typecheck + build + bundle assert + smoke test
  │
  ▼  pull request → maintainer review → merge to main
main
  │
  ▼  maintainer pushes SemVer tag vMAJOR.MINOR.PATCH on a commit already in main
Release workflow .github/workflows/release.yml
  pytest → npm ci / build / test:frontend → tag + ancestry validation
  → docker build --platform linux/amd64 → docker save | gzip → plastics-kb-<version>.tar.gz
  → gh release create → gh release upload
  │
  ▼  private GitHub Release with the versioned image archive
Host systemd timer (every 5 minutes, defined on the host) → scripts/auto-deploy-release.sh
  flock → git pull --ff-only origin main → gh release view (latest)
  → skip when that version already runs, or when the asset is missing
  → gh release download → docker load → tag/push localhost:32000/plastics-kb:<version>
  → scripts/deploy-release.sh <version>
  │
  ▼
microk8s kubectl apply -f deploy/k8s.yaml → set image + APP_VERSION → rollout status
  │
  ▼
kb.konverta.eu (Cloudflare Access → nginx Ingress → plastics-kb pod, SQLite on the PVC)
```

## 1. Branch, PR, merge

Per [AGENTS.md](../AGENTS.md): work on `dsh/<short-topic>`, push the branch, and merge
through a pull request. Feature branches and pull requests get CI; only `main` is
tagged.

## 2. CI on branches and pull requests

`.github/workflows/ci.yml` runs on every push to any branch and on every pull request:

1. `actions/setup-python` 3.12, then `pip install -r requirements.txt pytest`
2. `pytest` (config in `pytest.ini`: `testpaths = tests`, `pythonpath = .`, `-q`)
3. `docker build --pull --tag plastics-kb:ci .` — the real multi-stage image build,
   which also compiles the frontend bundle and asserts `app/static/dist/app.js`

`.github/workflows/frontend-ci.yml` runs on the same events but only when one of its
path filters matches: `app/static/src/**`, `app/static/index.html`, `app/static/*.css`,
`tests/frontend/**`, `tsconfig.json`, `package.json`, `package-lock.json`, `Dockerfile`,
or the workflow file itself. It runs:

1. `npm ci`
2. `npm run typecheck`
3. `npm run build`, then `test -f app/static/dist/app.js`
4. `npm run test:frontend` (`tests/frontend/smoke.test.js`), which boots the built
   bundle in jsdom against a stubbed API

A change that only touches Python files therefore does not run the frontend job, but the
release workflow always does (below).

## 3. Release workflow (tag)

`.github/workflows/release.yml` triggers on pushing a tag matching `v*.*.*`, with
`contents: write` permission. Steps, in order:

1. Checkout with `fetch-depth: 0` (full history and tags).
2. Python 3.12, `pip install -r requirements.txt pytest`, `pytest`.
3. Node 20, `npm ci`, `npm run build`, then `npm run test:frontend`. The frontend is
   built and booted in the release workflow because the host deploys this image
   automatically.
4. Validation and image build, all in one step:
   - the tag must match `^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$`
   - `git fetch origin main` and `git merge-base --is-ancestor "$GITHUB_SHA" origin/main`
     — a tag on an unmerged commit fails the release
   - `docker build --pull --platform linux/amd64 --build-arg APP_VERSION="$VERSION" --tag "plastics-kb:$VERSION" .`
   - `docker save "plastics-kb:$VERSION" | gzip -1 > "/tmp/plastics-kb-$VERSION.tar.gz"`
5. `gh release create "$RELEASE_TAG" --generate-notes` in the private
   `bnelabs/konverta-plastics-kb` repository, so the release and its asset are visible
   only to people with repository access.
6. `gh release upload "$RELEASE_TAG" "/tmp/plastics-kb-${RELEASE_TAG#v}.tar.gz"`.

Notes:

- The release is created before the asset is uploaded. In that short window the latest
  release has no asset, and the host script treats it as "not ready" and skips that tick;
  the next tick picks the asset up.
- The release asset name is exactly `plastics-kb-<version>.tar.gz` (no leading `v`), and
  it is what the host requires before it will deploy.
- `--build-arg APP_VERSION` is currently inert: the `Dockerfile` declares no
  `ARG APP_VERSION` and no matching `ENV`, so the image does not bake in a version. The
  version reported at runtime comes from the `APP_VERSION` environment variable that
  `scripts/deploy-release.sh` sets on the Deployment (the manifest default in
  `deploy/k8s.yaml` applies only until the first scripted deploy).
- Commit `5de5fa1` fixed the bundle path so the image actually contains
  `app/static/dist/app.js`; that history is recorded in [CHANGELOG.md](../CHANGELOG.md).

## 4. Host auto-deploy

A systemd timer on the server runs every five minutes and calls
`scripts/auto-deploy-release.sh`. The unit file and the five-minute interval live on the
host; only the script is in this repository. Each run, with `set -euo pipefail`:

1. `flock -n 9` on `/run/lock/konverta-plastics-kb-release.lock` — if another run holds
   the lock, the script exits 0 immediately.
2. `cd /srv/plastics-kb` and `git pull --ff-only origin main` — the host checkout is
   always the newest `main`, so `scripts/deploy-release.sh` and `deploy/k8s.yaml` are
   used from `main`, not from the tagged release.
3. `gh release view --repo bnelabs/konverta-plastics-kb --json tagName --jq .tagName`
   reads the latest release; a non-SemVer or empty result exits 0.
4. Reads the running image:
   `microk8s kubectl -n plastics-kb get deployment plastics-kb -o jsonpath='{.spec.template.spec.containers[0].image}'`.
   If it already equals `localhost:32000/plastics-kb:<version>`, the script exits 0, so
   repeated ticks are a no-op.
5. Checks the release assets for exactly `plastics-kb-<version>.tar.gz`
   (`grep -Fxq`). **A missing release asset means no deploy**: the script exits 0 and the
   next tick retries.
6. Downloads the asset into a temporary directory, `gzip -dc | docker load`, then
   `docker tag` and `docker push` to the local registry
   `localhost:32000/plastics-kb:<version>`.
7. Calls `/srv/plastics-kb/scripts/deploy-release.sh <version>`.

Because the `gh` calls redirect errors to `/dev/null` with `|| true`, a broken `gh`
authentication looks exactly like "no release published": the tick does nothing. Use the
diagnostics in section 8 when a release is not picked up.

## 5. The deploy step

`scripts/deploy-release.sh <MAJOR.MINOR.PATCH>` (it rejects anything else with exit 2):

1. `microk8s kubectl apply -f deploy/k8s.yaml`
2. `microk8s kubectl -n plastics-kb set image deployment/plastics-kb "plastics-kb=localhost:32000/plastics-kb:$version"`
3. `microk8s kubectl -n plastics-kb set env deployment/plastics-kb "APP_VERSION=$version"`
4. `microk8s kubectl -n plastics-kb rollout status deployment/plastics-kb --timeout=180s`
5. `microk8s kubectl -n plastics-kb get pod -o wide`

Steps 2 and 3 change the pod template, which creates a new Deployment revision and
replaces the pod; the trailing `rollout status` fails the script if the new pod does not
become ready within 180 seconds (in that case the old pod has already been removed,
because the strategy is `Recreate`).

What is deployed (`deploy/k8s.yaml`):

- one replica, `strategy: Recreate` (brief downtime per deploy), `revisionHistoryLimit: 5`
- `imagePullPolicy: IfNotPresent`. Each release uses a new immutable version tag; if the
  same version tag is pushed again, a node that already has it will not pull the new
  content. Bump the version instead of reusing a tag.
- 1 GiB `microk8s-hostpath` PVC mounted at `/data` (the SQLite database and its WAL),
  an `emptyDir` at `/tmp` limited to 32 MiB, read-only root filesystem, non-root uid
  10001, all capabilities dropped, seccomp `RuntimeDefault`
- startup/readiness/liveness probes on `/healthz` (ports: `http` 8000, `mcp` 8001)
- Ingress for `kb.konverta.eu` with cert-manager `letsencrypt-prod` TLS, plus a
  NetworkPolicy that only admits the `ingress` namespace to port 8000 and the
  `deepseek-harness` namespace to port 8001

## 6. Verify the running version

From the server:

```sh
# image the Deployment asks for
microk8s kubectl -n plastics-kb get deploy plastics-kb -o jsonpath='{.spec.template.spec.containers[0].image}'

# all container env values, including APP_VERSION
microk8s kubectl -n plastics-kb get deploy plastics-kb \
  -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}={.value}{"\n"}{end}'

# what the running process reports (authoritative; /healthz is exempt from the Access gate)
microk8s kubectl -n plastics-kb exec deploy/plastics-kb -- \
  python -c "import json,urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)))"
```

`/healthz` returns `{"status": "ok", "version": "<APP_VERSION>"}`. `APP_VERSION`
defaults to `0.1.0` when the environment variable is unset, so always set it as
`deploy-release.sh` does.

Release-side checks:

```sh
gh release list --repo bnelabs/konverta-plastics-kb
gh release view --repo bnelabs/konverta-plastics-kb \
  --json tagName,assets --jq '{tagName, assets: [.assets[].name]}'
git fetch --tags origin && git tag --list 'v*.*.*' --sort=-v:refname | head -5
```

## 7. Rollback

Kubernetes keeps the last five old revisions (`revisionHistoryLimit: 5` in
`deploy/k8s.yaml`), which is what `rollout undo` restores:

```sh
microk8s kubectl -n plastics-kb rollout history deployment/plastics-kb
microk8s kubectl -n plastics-kb rollout undo deployment/plastics-kb          # previous revision
microk8s kubectl -n plastics-kb rollout undo deployment/plastics-kb --to-revision=3
microk8s kubectl -n plastics-kb rollout status deployment/plastics-kb --timeout=180s
```

A rollback restores the whole pod template from that revision, so the image **and** the
`APP_VERSION` environment variable move together. Then re-run the verification commands
from section 6.

Caveats:

- **The rollback is not sticky.** The host timer compares the running image with the
  latest GitHub release; after a rollback they differ, so the next tick pushes and
  deploys the newest release again. To keep an older version running, either remove the
  bad release (or its asset) so the latest release is the good one, or stop the host
  timer while the fix is prepared.
- **The manifest is not rolled back.** `rollout undo` restores the previous pod template
  only. What lives in `deploy/k8s.yaml` (probes, resources, env defaults, Ingress,
  NetworkPolicy) is re-applied from the host's `main` checkout the next time
  `deploy-release.sh` runs, so a rollback does not restore an older manifest.
- **Data is not rolled back.** The SQLite database lives on the PVC and survives. Schema
  initialization only adds missing columns (`ALTER TABLE ... ADD COLUMN` in
  `ensure_schema`), so an older image can start against a newer database, but there is no
  down-migration and no data undo. Recovery of data is the daily
  `scripts/backup-db.sh` snapshot path (`/srv/backups/plastics-kb`, integrity-checked,
  35-day retention), which is a separate restore exercise.
- `Recreate` means a short outage during both the deploy and the rollback.

## 8. Failure modes

| Condition | What the files do |
| --- | --- |
| Tag does not match `vMAJOR.MINOR.PATCH` | Release workflow validation fails; and `auto-deploy-release.sh` exits 0 on its own regex check |
| Tag is not an ancestor of `origin/main` | `git merge-base --is-ancestor` fails, so no image and no release |
| `pytest` or the frontend build/smoke test fails | Release workflow stops before `gh release create`; no release, so the host deploys nothing (this is the recorded history of `v0.2.0`, which was superseded by `v0.2.1`) |
| Release exists but `plastics-kb-<version>.tar.gz` is missing | The exact-name `grep -Fxq` check fails and the script exits 0 — no deploy, retried next tick |
| Release asset is uploaded a few seconds after the release | The tick in that window skips; a later tick deploys it |
| Deployment already runs the release version | Exit 0, no docker or kubectl work |
| Two timer ticks overlap | `flock -n` makes the second exit 0 |
| `git pull --ff-only` fails (diverged or dirty `/srv/plastics-kb`) | Script exits non-zero before any download; the running pod is unchanged |
| `gh` is unauthenticated, or the API fails | Errors are swallowed; the tick behaves as "no release" and deploys nothing |
| `docker load`/`docker push` fails | Script exits non-zero; `deploy-release.sh` is not reached and the running pod is unchanged |

Diagnostics on the host:

```sh
systemctl list-timers --all          # find the release timer unit
journalctl -u <release-timer-unit>   # logs of the timer / last run
gh auth status --hostname github.com
docker image ls | grep plastics-kb
```

The unit name is host configuration and is not part of this repository.

## 9. Access control and observability

- `kb.konverta.eu` is behind Cloudflare Access. The app enforces it as well: for every
  path except the exact `/healthz`, when `CF_ACCESS_AUD` is set the middleware requires a
  `cf-access-jwt-assertion` header, validates it against the `CF_ACCESS_TEAM_DOMAIN`
  JWKS with the configured audience and issuer, and rejects any other email than
  `CF_ACCESS_EMAIL` (`baris@konverta.eu` in `deploy/k8s.yaml`). Missing or invalid tokens
  get 401, a valid token for another account gets 403.
- `/healthz` is exempt so the Kubernetes probes work from inside the pod; it reports only
  `status` and `version`.
- `GET /api/v1/metrics` is **not** exempt, so it needs an Access session or an in-cluster
  call. It returns `version`, `uptime_seconds`, `database_bytes`, record counts, and the
  last `kb_events` row.
- Public pages and APIs therefore behave differently through Cloudflare than inside the
  cluster; use the in-cluster `/healthz` check in section 6 to separate a deployment
  problem from an access problem.

## 10. Manual server-side build and deploy

Both commands run on the server from the checkout at `/srv/plastics-kb`:

```sh
scripts/build-release.sh 0.2.2   # isolated buildx builder, --pull --no-cache, pushes localhost:32000/plastics-kb:0.2.2
scripts/deploy-release.sh 0.2.2  # apply manifest, set image + APP_VERSION, wait for the rollout
```

`build-release.sh` creates its own `docker-container` builder and removes it on exit, so
it does not grow the host's shared build cache. It does not create a GitHub release, and
it is the escape hatch when a release asset needs to be rebuilt manually.

## Scope of this document

- The systemd unit, its five-minute interval, the `/run/lock` path ownership, the
  `gh`/`docker`/`microk8s` credentials, and the Cloudflare Access application policy are
  host or account configuration. This repository contains the scripts and the manifest
  only.
- CI runs these tests in GitHub Actions. The DSH workspace sandbox is not a substitute
  for CI: changes to tests, Python dependencies or workflows must be validated by the
  workflows above before a tag is created.
