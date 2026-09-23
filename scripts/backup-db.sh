#!/usr/bin/env bash
set -euo pipefail
namespace=plastics-kb
pod="$(microk8s kubectl -n "$namespace" get pod -l app.kubernetes.io/name=plastics-kb --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')"
[[ -n "$pod" ]] || { echo 'No running KB pod found' >&2; exit 1; }
trap 'microk8s kubectl -n "$namespace" exec "$pod" -- rm -f /tmp/plastics-kb-backup.sqlite3 >/dev/null 2>&1 || true' EXIT
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="/srv/backups/plastics-kb/kb-$stamp.sqlite3"
mkdir -p /srv/backups/plastics-kb
microk8s kubectl -n "$namespace" exec "$pod" -- python -c 'import sqlite3; src=sqlite3.connect("/data/plastics-kb.sqlite3"); dst=sqlite3.connect("/tmp/plastics-kb-backup.sqlite3"); src.backup(dst); dst.close(); src.close()'
microk8s kubectl -n "$namespace" cp "$pod:/tmp/plastics-kb-backup.sqlite3" "$destination"
microk8s kubectl -n "$namespace" exec "$pod" -- rm -f /tmp/plastics-kb-backup.sqlite3
python3 -c 'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); result=c.execute("PRAGMA integrity_check").fetchone()[0]; c.close(); print(result); sys.exit(result != "ok")' "$destination"
find /srv/backups/plastics-kb -type f -name 'kb-*.sqlite3' -mtime +35 -delete
echo "SQLite backup verified: $destination"
