#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export DJANGO_SETTINGS_MODULE="config.test_settings"

PYTHON_BIN="./venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python"
fi

"$PYTHON_BIN" manage.py test \
  bookings.tests.BookingFraudDetectionTests \
  bookings.tests.BookingFlowTests.test_owner_mark_paid_at_ground_for_due_booking \
  "$@"
