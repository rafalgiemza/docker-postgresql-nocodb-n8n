#!/bin/bash
set -e
# .env vars (POSTGRES_USER, APP_DB) come from the Makefile (`include .env` +
# `export`), not a bash `source` here - patrz komentarz w seed-extra.sh.

# Import historycznych rekordow starego CRM (CSV) wprost do PostgreSQL, bo
# NocoDB nie pozwala ustawic created_at (.ai/rules/nocodb.md, sekcja 6).
# Pelny opis i tryby (dry-run / --apply): nagłówek scripts/import-crm-legacy.py.
# Stdlib-only python3 na hoście + `docker exec` do kontenera postgres.
command -v docker >/dev/null 2>&1 || {
  echo "❌ Brak 'docker' w PATH."
  exit 1
}

python3 -I scripts/import-crm-legacy.py "$@"
