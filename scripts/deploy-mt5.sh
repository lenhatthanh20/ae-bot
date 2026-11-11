#!/bin/bash
# Copy the EA and scripts into MT5 (overwrites the old copies). Compile them in MetaEditor (F7) after.
set -eu
cd "$(dirname "$0")/.."
MQL5="${MT5_MQL5:-}"
[ -n "$MQL5" ] || { echo "MT5_MQL5 is not set: point it at the Windows MQL5 folder mounted over SMB"; exit 1; }
[ -d "$MQL5" ] || { echo "MT5_MQL5 is not a folder: $MQL5"; exit 1; }
cp -v mt5/AIGold.mq5 "$MQL5/Experts/"
cp -v mt5/PingTest.mq5 mt5/ExportM1.mq5 "$MQL5/Scripts/"
