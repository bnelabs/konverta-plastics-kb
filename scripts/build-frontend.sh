#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
npx tsc app/static/src/app.ts --target ES2020 --module ES2020 --lib ES2020,DOM --outDir app/static/dist --allowJs --noEmitOnError false
echo "Frontend built to app/static/dist"
