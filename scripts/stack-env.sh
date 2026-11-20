#!/bin/bash
# Prints .env.example with a random value for every empty internal secret.
# An internal secret is a name ending in _PASSWORD, _SECRET, _TOKEN or _KEY, unless it belongs to
# an outside provider (listed in EXTERNAL). 32 bytes in hex suits all of them, HUB_CREDENTIALS_KEY included.
#   scripts/stack-env.sh [path/to/.env.example]
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SOURCE=${1:-$ROOT/.env.example}
EXTERNAL=" OPENARGA_AI_KEY OPENARGA_BRAVE_KEY GOOGLE_CLIENT_SECRET OPENARGA_OIDC_CLIENT_SECRET "

version=$(git -C "$ROOT" describe --tags 2>/dev/null || true)
version=${version#v}
[[ "$version" =~ ^[0-9] ]] || version=""

while IFS= read -r line; do
  if [[ "$line" == "OPENARGA_VERSION=" && -n "$version" ]]; then
    echo "OPENARGA_VERSION=$version"
    continue
  fi
  if [[ "$line" =~ ^([A-Z0-9_]+)=$ ]]; then
    name=${BASH_REMATCH[1]}
    if [[ "$name" =~ (PASSWORD|SECRET|TOKEN|KEY)$ ]] && [[ "$EXTERNAL" != *" $name "* ]]; then
      echo "$name=$(openssl rand -hex 32)"
      continue
    fi
  fi
  echo "$line"
done <"$SOURCE"
