#!/bin/zsh
# Start the bridge and keep the Mac awake while it runs.
set -eu
cd "$(dirname "$0")"
export AI_MODE="${AI_MODE:-api}"
export BRIDGE_MODEL="${BRIDGE_MODEL:-claude-opus-5-5}"
if [ "$AI_MODE" = "api" ]; then
  export ANTHROPIC_API_KEY="$(security find-generic-password -a "$USER" -s aigold-anthropic -w)"
fi
exec caffeinate -is .venv/bin/python bridge/server.py
