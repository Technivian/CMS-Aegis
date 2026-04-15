#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

INTERVAL_MINUTES="60"
VERIFY_MODE="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --verify)
      VERIFY_MODE="true"
      shift
      ;;
    --interval-minutes)
      INTERVAL_MINUTES="${2:-60}"
      shift 2
      ;;
    *)
      # Backward compatibility: first positional argument remains interval minutes.
      INTERVAL_MINUTES="$1"
      shift
      ;;
  esac
done

mkdir -p logs

start_proc() {
  local name="$1"
  local pid_file="$2"
  local log_file="$3"
  shift 3

  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "$name already running (pid $(cat "$pid_file"))."
    return
  fi

  : > "$log_file"
  nohup "$@" >> "$log_file" 2>&1 &
  local pid=$!
  echo "$pid" > "$pid_file"

  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$pid_file"
    echo "Failed to start $name. See $log_file for details."
    return 1
  fi

  echo "Started $name (pid $pid)."
}

start_https_server() {
  local pid_file="logs/dev_https.pid"

  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "HTTPS dev server already running (pid $(cat "$pid_file"))."
    return 0
  fi

  bash "$ROOT_DIR/scripts/dev_https.sh" up --background
}

start_https_server

start_proc "reminder scheduler" "logs/reminder_scheduler.pid" "logs/reminder_scheduler.log" \
  "$ROOT_DIR/.venv/bin/python" -u manage.py run_reminder_scheduler --interval-minutes "$INTERVAL_MINUTES"

echo "Services started."
echo "- HTTPS server: https://127.0.0.1:8000/"
echo "- HTTPS log:    logs/dev_https.log"
echo "- Scheduler log: logs/reminder_scheduler.log"

if [[ "$VERIFY_MODE" == "true" ]]; then
  echo "Running startup verification checks..."
  "$ROOT_DIR/.venv/bin/python" manage.py shell -c "
from django.test import Client
from django.contrib.auth.models import User
from contracts.models import Organization, OrganizationMembership

verification_username = 'startup_verify_user'
verification_org_slug = 'startup-verify-org'

org, _ = Organization.objects.get_or_create(
  slug=verification_org_slug,
  defaults={'name': 'Startup Verify Org'},
)
user, created = User.objects.get_or_create(
  username=verification_username,
  defaults={'email': 'startup-verify@example.com'},
)
if created:
  user.set_password('startup-verify-pass')
  user.save(update_fields=['password'])

OrganizationMembership.objects.get_or_create(
  organization=org,
  user=user,
  defaults={
    'role': OrganizationMembership.Role.OWNER,
    'is_active': True,
  },
)

client = Client()
client.force_login(user)

create_response = client.get('/care/casussen/new/', follow=False)
location = create_response.get('Location', '')
if create_response.status_code != 200:
  raise SystemExit(
    f'Verification failed: expected case-create page to load directly, '
    f'got status={create_response.status_code} location={location}'
  )

dashboard_html = client.get('/dashboard/').content.decode('utf-8')
if 'href=\"/care/casussen/new/\"' not in dashboard_html:
  raise SystemExit('Verification failed: dashboard new-case link is not canonical')
if '/care/casussen/new/?v=' in dashboard_html:
  raise SystemExit('Verification failed: dashboard contains version-query create href')
if 'dash-grid' not in dashboard_html or 'Knelpuntfocus' not in dashboard_html:
  raise SystemExit('Verification failed: dashboard design shell is missing expected layout contracts')
if 'careon-premium-theme.css' not in dashboard_html or 'title=\"Zoeken\"' not in dashboard_html:
  raise SystemExit('Verification failed: dashboard base shell lost theme/search contracts')
if 'data-theme-selector' not in dashboard_html or 'toggleTheme' not in dashboard_html:
  raise SystemExit('Verification failed: dashboard base shell lost theme controls')

case_list_html = client.get('/care/casussen/').content.decode('utf-8')
if 'href=\"/care/casussen/new/\"' not in case_list_html:
  raise SystemExit('Verification failed: case list new-case link is not canonical')
if '/care/casussen/new/?v=' in case_list_html:
  raise SystemExit('Verification failed: case list contains version-query create href')

reports_html = client.get('/care/reports/').content.decode('utf-8')
if 'page-wrap' not in reports_html or 'dash-grid' not in reports_html:
  raise SystemExit('Verification failed: reports dashboard lost page-wrap/dash-grid layout contracts')
if 'Rapportages & Regie' not in reports_html:
  raise SystemExit('Verification failed: reports dashboard did not render expected heading')

print('Startup verification passed')
"
fi
