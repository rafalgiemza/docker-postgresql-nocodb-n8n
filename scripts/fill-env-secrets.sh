#!/bin/bash

# Interactively fill in .env values that generate-env.sh intentionally
# leaves as placeholders: external API keys/tokens that only exist after
# a manual step in some UI, plus CREDS_IV (needs a 16-byte secret, while
# generate-env.sh only auto-generates 32-byte ones).
# Usage: ./scripts/fill-env-secrets.sh (from the repo root)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$REPO_ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: $ENV_FILE not found — run ./scripts/generate-env.sh first" >&2
    exit 1
fi

get_value() {
    grep -m1 "^$1=" "$ENV_FILE" | cut -d= -f2-
}

set_value() {
    awk -v name="$1" -v value="$2" -F= 'BEGIN{OFS="="} $1==name{$0=name"="value} {print}' "$ENV_FILE" > "$ENV_FILE.tmp"
    mv "$ENV_FILE.tmp" "$ENV_FILE"
}

# CREDS_IV is a random secret, not something the user provides — just generate it.
if [[ "$(get_value CREDS_IV)" == *PLACEHOLDER* ]]; then
    set_value CREDS_IV "$(openssl rand -hex 16)"
    echo "✅ CREDS_IV generated (16-byte hex)"
fi

# name|hint pairs for values that genuinely need a human to fetch them.
PROMPTS="
OPENROUTER_API_KEY|API key from https://openrouter.ai/keys
NC_API_TOKEN|NocoDB: sign up as super-admin in the UI, then Account -> API Tokens
N8N_API_KEY|n8n: finish the owner setup wizard, then Settings -> API -> Create API Key
BESZEL_AGENT_KEY|Beszel hub public key, from hub UI -> Add System (after first login)
"

# Read the prompt list from fd 3, not stdin — stdin must stay free for the
# interactive `read -p` below (piping into `while read` would otherwise make
# both reads fight over the same stream).
while IFS='|' read -r name hint <&3; do
    [[ -n "$name" ]] || continue
    current="$(get_value "$name")"
    [[ "$current" == *PLACEHOLDER* ]] || continue
    echo
    echo "$name"
    echo "  $hint"
    read -r -p "  value (leave empty to skip for now): " value
    if [[ -z "$value" ]]; then
        echo "  ⏭  skipped, still a placeholder"
        continue
    fi
    set_value "$name" "$value"
    echo "  ✅ saved"
done 3<<< "$PROMPTS"

echo
REMAINING="$(grep -E '^[A-Z0-9_]+=.*PLACEHOLDER' "$ENV_FILE" | cut -d= -f1 || true)"
if [[ -n "$REMAINING" ]]; then
    echo "Still placeholders (re-run this script later once you have the values):"
    echo "$REMAINING" | sed 's/^/  - /'
else
    echo "✅ No placeholders left in $ENV_FILE"
fi
