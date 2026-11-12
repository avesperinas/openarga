#!/usr/bin/env bash
set -euo pipefail

ID="${1:?uso: new-module.sh <id> <nombre>}"
NAME="${2:-$ID}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/modules/$ID"

[[ "$ID" =~ ^[a-z][a-z0-9_]*$ ]] || { echo "id inválido: solo minúsculas, dígitos y _"; exit 1; }
[[ -d "$DEST" ]] && { echo "el módulo $ID ya existe"; exit 1; }
[[ "$ID" == "kernel" ]] && { echo "'kernel' está reservado por el sistema"; exit 1; }

cp -r "$ROOT/modules/_template" "$DEST"

grep -rl '__MODULE_ID__\|__MODULE_NAME__' "$DEST" | while read -r f; do
  sed -i.bak "s/__MODULE_ID__/$ID/g; s/__MODULE_NAME__/$NAME/g" "$f"
  rm -f "$f.bak"
done

find "$DEST" -depth -name '*__MODULE_ID__*' | while read -r path; do
  mv "$path" "$(dirname "$path")/$(basename "$path" | sed "s/__MODULE_ID__/$ID/g")"
done

python3 - "$ROOT/pyproject.toml" "$ID" <<'PY'
import re
import sys

path, module = sys.argv[1], sys.argv[2]
text = open(path).read()

if f'"{module}"' not in text:
    text = re.sub(
        r'(dependencies = \[)([^\]]*)(\])',
        lambda m: f'{m.group(1)}{m.group(2).rstrip()} "{module}"{m.group(3)}'
        if m.group(2).rstrip().endswith(",")
        else f'{m.group(1)}{m.group(2).rstrip()}, "{module}"{m.group(3)}',
        text,
        count=1,
    )
    text = text.replace(
        "[tool.uv.sources]\n",
        f"[tool.uv.sources]\n{module} = {{ workspace = true }}\n",
        1,
    )
    text = text.replace(
        'known-first-party = [',
        f'known-first-party = ["{module}", ',
        1,
    )
    open(path, "w").write(text)
PY

( cd "$ROOT" && uv lock --quiet )

echo "modules/$ID creado y enganchado al workspace."
echo "Compruébalo: uv run pytest modules/$ID"
echo "Después: lo que dice modules/$ID/README.md, «Lo siguiente»."
