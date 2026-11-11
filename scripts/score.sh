#!/bin/bash
# Score shadow-mode logs against the M1 file written by the ExportM1 script.
# Usage: scripts/score.sh [symbol]   (default XAUUSD)
set -eu
cd "$(dirname "$0")/.."
MQL5="${MT5_MQL5:-}"
[ -n "$MQL5" ] || { echo "MT5_MQL5 is not set: point it at the Windows MQL5 folder mounted over SMB"; exit 1; }
[ -d "$MQL5" ] || { echo "MT5_MQL5 is not a folder: $MQL5"; exit 1; }
exec .venv/bin/python tools/scoring.py --m1 "$MQL5/Files/m1_${1:-XAUUSD}.csv" logs/decisions-*.jsonl
