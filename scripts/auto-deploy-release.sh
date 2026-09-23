#!/usr/bin/env bash
set -euo pipefail
repo="bnelabs/konverta-plastics-kb"
project="/srv/plastics-kb"
exec 9>/run/lock/konverta-plastics-kb-release.lock
flock -n 9 || exit 0
cd "$project"
git pull --ff-only origin main >/dev/null
tag="$(gh release view --repo "$repo" --json tagName --jq .tagName 2>/dev/null || true)"
[[ "$tag" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || exit 0
version="${tag#v}"
current="$(microk8s kubectl -n plastics-kb get deployment plastics-kb -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || true)"
[[ "$current" != "localhost:32000/plastics-kb:$version" ]] || exit 0
assets="$(gh release view "$tag" --repo "$repo" --json assets --jq '.assets[].name' 2>/dev/null || true)"
grep -Fxq "plastics-kb-$version.tar.gz" <<<"$assets" || exit 0
tmp="$(mktemp -d /tmp/kb-release.XXXXXX)"
trap 'rm -rf "$tmp"' EXIT
gh release download "$tag" --repo "$repo" --pattern "plastics-kb-$version.tar.gz" --dir "$tmp" >/dev/null
gzip -dc "$tmp/plastics-kb-$version.tar.gz" | docker load >/dev/null
docker tag "plastics-kb:$version" "localhost:32000/plastics-kb:$version"
docker push "localhost:32000/plastics-kb:$version" >/dev/null
"$project/scripts/deploy-release.sh" "$version"
