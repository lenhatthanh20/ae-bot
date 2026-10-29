#!/bin/bash
# One-time setup: Python venv and Claude login check.
set -eu
cd "$(dirname "$0")/.."
command -v uv >/dev/null || brew install uv
[ -x .venv/bin/python ] || uv venv --python 3.12
claude auth status
