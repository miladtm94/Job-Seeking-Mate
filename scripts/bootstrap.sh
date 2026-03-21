#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cp -n "$ROOT_DIR/.env.example" "$ROOT_DIR/.env" || true

python3 -m venv "$ROOT_DIR/backend/.venv"
source "$ROOT_DIR/backend/.venv/bin/activate"
pip install --upgrade pip
pip install -e "$ROOT_DIR/backend[dev]"

echo "Backend bootstrap complete."
echo "Run: cd $ROOT_DIR/backend && source .venv/bin/activate && uvicorn app.main:app --reload"
