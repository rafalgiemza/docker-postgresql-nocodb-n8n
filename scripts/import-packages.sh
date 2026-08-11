#!/bin/bash
set -e
# .env vars come from the Makefile (`include .env` + `export`), not a bash
# `source` here - patrz komentarz w seed-extra.sh.

# warianty_slajd_4.txt -> tabela package_variants (patrz nagłówek
# scripts/import-packages.py). Uruchamiane w kontenerze testimonials-import
# (nie na hosta python3) - ten sam kontener co import-testimonials.py, bo
# potrzebuje tylko `requests`, który już tam jest (patrz
# testimonials-import/README.md dlaczego kontener, nie `pip install` na hoście).
command -v docker >/dev/null 2>&1 || {
  echo "❌ Brak 'docker' w PATH."
  exit 1
}

NC_URL="${NC_LOCAL_URL:-http://localhost:8081}"
echo "⏳ Czekam, aż NocoDB odpowie pod ${NC_URL}..."
for attempt in $(seq 1 30); do
  curl -fsS -o /dev/null "${NC_URL}/" 2>/dev/null && break
  if [ "$attempt" -eq 30 ]; then
    echo "❌ NocoDB (${NC_URL}) nie odpowiada po 60s — sprawdź 'make ps' / 'make logs'."
    exit 1
  fi
  sleep 2
done

docker compose -f docker-compose.yml run --rm testimonials-import \
  python3 scripts/import-packages.py "$@"
