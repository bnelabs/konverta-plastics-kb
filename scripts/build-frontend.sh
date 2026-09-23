#!/usr/bin/env bash
# Build the TypeScript frontend into app/static/dist (served at /assets/dist/).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -x node_modules/.bin/tsc ]; then
  # --include=dev: NODE_ENV=production environments would otherwise skip TypeScript.
  npm install --include=dev --no-audit --no-fund
fi

npm run build

for required in app/static/dist/app.js app/static/dist/curation.js; do
  if [ ! -f "$required" ]; then
    echo "ERROR: expected build output missing: $required" >&2
    exit 1
  fi
done

echo "Frontend built to app/static/dist"
