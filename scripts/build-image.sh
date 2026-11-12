#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DOCKERFILE=$1
TAG=$2
SCOPE=arga-$(basename "$(dirname "$DOCKERFILE")")

twice() { "$@" || { echo "reintento: $TAG" >&2; "$@"; }; }

if [[ -n ${BUILD_REV:-} ]]; then
  build_from_git() {
    git -C "$ROOT" archive --format=tar "$BUILD_REV" \
      | docker build -q --label "org.opencontainers.image.source=https://github.com/avesperinas/openarga" \
        --label "org.opencontainers.image.revision=$(git -C "$ROOT" rev-parse "$BUILD_REV")" \
        -f "$DOCKERFILE" -t "$TAG" - >/dev/null
  }
  twice build_from_git
  exit 0
fi

case ${BUILD_CACHE:-} in
  "")
    twice docker build -q -f "$ROOT/$DOCKERFILE" -t "$TAG" "$ROOT" >/dev/null
    exit 0
    ;;
  gha)
    CACHE=(--cache-from "type=gha,scope=$SCOPE" --cache-to "type=gha,mode=max,scope=$SCOPE")
    ;;
  local:*)
    DIR=${BUILD_CACHE#local:}/$SCOPE
    CACHE=(--cache-from "type=local,src=$DIR" --cache-to "type=local,dest=$DIR,mode=max")
    ;;
  *)
    echo "BUILD_CACHE desconocido: $BUILD_CACHE (vacío, gha o local:<carpeta>)" >&2
    exit 2
    ;;
esac
twice docker buildx build --load -q "${CACHE[@]}" -f "$ROOT/$DOCKERFILE" -t "$TAG" "$ROOT" >/dev/null
