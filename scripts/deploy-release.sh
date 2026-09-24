#!/usr/bin/env bash
# Deploy one released image version to MicroK8s.
#
# Usage: deploy-release.sh MAJOR.MINOR.PATCH
#
# The manifest holds the placeholder __KB_RELEASE__ for both the image tag and
# APP_VERSION. Rendering it before `kubectl apply` matters: applying the raw
# manifest and then patching the image would first roll the Deployment back to
# whatever version the file happens to name, briefly starting an old pod. With
# one rendered apply the spec changes exactly once.
set -euo pipefail

version="${1:-}"
[[ "$version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || { echo 'Usage: deploy-release.sh MAJOR.MINOR.PATCH' >&2; exit 2; }

project="${KB_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
manifest="$project/deploy/k8s.yaml"
[[ -f "$manifest" ]] || { echo "Manifest not found: $manifest" >&2; exit 2; }

# The timer runs this as root on the host; kubectl is reached through MicroK8s.
if [[ -n "${KUBECTL:-}" ]]; then
  read -r -a kubectl_cmd <<<"${KUBECTL}"
else
  kubectl_cmd=(microk8s kubectl)
fi

if ! grep -q '__KB_RELEASE__' "$manifest"; then
  echo "Refusing to deploy: $manifest has no __KB_RELEASE__ placeholder." >&2
  echo "A hardcoded version there would be applied before the image is set." >&2
  exit 2
fi

rendered="$(mktemp "${TMPDIR:-/tmp}/kb-deploy-XXXXXX.yaml")"
trap 'rm -f "$rendered"' EXIT
sed "s|__KB_RELEASE__|${version}|g" "$manifest" >"$rendered"

applied_version="$(grep -c "plastics-kb:${version}\$" "$rendered" || true)"
[[ "$applied_version" -ge 1 ]] || { echo "Rendered manifest does not name plastics-kb:${version}" >&2; exit 2; }

"${kubectl_cmd[@]}" apply -f "$rendered"
# Idempotent confirmations: they are no-ops when the rendered manifest is correct
# and repair drift if somebody edited the Deployment by hand.
"${kubectl_cmd[@]}" -n plastics-kb set image deployment/plastics-kb "plastics-kb=localhost:32000/plastics-kb:$version"
"${kubectl_cmd[@]}" -n plastics-kb set env deployment/plastics-kb "APP_VERSION=$version"
"${kubectl_cmd[@]}" -n plastics-kb rollout status deployment/plastics-kb --timeout=180s
"${kubectl_cmd[@]}" -n plastics-kb get deployment plastics-kb \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
"${kubectl_cmd[@]}" -n plastics-kb get pod -o wide
