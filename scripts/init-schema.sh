#!/bin/bash
set -e
# .env vars come from the Makefile (`include .env` + `export`), not a bash
# `source` here — bash's own parser chokes on unquoted values containing
# spaces (e.g. BESZEL_AGENT_KEY's ssh-ed25519 value), unlike Make's.

# Tworzy CAŁY schemat CRM (16 tabel + relacje) w NocoDB przez Meta API v3/v2 —
# pełny kontekst, wymogi i to, co zostaje do wyklikania ręcznie, patrz nagłówek
# scripts/init-schema.py. Wymaga uprzedniego `make wire-apps`.
command -v python3 >/dev/null 2>&1 || {
  echo "❌ Brak 'python3' w PATH."
  exit 1
}
python3 -c "import requests" 2>/dev/null || {
  echo "❌ Brak modułu 'requests' dla python3 — zainstaluj: pip3 install -r fable/requirements.txt"
  exit 1
}

python3 scripts/init-schema.py "$@"
