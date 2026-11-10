#!/usr/bin/env bash
# Run dbt with the project's .env loaded:  scripts/dbt.sh build | test | docs generate ...
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
set -a; source "$ROOT/.env"; set +a
cd "$ROOT/dbt"
exec "$ROOT/.venv/bin/dbt" "$@"
