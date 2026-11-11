#!/bin/bash
# Statistics report from logs/ and the MT5 files (events log, ExportDeals, ExportM1).
# Usage: scripts/stats.sh [stats.py args...]   e.g. --html, --since 2026-11-01, --setup all
# SYMBOL env picks the symbol (default XAUUSD). --html without a path writes local/ and opens it.
set -eu
cd "$(dirname "$0")/.."
MQL5="${MT5_MQL5:-}"
[ -n "$MQL5" ] || { echo "MT5_MQL5 is not set: point it at the Windows MQL5 folder mounted over SMB"; exit 1; }
[ -d "$MQL5" ] || { echo "MT5_MQL5 is not a folder: $MQL5"; exit 1; }
F="$MQL5/Files" SYM="${SYMBOL:-XAUUSD}" html=""
args=(--m1 "$F/m1_$SYM.csv" --deals "$F/deals_$SYM.csv")
for e in "$F"/aigold_events_*.csv; do [ -e "$e" ] && args+=(--events "$e"); done
while [ $# -gt 0 ]; do
  args+=("$1")
  if [ "$1" = --html ] && { [ $# -eq 1 ] || [[ $2 == -* ]]; }; then
    html="local/stats-$(date +%F).html"
    args+=("$html")
  fi
  shift
done
.venv/bin/python tools/stats.py logs/decisions-*.jsonl "${args[@]}"
[ -z "$html" ] || open "$html"
