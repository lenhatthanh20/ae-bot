#!/bin/bash
# Copy the EA and scripts into MT5 (overwrites the old copies). Compile them in MetaEditor (F7) after.
set -eu
cd "$(dirname "$0")/.."
MQL5="${MT5_MQL5:-$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5}"
[ -d "$MQL5" ] || { echo "MT5 folder not found: $MQL5 (set MT5_MQL5)"; exit 1; }
cp -v mt5/AIGold.mq5 "$MQL5/Experts/"
cp -v mt5/PingTest.mq5 mt5/ExportM1.mq5 "$MQL5/Scripts/"
