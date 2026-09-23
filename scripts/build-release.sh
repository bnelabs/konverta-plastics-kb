#!/usr/bin/env bash
set -euo pipefail
version="${1:-}"
[[ "$version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || { echo 'Usage: build-release.sh MAJOR.MINOR.PATCH' >&2; exit 2; }
builder="kb-release-${version//./-}"
cleanup() { docker buildx rm "$builder" >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker buildx create --name "$builder" --driver docker-container --use >/dev/null
docker buildx build --builder "$builder" --pull --no-cache --load --build-arg "APP_VERSION=$version" --tag "localhost:32000/plastics-kb:$version" .
docker push "localhost:32000/plastics-kb:$version"
echo "Built and pushed localhost:32000/plastics-kb:$version (isolated builder will be removed)."
