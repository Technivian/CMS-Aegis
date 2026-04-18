#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install with: brew install uv" >&2
  exit 1
fi

PYTHON_PATH="$(uv python find 3.12 2>/dev/null || true)"
if [[ -z "$PYTHON_PATH" ]]; then
  echo "Python 3.12 not found via uv. Installing..."
  uv python install 3.12
  PYTHON_PATH="$(uv python find 3.12)"
fi

if [[ -d .venv ]]; then
  mv .venv ".venv.backup.$(date +%Y%m%d%H%M%S)"
fi

uv venv --python "$PYTHON_PATH" .venv
.venv/bin/python -m ensurepip --upgrade
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements/dev.txt

echo "Created .venv with $(.venv/bin/python --version)"
