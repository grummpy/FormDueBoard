#!/usr/bin/env bash
# Linux launcher. The first run creates .venv and installs dependencies.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "FormDueBoard needs Python 3.11 or newer, and python3 was not found."
  echo "Install it from https://www.python.org/downloads/ and then run ./launch.sh again."
  exit 1
fi

PY_OK="$(python3 -c 'import sys; print("yes" if sys.version_info >= (3, 11) else "no")')"
if [ "$PY_OK" != "yes" ]; then
  echo "FormDueBoard needs Python 3.11 or newer. This machine has:"
  python3 --version || true
  echo "Install a newer Python from https://www.python.org/downloads/"
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Setting up FormDueBoard for the first time..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --disable-pip-version-check -q -r requirements.txt
exec python -m formdueboard
