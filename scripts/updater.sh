#!/usr/bin/env bash
# Self-update runner (runs inside the `updater` sidecar container).
#
# Watches for the marker the bot's «Обновить» button drops into the shared volume and then
# runs scripts/update.sh (backup → git pull → rebuild → restart). The container has the host
# docker socket + the host repo bind-mounted at /repo, so update.sh operates on the real files
# and the host daemon. SKIP_UPDATER_RECREATE tells update.sh not to recreate US mid-update.
set -uo pipefail

REPO=/repo
MARKER="${UPDATE_REQUEST_FILE:-/repo/update-signals/request}"
LOG="$(dirname "$MARKER")/last-update.log"

mkdir -p "$(dirname "$MARKER")"
# The bind-mounted repo is owned by the host user; git refuses to run in a "dubious" dir as root.
git config --global --add safe.directory "$REPO" 2>/dev/null || true

echo "updater: watching $MARKER"
while true; do
  if [ -f "$MARKER" ]; then
    echo "updater: request at $(date -u +%FT%TZ) — running update.sh"
    rm -f "$MARKER"
    if (cd "$REPO" && SKIP_UPDATER_RECREATE=1 bash scripts/update.sh) >>"$LOG" 2>&1; then
      echo "updater: update OK"
    else
      echo "updater: update FAILED — see $LOG"
    fi
    # git ran as root here; hand the repo back to its host owner so a later manual
    # ./scripts/update.sh (run as that user) isn't blocked by root-owned objects.
    chown -R "$(stat -c '%u:%g' "$REPO" 2>/dev/null || echo 0:0)" "$REPO" 2>/dev/null || true
  fi
  sleep 10
done
