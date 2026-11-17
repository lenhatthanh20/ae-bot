#!/bin/bash
# One-time setup: Python venv and Claude login check. Downloads nothing.
set -eu
cd "$(dirname "$0")/.."
[ -x .venv/bin/python ] || python3 -m venv .venv
claude auth status
