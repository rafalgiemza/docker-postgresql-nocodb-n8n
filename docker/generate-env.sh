#!/bin/bash

# Generate .env from .env.example, replacing placeholder values
# (anything starting with "change") with random 32-byte hex secrets.
# Usage: ./generate-env.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_EXAMPLE="$SCRIPT_DIR/.env.example"
ENV_FILE="$SCRIPT_DIR/.env"

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
        ((COUNT++))
    else
        echo "$line" >> "$ENV_FILE"
    fi
done < "$ENV_EXAMPLE"

echo "✅ Generated $ENV_FILE ($COUNT secret(s) randomized)"
echo "⚠️  Never commit .env to git — review non-secret values (hosts, versions) before deploying."
