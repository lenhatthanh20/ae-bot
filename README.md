# AIGold

MT5 bot for XAUUSD. Claude proposes a trade; the EA checks the risk rules and decides.
Two machines on one LAN: Windows runs MetaTrader 5, the Mac runs the bridge and `claude -p`.

```
Windows: MT5 + mt5/AIGold.mq5 --WebRequest (LAN)--> Mac: bridge/server.py (<mac-ip>:18765) --> claude -p
         <-- "BUY;1.50;2.00;74;<bar>"  (action; SL in ATR; TP as R:R; confidence; bar echo)
```

- EA sends 100 closed M5 bars (OHLC, EMA20/50/200, RSI14, ATR14) plus 30 closed M15 and H1 bars,
  once per new M5 bar, 07:00-16:00 GMT.
- `bridge/prompt.md`: M5 trend-pullback scalp. M15 + H1 bias, pullback to the ema20-ema50 zone,
  rejection or engulfing trigger, room to the next level. Sideways or unsure → NONE (the default).
- The EA computes SL/TP prices itself and enforces every risk guard (see [Risk guards](#risk-guards)).
- `InpDryRun=true` and `InpAllowLive=false` by default.
- Mac asleep, bridge down or LAN down: `WebRequest` fails, the EA prints `BRIDGE_ERR` and does not trade.
  Open positions keep their broker-side SL/TP; time exit and Friday close run in the EA.

## Layout

| Path | What |
|---|---|
| `mt5/AIGold.mq5` | Expert Advisor |
| `mt5/PingTest.mq5` | Phase 0 check: WebRequest from Windows to the Mac bridge + Calendar |
| `mt5/ExportM1.mq5` | Exports M1 bars for scoring |
| `bridge/server.py` | Bridge, `AI_MODE=cli\|fake` |
| `bridge/prompt.md` | System prompt |
| `tools/scoring.py` | Offline scoring of shadow-mode decisions |
| `tools/compare_models.py` | Same payloads on Haiku/Sonnet/Opus |
| `run.sh` | Starts the bridge with `caffeinate` |

## Quick start (macOS)

```bash
brew install uv
uv venv --python 3.12 && uv pip install -r requirements.txt

(cd bridge && ../.venv/bin/python -m unittest -v)
(cd tools && ../.venv/bin/python -m unittest -v)

AI_MODE=fake ./run.sh     # EA tests without tokens, localhost only
./run.sh                  # claude -p, subscription login
touch HALT                # kill switch: bridge answers NONE
```

## Bridge environment

| Variable | Default | Notes |
|---|---|---|
| `AI_MODE` | `fake` in code, `cli` in `run.sh` | `cli` \| `fake` |
| `BRIDGE_MODEL` | `claude-opus-5-5` | Or `claude-sonnet-5-5`, `claude-haiku-5-5` |
| `BRIDGE_EFFORT` | `low` | `low` \| `medium` |
| `DAILY_USD_CAP` | `3` in code, `20` in `run.sh` | Over the cap the bridge answers NONE (UTC day). In cli mode this is an estimate |
| `PORT` | `18765` | A new port needs a new `InpUrl` and WebRequest whitelist entry |
| `BRIDGE_HOST` | `127.0.0.1` | `0.0.0.0` to listen on the LAN |
| `ALLOW_IPS` | `127.0.0.1` | Comma list of client IPs. Others get HTTP 403: no Claude call, no decision log, no cost |
| `CLAUDE_BIN` | `claude` | Absolute path if `claude` is not on `PATH` |
| `FAKE_ACTION` | `BUY` | Fake mode only: `BUY` \| `SELL` \| `NONE` |

## Two-machine LAN setup

Both machines must be in the same subnet. Use fixed IPs (`<mac-ip>`, `<windows-ip>`), outside the router DHCP pool
or as DHCP reservations.

Mac:
1. Fixed IP on the LAN interface. Do not use VM interfaces (colima, Docker).
2. System Settings > Network > Firewall: allow incoming connections for `.venv/bin/python`.
3. Start the bridge on the LAN:
   ```bash
   BRIDGE_HOST=0.0.0.0 ALLOW_IPS=127.0.0.1,<windows-ip> ./run.sh
   curl http://127.0.0.1:18765/health   # ok
   ```
   To test the LAN address from the Mac itself, add `<mac-ip>` to `ALLOW_IPS`; otherwise it answers 403:
   ```bash
   BRIDGE_HOST=0.0.0.0 ALLOW_IPS=127.0.0.1,<mac-ip>,<windows-ip> ./run.sh
   curl http://<mac-ip>:18765/health   # ok
   ```
4. Keep it awake: AC power, lid open. `run.sh` runs `caffeinate -is`.

Windows:
1. MT5 Tools > Options > Expert Advisors: allow algo trading, allow WebRequest for `http://<mac-ip>:18765`.
2. Share the MT5 data folder (File > Open Data Folder, the `MQL5` folder) and mount it on the Mac over SMB.
   Then on the Mac: `export MT5_MQL5=<path-to-MQL5>` and run `scripts/deploy-mt5.sh`.
3. Compile in MetaEditor (F7). Run `PingTest` with `InpUrl=http://<mac-ip>:18765/health`, then attach `AIGold`
   to an XAUUSD M5 chart with `InpUrl=http://<mac-ip>:18765/decide`.
4. Never sleep, set Windows Update active hours, add MT5 to Startup, keep time sync on (the EA uses `TimeGMT()`).

## Scripts

| Script | What |
|---|---|
| `scripts/setup.sh` | uv venv + `claude auth status` |
| `scripts/smoke.sh fake` | Bridge end to end on `127.0.0.1`, no tokens (also runs in CI) |
| `scripts/smoke.sh cli` | One real `claude -p` call: checks structured output, latency, HALT |
| `scripts/deploy-mt5.sh` | Copies `mt5/*.mq5` into `$MT5_MQL5` (required); compile with F7 after |
| `scripts/score.sh [symbol]` | `tools/scoring.py` on `logs/` with `$MT5_MQL5/Files/m1_<symbol>.csv` from `ExportM1` |

`smoke.sh` uses its own port (18766), log dir and HALT file, so it can run next to a live bridge.

## Risk guards

| # | Guard | Where |
|---|---|---|
| 1 | Block live accounts (`InpAllowLive=false` → INIT_FAILED) | EA `OnInit` |
| 2 | Kill switch: MT5 **Algo Trading** button (EA checks `TERMINAL_TRADE_ALLOWED`) | MT5 + EA `PreCheck` |
| 3 | Kill switch: `touch HALT` → bridge always answers NONE | Bridge `decide` |
| 4 | `InpDryRun=true` by default | EA `Execute` |
| 5 | At most one AI call per bar, also after restart (GV `lastbar` written before the call + `GlobalVariablesFlush`) | EA `OnTick` |
| 6 | Skip the bar if it opened more than 60 s ago | EA `OnTick` |
| 7 | One position at a time (symbol + magic; on netting accounts any position on the symbol) | EA `PreCheck` |
| 8 | GMT session window, no entries on Saturday/Sunday | EA `PreCheck` |
| 9 | Spread ≤ `InpMaxSpreadPts` | EA `PreCheck` |
| 10 | HIGH-impact USD news ±30 min; calendar error → no entry | EA `NewsBlackout` |
| 11 | Trades per day counted from history (not RAM) | EA `TradesToday` |
| 12 | Daily loss on equity (GV keeps start-of-day equity) | EA `DailyLossHit` |
| 13 | Kill at 10% drawdown from equity peak (GV keeps the peak) | EA `PreCheck` |
| 14 | Bridge error, timeout, HTTP ≠ 200, bad format or `bar` echo mismatch → no entry | EA `OnTick` + bridge |
| 15 | Bar changed or price drifted > 0.3 ATR while waiting for the AI → skip | EA `OnTick` |
| 16 | Confidence ≥ 70 | EA `Validate` |
| 17 | SL 1.0-2.0 ATR, RR 1.2-2, TP ≤ 3 ATR, SL ≥ 6× spread | EA `Validate` |
| 18 | Broker stops/freeze level | EA `Validate` |
| 19 | Risk per trade ≤ 1% of balance (`OrderCalcProfit`) | EA `Validate` |
| 20 | SL/TP required, sent in the same request; prices normalized to tick; lot clamped | EA `Validate` / `Execute` |
| 21 | Filling mode by symbol, deviation 30 points, no retry | EA `OnInit` / `Execute` |
| 22 | Time exit (12 bars) and Friday close 19:00 GMT (fixed rules, no AI) | EA `ManagePosition` |
| 23 | Bridge bind is opt-in (`BRIDGE_HOST`, default `127.0.0.1`) + client IP allowlist (`ALLOW_IPS`) | Bridge |
| 24 | `DAILY_USD_CAP` | Bridge |
| 25 | `ANTHROPIC_API_KEY` unset, so `claude -p` uses the subscription login; no secrets in repo or logs | `run.sh` |

## Live gate

Forward data only: replaying history has look-ahead (the model has seen past gold prices) and the
Strategy Tester cannot run WebRequest. Freeze `prompt.md`, the model and `InpMinConfidence` for the whole sample.

Gate, fixed in advance: n ≥ 100, mean > +0.15R after costs, lower 95% CI > 0, p < 0.05 against random
direction, max drawdown < 10R, one prompt/model only. `tools/scoring.py` prints `GATE: PASS` or `GATE: FAIL`.
A FAIL means stop or rewrite the rules and start a new sample; never tune on the old sample and re-score it.

## Rollout

Stay on demo until the gate passes.

- **Phase 0, setup gate:** broker demo account, exact symbol name, WebRequest whitelist on Windows.
  `PingTest` against `http://<mac-ip>:18765/health` must print `WebRequest code=200` and `Calendar ok=true values>0`
  (no calendar → `InpNewsFilter=false`, demo only). Note the server GMT offset.
- **Phase 1, bridge:** unit tests pass, `scripts/smoke.sh fake` passes, logs have `prompt_sha`, `usage`, `latency_ms`,
  `HALT` gives NONE.
- **Phase 2a, EA dry run with `AI_MODE=fake`:** EA prints `DRYRUN`; with the bridge stopped it prints `BRIDGE_ERR`
  and places no order.
- **Phase 2b, demo orders with `AI_MODE=fake` (3-5 days):** `InpDryRun=false`. Expect orders with SL/TP from the start,
  `SKIP POSITION`, `TIME_EXIT` after 12 bars, `SKIP TRADES_DAY` after 5 trades, `SKIP ALGO_OFF`, `AI NONE` with `HALT`,
  Friday close. Restart MT5 mid-bar: no second order in the same bar. Record slippage and every retcode other than 10009.
- **Phase 3, shadow mode with the real AI (≥ 4 weeks, ≥ 100 scored signals):** freeze `prompt.md`, run `./run.sh`,
  `InpDryRun=true`. Compare models with `tools/compare_models.py` in the first days.
- **Phase 4, decision:** run `scripts/score.sh`. FAIL → stop or restart Phase 3 with new rules.
  PASS → check that model cost does not eat the edge at the planned lot size.
- **Phase 5, live 0.01 lot (only after Phase 4 PASS):** small separate live account, `InpAllowLive=true`,
  `InpDryRun=false`, all guards on. Compare live with shadow weekly; stop if live falls below the shadow CI.
