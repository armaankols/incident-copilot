#!/bin/sh
# Run from a terminal with package-index and Python-distribution network access.
set -eu
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="$PWD/.uv-cache"
export UV_PYTHON_INSTALL_DIR="$PWD/.python"
if command -v python3.12 >/dev/null 2>&1; then
  python3.12 -m venv .venv
else
  python3 -m pip install --target .bootstrap uv
  .bootstrap/bin/uv python install 3.12
  .bootstrap/bin/uv venv --python 3.12 .venv
fi
if [ -f requirements-dev.lock ]; then
  .venv/bin/python -m pip install -r requirements-dev.lock
else
  .venv/bin/python -m pip install -r requirements-dev.txt
  .venv/bin/python scripts/lock_environment.py
fi
.venv/bin/python -m pytest -q tests
.venv/bin/python -m evals.retrieval_eval
