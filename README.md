# AIGold

MT5 bot for XAUUSD. Claude proposes a trade; the EA checks the risk rules and decides.
Full design, review results and rollout gates: [docs/PLAN.md](docs/PLAN.md).

```
MT5 EA (mt5/AIGold.mq5) --WebRequest--> bridge/server.py (127.0.0.1:8000) --> Claude API
        <-- "BUY;1.50;2.00;74;<bar>"  (action; SL in ATR; TP as R:R; confidence; bar echo)
```

- EA sends 100 closed M15 bars (OHLC, EMA20/50/200, RSI14, ATR14) plus 30 closed H1 and H4 bars.
- `bridge/prompt.md`: the model checks 8 angles (trend, structure, levels, EMAs, momentum,
  volatility, price action, session) and trades only when 5+ agree. Default is NONE.
- The EA computes SL/TP prices itself and enforces every risk guard (see PLAN §6).
- `InpDryRun=true` and `InpAllowLive=false` by default.

## Layout

| Path | What |
|---|---|
| `mt5/AIGold.mq5` | Expert Advisor |
| `mt5/PingTest.mq5` | Phase 0 check: WebRequest + Calendar under Wine |
| `mt5/ExportM1.mq5` | Exports M1 bars for scoring |
| `bridge/server.py` | Bridge, `AI_MODE=api\|cli\|fake` |
| `bridge/prompt.md` | System prompt |
| `tools/scoring.py` | Offline scoring of shadow-mode decisions |
| `tools/compare_models.py` | Same payloads on Haiku/Sonnet/Opus |
| `run.sh` | Starts the bridge with `caffeinate`, key from Keychain |

## Quick start (macOS)

```bash
brew install uv
uv venv --python 3.12 && uv pip install -r requirements.txt
security add-generic-password -a "$USER" -s aigold-anthropic -w   # paste the API key

(cd bridge && ../.venv/bin/python -m unittest -v)
(cd tools && ../.venv/bin/python -m unittest -v)

AI_MODE=fake ./run.sh     # EA tests without tokens
./run.sh                  # real API
touch HALT                # kill switch: bridge answers NONE
```

MT5 side:
1. Tools > Options > Expert Advisors: allow algo trading, allow WebRequest for `http://127.0.0.1:8000`.
2. Copy `mt5/*.mq5` into `MQL5/Experts` (EA) and `MQL5/Scripts` (PingTest, ExportM1).
   Path: File > Open Data Folder.
3. Compile in MetaEditor (F7), run `PingTest` first, then attach `AIGold` to an XAUUSD M15 chart.

Follow the phases in PLAN §7. Stay on demo until `tools/scoring.py` prints `GATE: PASS`.
