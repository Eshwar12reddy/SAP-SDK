#!/usr/bin/env bash
# Safe migration wrapper: back up first if the database already holds data, then run the
# migrate service (fresh DB -> baseline; legacy DB -> verify + stamp; versioned DB -> upgrade).
set -euo pipefail
. "$(dirname "$0")/_compose.sh"
$DC up -d postgres
until $DC exec -T postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; do sleep 2; done
HAS_DATA=$(psql_in -d "$POSTGRES_DB" -tA -c "SELECT to_regclass('public.users') IS NOT NULL")
if [ "$HAS_DATA" = "t" ]; then
  echo "Existing data detected: taking a backup before migrating"
  "$(dirname "$0")/db_backup.sh"
fi
$DC build migrate
$DC run --rm migrate
