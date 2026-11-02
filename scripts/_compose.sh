# Sourced by the other scripts. Overridable: ENV_FILE, COMPOSE_PROJECT.
cd "$(dirname "$0")/.."
ENV_FILE="${ENV_FILE:-.env.staging}"
[ -f "$ENV_FILE" ] || { echo "Missing $ENV_FILE (copy .env.staging.example and fill it in)" >&2; exit 1; }
set -a; . "$ENV_FILE"; set +a
DC="docker compose --env-file $ENV_FILE -f docker-compose.staging.yml ${COMPOSE_PROJECT:+-p $COMPOSE_PROJECT}"
psql_in() { $DC exec -T postgres psql -U "$POSTGRES_USER" -v ON_ERROR_STOP=1 "$@"; }
