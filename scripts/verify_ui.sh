#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="./.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python"
fi

DEFAULT_E2E_PORT="${E2E_PORT:-8010}"
E2E_PORT="$DEFAULT_E2E_PORT"

if [[ -z "${E2E_BASE_URL:-}" ]]; then
  for candidate in $(seq "$DEFAULT_E2E_PORT" $((DEFAULT_E2E_PORT + 20))); do
    if ! lsof -nP -iTCP:"$candidate" -sTCP:LISTEN >/dev/null 2>&1; then
      E2E_PORT="$candidate"
      break
    fi
  done
  E2E_BASE_URL="http://127.0.0.1:${E2E_PORT}"
else
  E2E_BASE_URL="${E2E_BASE_URL}"
  E2E_PORT="${E2E_BASE_URL##*:}"
fi
E2E_USERNAME="${E2E_USERNAME:-e2e_owner}"
E2E_PASSWORD="${E2E_PASSWORD:-e2e_pass_123}"

mkdir -p logs

echo "[verify-ui] Running UI integrity suites..."
"$PYTHON_BIN" manage.py test \
  tests.test_redesign_layout \
  tests.test_dashboard_shell \
  tests.test_reports_dashboard \
  tests.test_ui_click_integrity \
  tests.test_redesign_components \
  -v 2

echo "[verify-ui] Installing Playwright dependencies (if needed)..."
npm --prefix client install >/dev/null
npm --prefix client exec playwright install chromium >/dev/null

echo "[verify-ui] Seeding E2E user and organization..."
"$PYTHON_BIN" manage.py shell -c "
from django.contrib.auth.models import User
from contracts.models import Organization, OrganizationMembership

username='${E2E_USERNAME}'
password='${E2E_PASSWORD}'
email=f'{username}@example.com'

user, _ = User.objects.get_or_create(username=username, defaults={'email': email})
user.email = email
user.set_password(password)
user.is_active = True
user.save()

org, _ = Organization.objects.get_or_create(name='E2E Org', defaults={'slug': 'e2e-org'})
OrganizationMembership.objects.update_or_create(
    organization=org,
    user=user,
    defaults={'role': OrganizationMembership.Role.OWNER, 'is_active': True},
)
print('seeded', username)
"

echo "[verify-ui] Starting temporary Django server at ${E2E_BASE_URL}..."
"$PYTHON_BIN" manage.py runserver "127.0.0.1:${E2E_PORT}" --noreload > logs/e2e-devserver.log 2>&1 &
SERVER_PID=$!

cleanup() {
  if kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

for _ in {1..30}; do
  if curl -s -o /dev/null "${E2E_BASE_URL}/login/"; then
    break
  fi
  sleep 1
done

if ! curl -s -o /dev/null "${E2E_BASE_URL}/login/"; then
  echo "[verify-ui] Server did not become ready; check logs/e2e-devserver.log"
  exit 1
fi

echo "[verify-ui] Running Playwright smoke tests..."
E2E_BASE_URL="${E2E_BASE_URL}" \
E2E_USERNAME="${E2E_USERNAME}" \
E2E_PASSWORD="${E2E_PASSWORD}" \
npm --prefix client run test:e2e

echo "[verify-ui] Completed successfully."
