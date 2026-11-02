#!/usr/bin/env bash
# Restore a backup into a NEW database. Never touches or replaces the live database.
#   scripts/db_restore.sh backups/sapsdk_2026....dump [target_db_name]
# Default target: <POSTGRES_DB>_restore_<timestamp>. Refuses to use an existing database.
# To cut over to the restored copy, see docs/STAGING_DEPLOYMENT_GUIDE.md ("Restore").
set -euo pipefail
. "$(dirname "$0")/_compose.sh"
DUMP="${1:?usage: db_restore.sh <dump-file> [target_db_name]}"
[ -s "$DUMP" ] || { echo "No such backup: $DUMP" >&2; exit 1; }
TARGET="${2:-${POSTGRES_DB}_restore_$(date -u +%Y%m%d%H%M%S)}"
[[ "$TARGET" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || { echo "Invalid database name" >&2; exit 1; }
[ "$TARGET" != "$POSTGRES_DB" ] || { echo "Refusing to restore over the live database ($POSTGRES_DB)" >&2; exit 1; }
EXISTS=$(psql_in -d postgres -tA -c "SELECT 1 FROM pg_database WHERE datname = '$TARGET'")
[ -z "$EXISTS" ] || { echo "Database $TARGET already exists; choose another name" >&2; exit 1; }
psql_in -d postgres -c "CREATE DATABASE \"$TARGET\""
$DC exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$TARGET" --no-owner --exit-on-error < "$DUMP"
echo "Restored into database: $TARGET"
psql_in -d "$TARGET" -tA -c "SELECT 'users=' || count(*) FROM users"
