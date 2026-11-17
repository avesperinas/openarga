#!/usr/bin/env bash
set -euo pipefail

# A fork's own modules go to modules/custom/, so upstream modules/ merges without conflicts.
# --core puts it in modules/ instead.
FOLDER="modules/custom"
if [[ "${1:-}" == "--core" ]]; then FOLDER="modules"; shift; fi
ID="${1:?usage: new-module.sh [--core] <id> <name>}"
NAME="${2:-$ID}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$FOLDER/$ID"
DEST="$ROOT/$DIR"

[[ "$ID" =~ ^[a-z][a-z0-9_]*$ ]] || { echo "invalid id: lowercase letters, digits and _ only"; exit 1; }
[[ -d "$DEST" || -d "$ROOT/modules/$ID" || -d "$ROOT/modules/custom/$ID" ]] && { echo "module $ID already exists"; exit 1; }
[[ "$ID" == "kernel" || "$ID" == "custom" ]] && { echo "'$ID' is reserved by the system"; exit 1; }

mkdir -p "$ROOT/$FOLDER"
cp -r "$ROOT/modules/_template" "$DEST"

grep -rl '__MODULE_ID__\|__MODULE_NAME__\|__MODULE_DIR__' "$DEST" | while read -r f; do
  sed -i.bak "s#__MODULE_DIR__#$DIR#g; s/__MODULE_ID__/$ID/g; s/__MODULE_NAME__/$NAME/g" "$f"
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

grep -q "^${ID^^}_DB_PASSWORD=" "$ROOT/.env.example" || echo "${ID^^}_DB_PASSWORD=" >> "$ROOT/.env.example"

( cd "$ROOT" && uv lock --quiet && uv run --quiet ruff check --quiet --fix --select I "$DIR" && uv run --quiet ruff format --quiet "$DIR" )

echo "$DIR created and added to the workspace."
echo "Check it: uv run pytest $DIR"
echo "Then: docs/platform/ explains manifests, tools, widgets and the demo seed."
