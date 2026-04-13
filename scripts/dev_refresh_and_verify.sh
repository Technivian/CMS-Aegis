#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PORT="8000"

kill_if_running() {
  local pid="$1"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" || true
  fi
}

echo "[1/4] Stopping current services..."
if [[ -f logs/dev_https.pid ]]; then
  kill_if_running "$(cat logs/dev_https.pid 2>/dev/null || true)"
fi
if [[ -f logs/reminder_scheduler.pid ]]; then
  kill_if_running "$(cat logs/reminder_scheduler.pid 2>/dev/null || true)"
fi
rm -f logs/dev_https.pid logs/reminder_scheduler.pid logs/devserver.pid

port_pids="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
if [[ -n "$port_pids" ]]; then
  for pid in $port_pids; do
    kill_if_running "$pid"
  done
fi

echo "[2/4] Starting services..."
bash scripts/dev_up.sh

if [[ ! -f logs/dev_https.pid ]]; then
  echo "ERROR: logs/dev_https.pid not created"
  exit 1
fi
https_pid="$(cat logs/dev_https.pid)"
if ! kill -0 "$https_pid" 2>/dev/null; then
  echo "ERROR: HTTPS process from pid file is not running: $https_pid"
  exit 1
fi

echo "[3/4] Verifying canonical redirect and rendered links..."
.venv/bin/python manage.py shell -c "
from django.test import Client
from django.contrib.auth.models import User
from contracts.models import Organization, OrganizationMembership

verification_username = 'startup_verify_user'
verification_org_slug = 'startup-verify-org'

org, _ = Organization.objects.get_or_create(
  slug=verification_org_slug,
  defaults={'name': 'Startup Verify Org'},
)
u, created = User.objects.get_or_create(
  username=verification_username,
  defaults={'email': 'startup-verify@example.com'},
)
if created:
  u.set_password('startup-verify-pass')
  u.save(update_fields=['password'])

OrganizationMembership.objects.get_or_create(
  organization=org,
  user=u,
  defaults={
    'role': OrganizationMembership.Role.OWNER,
    'is_active': True,
  },
)

c = Client()
c.force_login(u)

r = c.get('/care/casussen/new/', follow=False)
loc = r.get('Location', '')
if r.status_code != 200:
  raise SystemExit(f'ERROR: create page load invalid: status={r.status_code} location={loc}')

d = c.get('/dashboard/')
dh = d.content.decode('utf-8')
if 'href=\"/care/casussen/new/\"' not in dh:
  raise SystemExit('ERROR: dashboard new-case link is not canonical')
if '/care/casussen/new/?v=' in dh:
  raise SystemExit('ERROR: dashboard still contains version-query create href')

l = c.get('/care/casussen/')
lh = l.content.decode('utf-8')
if 'href=\"/care/casussen/new/\"' not in lh:
  raise SystemExit('ERROR: case list page does not contain canonical new-case href')
if '/care/casussen/new/?v=' in lh:
  raise SystemExit('ERROR: case list still contains version-query create href')

print('Verification passed')
"

echo "[4/4] Done. HTTPS server PID: $https_pid"
echo "URL: https://127.0.0.1:8000/"
