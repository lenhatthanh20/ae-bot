#!/bin/bash
# End-to-end bridge check on its own port, logs and HALT file, so a running bot is not touched.
# Usage: scripts/smoke.sh fake   (no tokens)
#        scripts/smoke.sh cli    (one real claude -p call)
set -eu
cd "$(dirname "$0")/.."
MODE="${1:-fake}"
case "$MODE" in fake|cli) ;; *) echo "usage: $0 fake|cli"; exit 2 ;; esac
PORT="${PORT:-18766}"
URL="http://127.0.0.1:$PORT"
TMP="$(mktemp -d)"
BAR=1767225600
BODY=$'bar=1767225600;sym=XAUUSD;tf=PERIOD_M15;bid=2650.10;ask=2650.40;atr=5.20\ntime,open,high,low,close,ema20,ema50,ema200,rsi14,atr14\n'
FAIL=0

if curl -s -o /dev/null "$URL/health"; then echo "port $PORT is busy, set PORT=..."; exit 1; fi
if [ "$MODE" = cli ]; then unset ANTHROPIC_API_KEY; fi
AI_MODE="$MODE" PORT="$PORT" LOG_DIR="$TMP" HALT_FILE="$TMP/HALT" DAILY_USD_CAP=20 \
  .venv/bin/python bridge/server.py >"$TMP/server.out" 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null || true' EXIT
for _ in $(seq 50); do curl -sf -o /dev/null "$URL/health" && break; sleep 0.2; done

check() {  # name, got, want
  if [ "$2" = "$3" ]; then echo "PASS $1"; else echo "FAIL $1: got '$2', want '$3'"; FAIL=1; fi
}
decide() { printf '%s' "$BODY" | curl -s --max-time 70 --data-binary @- "$URL/decide"; }
last() { tail -n1 "$TMP"/decisions-*.jsonl | jq -r "$1"; }

check health "$(curl -s "$URL/health")" ok
if [ "$MODE" = fake ]; then
  check "fake decide" "$(decide)" "BUY;1.50;2.00;80;$BAR"
else
  echo "calling claude -p, can take up to 55 s..."
  echo "line: $(decide)"
  check "claude result" "$(last '.usage.stop // .error')" success
  check "structured output" "$(last '.decision.action | type')" string
  echo "decision: $(last '.decision | tostring')"
  echo "latency: $(last .latency_ms) ms (EA timeout is 60000)"
fi
touch "$TMP/HALT"
check "HALT gives NONE" "$(decide)" "NONE;0;0;0;$BAR"
check "HALT logged" "$(last .error)" HALT

echo "logs: $TMP"
if [ "$FAIL" = 1 ]; then cat "$TMP/server.out"; fi
exit "$FAIL"
