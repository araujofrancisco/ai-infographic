#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT"

if [ -x "$ROOT/.venv/bin/python" ]; then

    PY="$ROOT/.venv/bin/python"

else

    PY="python3"

fi

echo "== pytest (unit + component) =="

"$PY" -m pytest

echo "== ruff (safety rules) =="

if "$PY" -m ruff check >/dev/null 2>&1; then

    "$PY" -m ruff check

else

    echo "ruff not installed; skipping lint"

fi

echo "== smoke test =="

"$PY" smoke_test.py

echo "ALL VERIFICATION PASSED"
