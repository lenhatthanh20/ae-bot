#!/bin/bash
# Score shadow-mode logs against the M1 file written by the ExportM1 script.
# Usage: scripts/score.sh [symbol]   (default XAUUSD)
set -eu
cd "$(dirname "$0")/.."
MQL5="${MT5_MQL5:-$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5}"
exec .venv/bin/python tools/scoring.py --m1 "$MQL5/Files/m1_${1:-XAUUSD}.csv" logs/decisions-*.jsonl
