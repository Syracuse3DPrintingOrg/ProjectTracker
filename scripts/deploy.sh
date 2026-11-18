#!/usr/bin/env bash
# Build SQ here and run it on a Docker host over SSH, with no registry.
#
#   scripts/deploy.sh <ssh-target> <host-data-dir> [host-port]
#   SSH_OPTS="-i key -o IdentitiesOnly=yes" scripts/deploy.sh root@server /mnt/appdata/sq/data
#
# On the host it backs up the data folder, keeps the running container's
# environment (without printing it), replaces the container with the new
# version, waits for /health to report that version, and puts the old
# image back if it does not. Needs docker here and docker plus curl there.
set -euo pipefail

TARGET=${1:?usage: deploy.sh <ssh-target> <host-data-dir> [host-port]}
DATA=${2:?usage: deploy.sh <ssh-target> <host-data-dir> [host-port]}
PORT=${3:-9280}
IMAGE=ghcr.io/syracuse3dprintingorg/projecttracker
ROOT=$(cd "$(dirname "$0")/.." && pwd)
VERSION=$(grep -oP 'APP_VERSION = "\K[^"]+' "$ROOT/service/app/config.py")
SSH=(ssh -o BatchMode=yes ${SSH_OPTS:-} "$TARGET")

echo "Building $IMAGE:$VERSION"
docker build -q -t "$IMAGE:$VERSION" "$ROOT"

echo "Sending the image to $TARGET"
docker save "$IMAGE:$VERSION" | gzip -1 | "${SSH[@]}" 'gunzip | docker load -q'
here=$(docker image inspect -f '{{json .RootFS.Layers}}' "$IMAGE:$VERSION")
there=$("${SSH[@]}" "docker image inspect -f '{{json .RootFS.Layers}}' $IMAGE:$VERSION" </dev/null)
[ "$here" = "$there" ] || { echo "The image that arrived does not match; nothing changed." >&2; exit 1; }

echo "Replacing the container"
# The remote script goes as an argument, not on stdin, so nothing in it
# can swallow the rest of the script.
"${SSH[@]}" "bash -c $(printf %q "$(cat <<'REMOTE'
set -euo pipefail
umask 077
IMAGE=$1 VERSION=$2 DATA=$3 PORT=$4 NAME=projecttracker
ENVFILE=$(mktemp)
trap 'rm -f "$ENVFILE"' EXIT

run() {
  docker run -d --name "$NAME" --restart unless-stopped \
    -p "$PORT:9280" -v "$DATA:/data" --env-file "$ENVFILE" \
    --label com.centurylinklabs.watchtower.enable=false "$1" >/dev/null </dev/null
}

OLD=""
if docker inspect "$NAME" >/dev/null 2>&1 </dev/null; then
  OLD=$(docker inspect -f '{{.Config.Image}}' "$NAME" </dev/null)
  # Keep what the container was given, minus what the image sets itself.
  docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$NAME" </dev/null \
    | grep -vE '^(PATH|LANG|GPG_KEY|PYTHON_[A-Z_]*|TRACKER_DATA_DIR)=' | grep . > "$ENVFILE" || true
  docker stop "$NAME" >/dev/null </dev/null
  trap 'docker start "$NAME" >/dev/null 2>&1 </dev/null || true; rm -f "$ENVFILE"' ERR
fi

BACKUPS="$(dirname "$DATA")/backups"
mkdir -p "$BACKUPS"
STAMP=$(date +%Y%m%d-%H%M%S)
tar -C "$(dirname "$DATA")" -czf "$BACKUPS/pre-deploy-$STAMP.tgz" "$(basename "$DATA")"
ls -1t "$BACKUPS"/pre-deploy-*.tgz | tail -n +6 | xargs -r rm -f
echo "Backed up the data folder to $BACKUPS/pre-deploy-$STAMP.tgz"

[ -n "$OLD" ] && docker rm "$NAME" >/dev/null </dev/null
trap - ERR
run "$IMAGE:$VERSION"

for _ in $(seq 1 30); do
  if curl -fsS -m 3 "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q "\"version\":\"$VERSION\""; then
    echo "SQ $VERSION is up"
    exit 0
  fi
  sleep 2
done

echo "SQ $VERSION did not come up. Last log lines:" >&2
docker logs --tail 30 "$NAME" </dev/null >&2 || true
if [ -n "$OLD" ]; then
  docker rm -f "$NAME" >/dev/null </dev/null
  run "$OLD"
  echo "Put $OLD back. The data backup is $BACKUPS/pre-deploy-$STAMP.tgz" >&2
fi
exit 1
REMOTE
)") _ $(printf %q "$IMAGE") $(printf %q "$VERSION") $(printf %q "$DATA") $(printf %q "$PORT")" </dev/null
