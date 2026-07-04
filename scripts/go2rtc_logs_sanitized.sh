#!/usr/bin/env sh
set -eu

TAIL="${TAIL:-200}"
SERVICE="${SERVICE:-go2rtc}"
PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON="${PYTHON:-python}"
export PYTHONPATH="${PROJECT_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

if [ -n "${EZVIZ_SECRETS_ENV_FILE:-}" ]; then
  docker compose logs --no-color --tail "$TAIL" "$SERVICE" \
    | "$PYTHON" -m ezviz_panel.backend.log_sanitizer --secrets-env-file "$EZVIZ_SECRETS_ENV_FILE"
else
  docker compose logs --no-color --tail "$TAIL" "$SERVICE" \
    | "$PYTHON" -m ezviz_panel.backend.log_sanitizer
fi
