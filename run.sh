#!/bin/zsh
# Start the bridge and keep the Mac awake while it runs.
set -eu
cd "$(dirname "$0")"
export AI_MODE="${AI_MODE:-cli}"
export BRIDGE_MODEL="${BRIDGE_MODEL:-claude-opus-5-5}"
export DAILY_USD_CAP="${DAILY_USD_CAP:-20}"  # cli cost is an estimate, not a real charge
unset ANTHROPIC_API_KEY  # claude -p must use the subscription login
exec caffeinate -is .venv/bin/python bridge/server.py
