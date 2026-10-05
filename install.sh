#!/bin/sh
# autoload/vimpythondocstring.vim adds .venv/deps to sys.path. The
# directory is rebuilt so a dropped requirement leaves nothing behind.
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
rm -rf .venv/deps
.venv/bin/pip install --quiet --target .venv/deps -r requirements.txt
