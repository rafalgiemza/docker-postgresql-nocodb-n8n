#!/bin/bash

# Generate .env from .env.example, replacing placeholder values
# (anything starting with "change") with random 32-byte hex secrets.
# Usage: ./scripts/generate-env.sh (from the repo root)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_EXAMPLE="$REPO_ROOT/.env.example"
ENV_FILE="$REPO_ROOT/.env"

if [[ ! -f "$ENV_EXAMPLE" ]]; then
    echo "Error: .env.example not found: $ENV_EXAMPLE" >&2
    exit 1
fi

if [[ -f "$ENV_FILE" ]]; then
    read -p "Warning: $ENV_FILE already exists. Overwrite? (y/n) " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]] || exit 1
fi

: > "$ENV_FILE"
COUNT=0
while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ ^([A-Z0-9_]+)=change.*$ ]]; then
        echo "${BASH_REMATCH[1]}=$(openssl rand -hex 32)" >> "$ENV_FILE"
        COUNT=$((COUNT + 1))
    else
        echo "$line" >> "$ENV_FILE"
    fi
done < "$ENV_EXAMPLE"

echo "✅ Generated $ENV_FILE ($COUNT secret(s) randomized)"
echo "⚠️  Never commit .env to git — review non-secret values (hosts, versions) before deploying."

PLACEHOLDERS="$(grep -E '^[A-Z0-9_]+=.*PLACEHOLDER' "$ENV_FILE" | cut -d= -f1 || true)"
if [[ -n "$PLACEHOLDERS" ]]; then
    echo
    echo "⚠️  These values still need to be filled in manually (not random secrets —"
    echo "    external API keys/tokens or a fixed-length IV) or the app will run with"
    echo "    the literal placeholder string as its \"secret\":"
    echo "$PLACEHOLDERS" | sed 's/^/    - /'
    echo "    Run ./scripts/fill-env-secrets.sh to fill them in interactively."
fi
