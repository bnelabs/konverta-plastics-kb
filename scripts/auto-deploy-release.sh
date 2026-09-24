#!/usr/bin/env bash
# Host-side release sync. Run every five minutes by a systemd timer.
#
# It deploys the LATEST GitHub Release, not every branch or commit:
#   1. fast-forward the checkout on main (a feature branch here stops all deploys)
#   2. read the latest release tag
#   3. skip when that version is already running
#   4. require the matching plastics-kb-<version>.tar.gz asset
#   5. docker load/push into the local registry and roll the Deployment forward
#
# Test hooks (defaults match production): KB_REPO, KB_PROJECT_DIR, KB_LOCK_FILE, KUBECTL.
set -euo pipefail

repo="${KB_REPO:-bnelabs/konverta-plastics-kb}"
project="${KB_PROJECT_DIR:-/srv/plastics-kb}"
lock="${KB_LOCK_FILE:-/run/lock/konverta-plastics-kb-release.lock}"

if [[ -n "${KUBECTL:-}" ]]; then
  read -r -a kubectl_cmd <<<"${KUBECTL}"
else
  kubectl_cmd=(microk8s kubectl)
fi

mkdir -p "$(dirname "$lock")" 2>/dev/null || true
exec 9>"$lock"
flock -n 9 || exit 0
cd "$project"
git pull --ff-only origin main >/dev/null
tag="$(gh release view --repo "$repo" --json tagName --jq .tagName 2>/dev/null || true)"
[[ "$tag" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || exit 0
version="${tag#v}"
current="$("${kubectl_cmd[@]}" -n plastics-kb get deployment plastics-kb -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || true)"
[[ "$current" != "localhost:32000/plastics-kb:$version" ]] || exit 0
assets="$(gh release view "$tag" --repo "$repo" --json assets --jq '.assets[].name' 2>/dev/null || true)"
grep -Fxq "plastics-kb-$version.tar.gz" <<< "$assets" || exit 0
tmp="$(mktemp -d /tmp/kb-release.XXXXXX)"
trap 'rm -rf "$tmp"' EXIT
gh release download "$tag" --repo "$repo" --pattern "plastics-kb-$version.tar.gz" --dir "$tmp" >/dev/null
gzip -dc "$tmp/plastics-kb-$version.tar.gz" | docker load >/dev/null
docker tag "plastics-kb:$version" "localhost:32000/plastics-kb:$version"
docker push "localhost:32000/plastics-kb:$version" >/dev/null
"$project/scripts/deploy-release.sh" "$version"
