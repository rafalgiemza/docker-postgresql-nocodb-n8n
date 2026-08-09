#!/bin/bash
set -e
# .env vars come from the Makefile (`include .env` + `export`), not a bash
# `source` here — bash's own parser chokes on unquoted values containing
# spaces (e.g. BESZEL_AGENT_KEY's ssh-ed25519 value), unlike Make's.

# Tworzy CAŁY schemat CRM (16 tabel + relacje) w NocoDB przez Meta API v3/v2 —
# pełny kontekst, wymogi i to, co zostaje do wyklikania ręcznie, patrz nagłówek
# scripts/init-schema.py. Wymaga uprzedniego ręcznego podłączenia źródła
# appdata/crm w NocoDB UI (docs/hard-reset.md, Krok 0).
command -v python3 >/dev/null 2>&1 || {
  echo "❌ Brak 'python3' w PATH."
  exit 1
}
python3 -c "import requests" 2>/dev/null || {
  echo "❌ Brak modułu 'requests' dla python3 — zainstaluj: pip3 install -r docs/archive/fable/requirements.txt"
  exit 1
}

# NocoDB healthcheck (fragments/nocodb.yml) daje mu do ~100s na start
# (interval 10s * retries 10) - zaraz po `make up` kontener bywa jeszcze
# "health: starting" i skrypt niżej pada z ConnectionError zamiast poczekać.
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

python3 scripts/init-schema.py "$@"
