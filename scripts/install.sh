#!/usr/bin/env bash
set -e
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$SCRIPT_DIR/.."
python3 scripts/auto_install.py --install-service --start
