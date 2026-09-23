#!/usr/bin/env bash
set -euo pipefail
version="${1:-}"
[[ "$version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || { echo 'Usage: deploy-release.sh MAJOR.MINOR.PATCH' >&2; exit 2; }
kubectl_cmd=(microk8s kubectl)
"${kubectl_cmd[@]}" apply -f deploy/k8s.yaml
"${kubectl_cmd[@]}" -n plastics-kb set image deployment/plastics-kb "plastics-kb=localhost:32000/plastics-kb:$version"
"${kubectl_cmd[@]}" -n plastics-kb set env deployment/plastics-kb "APP_VERSION=$version"
"${kubectl_cmd[@]}" -n plastics-kb rollout status deployment/plastics-kb --timeout=180s
"${kubectl_cmd[@]}" -n plastics-kb get pod -o wide
