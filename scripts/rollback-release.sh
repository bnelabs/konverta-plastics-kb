#!/usr/bin/env bash
# Durable rollback to an earlier KB release.
#
# Why this exists: `microk8s kubectl rollout undo` does not stick. The host timer
# deploys the LATEST GitHub Release every five minutes, so it re-converges onto
# the version you just rolled away from, usually within five minutes.
#
# The timer chooses its version with `gh release view` (newest published release,
# regardless of assets). So a rollback only sticks when the target release is the
# newest one left. This script withdraws the releases published after the target,
# then asks the normal sync to converge onto it.
#
# Usage:
#   rollback-release.sh --list                    # releases + what is running now
#   rollback-release.sh --to v0.2.1               # interactive confirmation
#   rollback-release.sh --to v0.2.1 --yes         # no prompt (for automation)
#   rollback-release.sh --to v0.2.1 --yes --delete-tags
#   rollback-release.sh --to v0.2.1 --yes --no-deploy   # withdraw only
#
# Test hooks (defaults match production): KB_REPO, KB_PROJECT_DIR, KUBECTL.
set -euo pipefail

repo="${KB_REPO:-bnelabs/konverta-plastics-kb}"
project="${KB_PROJECT_DIR:-/srv/plastics-kb}"

if [[ -n "${KUBECTL:-}" ]]; then
  read -r -a kubectl_cmd <<<"${KUBECTL}"
else
  kubectl_cmd=(microk8s kubectl)
fi

die() { echo "$*" >&2; exit 1; }

running_image() {
  "${kubectl_cmd[@]}" -n plastics-kb get deployment plastics-kb \
    -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || true
}

list_releases() {
  # Newest last, same ordering the timer's `gh release view` uses.
  gh release list --repo "$repo" --limit 100 --json tagName,publishedAt,isLatest \
    --jq '.[] | "\(.publishedAt)\t\(.tagName)\t\(.isLatest)"' 2>/dev/null | sort
}

usage() {
  sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

action=""
target=""
assume_yes=""
delete_tags=""
do_deploy="1"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --list) action="list"; shift ;;
    --to) action="rollback"; target="${2:-}"; shift 2 ;;
    --to=*) action="rollback"; target="${1#--to=}"; shift ;;
    --yes|-y) assume_yes="1"; shift ;;
    --delete-tags) delete_tags="1"; shift ;;
    --no-deploy) do_deploy=""; shift ;;
    -h|--help) usage 0 ;;
    *) die "Unknown argument: $1 (try --help)" ;;
  esac
done

[[ -n "$action" ]] || usage 2

all="$(list_releases)"
[[ -n "$all" ]] || die "No releases found in $repo, or gh is not authenticated."

if [[ "$action" == "list" ]]; then
  printf '%-10s %-22s %s\n' "RELEASE" "PUBLISHED" "ASSET"
  while IFS=$'\t' read -r published tag is_latest; do
    asset="$(gh release view "$tag" --repo "$repo" --json assets --jq '.assets[].name' 2>/dev/null | head -n1)"
    printf '%-10s %-22s %s%s\n' "$tag" "$published" "${asset:-<no asset>}" \
      "$([[ "$is_latest" == "true" ]] && echo '   <- latest (this is what the timer deploys)')"
  done <<< "$all"
  echo
  echo "running: $(running_image)"
  exit 0
fi

# --- rollback -----------------------------------------------------------------
target="${target#v}"
[[ "$target" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] \
  || die "Usage: rollback-release.sh --to MAJOR.MINOR.PATCH (got '${target:-<empty>}')"
tag="v$target"

target_at="$(awk -F'\t' -v t="$tag" '$2==t {print $1}' <<< "$all")"
[[ -n "$target_at" ]] || die "Release $tag not found in $repo. Use --list to see what is available."

assets="$(gh release view "$tag" --repo "$repo" --json assets --jq '.assets[].name' 2>/dev/null || true)"
grep -Fxq "plastics-kb-$target.tar.gz" <<< "$assets" \
  || die "Release $tag has no plastics-kb-$target.tar.gz asset. The timer would skip it, so rolling back to it cannot work. Pick a release with an image archive."

newer="$(awk -F'\t' -v at="$target_at" '$1 > at {print $2}' <<< "$all")"

echo "Target release : $tag (published $target_at)"
echo "Running image  : $(running_image)"
if [[ -n "$newer" ]]; then
  echo "Will withdraw  : $(tr '\n' ' ' <<< "$newer")"
  echo "                 (git tags are kept unless --delete-tags is given)"
else
  echo "Will withdraw  : nothing, $tag is already the newest release"
fi
echo

if [[ -n "$newer" && -z "$assume_yes" ]]; then
  if [[ -t 0 ]]; then
    read -r -p "Withdraw those releases so the timer converges onto $tag? [y/N] " reply
    [[ "$reply" =~ ^[Yy]$ ]] || die "Aborted; nothing was changed."
  else
    die "Refusing to delete releases without confirmation. Re-run with --yes."
  fi
fi

while IFS= read -r newer_tag; do
  [[ -n "$newer_tag" ]] || continue
  echo "Withdrawing release $newer_tag"
  if [[ -n "$delete_tags" ]]; then
    gh release delete "$newer_tag" --repo "$repo" --yes --cleanup-tag
  else
    gh release delete "$newer_tag" --repo "$repo" --yes
  fi
done <<< "$newer"

if [[ -z "$do_deploy" ]]; then
  echo
  echo "Releases withdrawn. The five-minute timer will converge onto $tag by itself."
  exit 0
fi

[[ -x "$project/scripts/auto-deploy-release.sh" ]] \
  || die "Cannot find $project/scripts/auto-deploy-release.sh; re-run with --no-deploy and let the timer converge."

echo
echo "Converging onto $tag now"
"$project/scripts/auto-deploy-release.sh"

echo
echo "Running image  : $(running_image)"
echo "Note: the image tag can lag the app's /healthz APP_VERSION until the rollout completes."
