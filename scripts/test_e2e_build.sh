#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export DJANGO_SETTINGS_MODULE="config.test_settings"

PYTHON_BIN="./venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python"
fi

"$PYTHON_BIN" manage.py check --fail-level ERROR
"$PYTHON_BIN" manage.py migrate --noinput
"$PYTHON_BIN" manage.py test accounts.tests bookings.tests
"$PYTHON_BIN" manage.py collectstatic --noinput --clear

echo "E2E build checks passed."
