#!/bin/bash
set -e
# .env vars come from the Makefile (`include .env` + `export`), not a bash
# `source` here - patrz komentarz w init-schema.sh.

# Zrzuca zywy schemat CRM (id tabel/pol, cele relacji) do pliku JSON - pelny
# kontekst i mechanizm: naglowek scripts/dump-crm-schema.py.
command -v python3 >/dev/null 2>&1 || {
  echo "❌ Brak 'python3' w PATH."
  exit 1
}
python3 -c "import requests" 2>/dev/null || {
  echo "❌ Brak modulu 'requests' dla python3 — zainstaluj: pip3 install -r fable/requirements.txt"
  exit 1
}

NC_URL="${NC_LOCAL_URL:-http://localhost:8081}"
echo "⏳ Czekam, aż NocoDB odpowie pod ${NC_URL}..."
for attempt in $(seq 1 30); do
  curl -fsS -o /dev/null "${NC_URL}/" 2>/dev/null && break
  if [ "$attempt" -eq 30 ]; then
    echo "❌ NocoDB (${NC_URL}) nie odpowiada po 60s — sprawdź NC_LOCAL_URL."
    exit 1
  fi
  sleep 2
done

python3 scripts/dump-crm-schema.py "$@"
