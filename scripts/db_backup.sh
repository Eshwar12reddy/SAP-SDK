#!/usr/bin/env bash
# Logical backup (pg_dump custom format) of the staging database into ./backups/.
# Read-only against the database; safe to run at any time.
set -euo pipefail
. "$(dirname "$0")/_compose.sh"
mkdir -p backups
OUT="backups/${POSTGRES_DB}_$(date -u +%Y%m%dT%H%M%SZ).dump"
$DC exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner > "$OUT"
[ -s "$OUT" ] || { rm -f "$OUT"; echo "Backup is empty, aborting" >&2; exit 1; }
# Verify the archive is readable.
$DC exec -T postgres pg_restore --list < "$OUT" > /dev/null
chmod 600 "$OUT"
echo "Backup written and verified: $OUT ($(du -h "$OUT" | cut -f1))"
