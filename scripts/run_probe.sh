#!/usr/bin/env sh
set -eu

CONFIG="${1:-cameras.local.yml}"
CAMERA_ID="${2:-}"
TIMEOUT="${TIMEOUT:-8}"
PYTHON_BIN="${PYTHON:-python3}"
SECRETS_ENV_FILE="${SECRETS_ENV_FILE:-}"

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

if [ -n "$CAMERA_ID" ]; then
  OUTPUT="probe-results/$CAMERA_ID.json"
  set -- "$PYTHON_BIN" -m ezviz_panel.camera_probe run \
    --config "$CONFIG" \
    --camera-id "$CAMERA_ID" \
    --timeout "$TIMEOUT" \
    --output "$OUTPUT"
else
  set -- "$PYTHON_BIN" -m ezviz_panel.camera_probe run \
    --config "$CONFIG" \
    --timeout "$TIMEOUT" \
    --output probe-results/all.json
fi

if [ -n "$SECRETS_ENV_FILE" ]; then
  set -- "$@" --secrets-env-file "$SECRETS_ENV_FILE"
fi

"$@"
