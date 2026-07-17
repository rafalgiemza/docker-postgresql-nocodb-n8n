#!/bin/bash

# First-time environment setup for a fresh server: generates .env with
# random secrets, prompts for the two values you must supply yourself up
# front (OpenRouter key, deployment domain), lists the DNS A records to add
# for the resulting *_HOST values, and reports which remaining placeholders
# need a manual step later because they depend on the stack already running
# (Beszel agent token, NocoDB/n8n API tokens).
#
# Refuses to run if ./backups already has dump files — that means this is
# a restore target (use 'make restore'), not a fresh server.
#
# Usage: ./scripts/init.sh (from the repo root)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

if compgen -G "backups/appdata_*.sql" >/dev/null; then
    echo "Error: backups/ already has dump files — this doesn't look like a fresh server." >&2
    echo "Use 'make restore' instead, or move ./backups aside if you really want a clean init." >&2
    exit 1
fi

./scripts/generate-env.sh

ENV_FILE="$REPO_ROOT/.env"

set_value() {
    awk -v name="$1" -v value="$2" -F= 'BEGIN{OFS="="} $1==name{$0=name"="value} {print}' "$ENV_FILE" >"$ENV_FILE.tmp"
    mv "$ENV_FILE.tmp" "$ENV_FILE"
}

echo
read -r -p "OpenRouter API key (https://openrouter.ai/keys), leave empty to skip: " OPENROUTER_KEY
if [[ -n "$OPENROUTER_KEY" ]]; then
    set_value OPENROUTER_API_KEY "$OPENROUTER_KEY"
    echo "✅ OPENROUTER_API_KEY set"
fi

echo
read -r -p "Domena produkcyjna (np. przyklad.pl, bez subdomeny), leave empty to skip: " DOMAIN
if [[ -n "$DOMAIN" ]]; then
    sed -i.bak "s/giemza\.dev/$DOMAIN/g" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
    echo "✅ Domena podmieniona we wszystkich *_HOST/*_URL: giemza.dev -> $DOMAIN"
fi

echo
echo "==> Rekordy DNS do dodania"
SERVER_IP="$(curl -fsSL --max-time 3 https://api.ipify.org || curl -fsSL --max-time 3 https://ifconfig.me || true)"
SERVER_IP="${SERVER_IP:-<adres IP serwera>}"
echo "Dodaj w panelu domeny rekordy A wskazujące na $SERVER_IP:"
grep -E '^[A-Z0-9_]+_HOST=' "$ENV_FILE" | while IFS='=' read -r name host; do
    printf "  %-24s A    %s\n" "$host" "$SERVER_IP"
done
echo "Bez tego Caddy nie wystawi certyfikatów Let's Encrypt przy 'make up'."

echo
echo "Gotowe. Te placeholdery zostają do ręcznego wypełnienia — wymagają, żeby"
echo "stack już działał, więc nie da się ich wygenerować teraz:"
echo "  - BESZEL_AGENT_KEY — wklej po pierwszym zalogowaniu do Beszel hub (Add System)"
echo "  - NC_API_TOKEN, N8N_API_KEY — patrz docs/init-nocodb.md, potem 'make wire-apps'"
echo "Uruchom ./scripts/fill-env-secrets.sh, żeby wypełnić je interaktywnie, gdy będą gotowe."
echo
echo "Następny krok: ustaw powyższe DNS, poczekaj na propagację, potem 'make up'"
