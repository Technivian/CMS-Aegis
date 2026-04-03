#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

INTERVAL_MINUTES="${1:-60}"
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

adopt_existing_dev_server() {
  local pid_file="logs/devserver.pid"
  local port_pid

  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "dev server already running (pid $(cat "$pid_file"))."
    return 0
  fi

  port_pid="$(lsof -ti tcp:8000 -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
  if [[ -n "$port_pid" ]]; then
    echo "$port_pid" > "$pid_file"
    echo "Adopted existing dev server on port 8000 (pid $port_pid)."
    return 0
  fi

  start_proc "dev server" "logs/devserver.pid" "logs/devserver.log" \
    "$ROOT_DIR/.venv/bin/python" -u manage.py runserver 0.0.0.0:8000 --noreload
}

adopt_existing_dev_server

start_proc "reminder scheduler" "logs/reminder_scheduler.pid" "logs/reminder_scheduler.log" \
  "$ROOT_DIR/.venv/bin/python" -u manage.py run_reminder_scheduler --interval-minutes "$INTERVAL_MINUTES"

echo "Services started."
echo "- Server log: logs/devserver.log"
echo "- Scheduler log: logs/reminder_scheduler.log"
