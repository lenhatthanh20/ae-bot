# AIGold

MT5 bot for XAUUSD. Claude proposes a trade; the EA checks the risk rules and decides.
Two machines on one LAN: Windows runs MetaTrader 5, the Mac runs the bridge and `claude -p`.

```
Windows: MT5 + mt5/AIGold.mq5 --WebRequest (LAN)--> Mac: bridge/server.py (<mac-ip>:18765) --> claude -p
         <-- "BUY;1.50;2.00;74;<bar>"  (action; SL in ATR; TP as R:R; confidence; bar echo)
```

- EA sends 100 closed M5 bars (OHLC, EMA20/50/200, RSI14, ATR14) plus 30 closed M15 and H1 bars,
  once per new M5 bar, 07:00-16:00 GMT.
- `bridge/prompt.md`: M5 trend-pullback scalp, every rule a number test on the rows. Stacked EMAs
  (ema20 > ema50 > ema200) with M15 + H1 agreeing, pullback to ema20, strong close back above it,
  vetoes for stretched price, volatility jumps and no room. Stop from a recipe (1.0-2.0 ATR), fixed
  R:R 1.2, confidence = 50 + 10 per extra that holds (5 extras). Any failed test → NONE (the default).
- The EA computes SL/TP prices itself and enforces every risk guard. Mac asleep, bridge down or LAN down: it prints
  `BRIDGE_ERR` and does not trade; open positions keep their broker-side SL/TP, time exit and Friday close.

## What you need

Mac with `python3`, the `claude` CLI logged in and `jq`. Windows with MetaTrader 5 and a broker account (demo first).
Both on one subnet with fixed IPs, written here as `<mac-ip>` and `<windows-ip>`. Run the steps in order.

## Step 1: Mac setup

```bash
scripts/setup.sh                                   # .venv from the local python3 + claude login check
(cd bridge && ../.venv/bin/python -m unittest -v)  # expected: OK
(cd tools && ../.venv/bin/python -m unittest -v)   # expected: OK
scripts/smoke.sh fake                              # expected: every line starts with PASS
```

## Step 2: Mac bridge on the LAN

```bash
# first: System Settings > Network > Firewall, allow incoming connections for .venv/bin/python
BRIDGE_HOST=0.0.0.0 ALLOW_IPS=127.0.0.1,<windows-ip> ./run.sh
curl http://127.0.0.1:18765/health                 # from a second terminal
```

Expected: `ok`. Keep the Mac awake: AC power, lid open. To test `http://<mac-ip>:18765/health` from the
Mac itself, add `<mac-ip>` to `ALLOW_IPS`; otherwise it answers 403.

## Step 3: Windows MT5

1. Tools > Options > Expert Advisors: allow algo trading; allow WebRequest for `http://<mac-ip>:18765`.
2. File > Open Data Folder: share the `MQL5` folder.
3. On the Mac: mount the share over SMB, `export MT5_MQL5=<path-to-MQL5>`, run `scripts/deploy-mt5.sh` (lists 4 files).
4. In MetaEditor, compile `AIGold`, `PingTest`, `ExportM1` and `ExportDeals` with F7. Expected: 0 errors.

## Step 4: Link check

Run the `PingTest` script with `InpUrl=http://<mac-ip>:18765/health`. Expected in the Experts tab:
`WebRequest code=200` and `Calendar ok=true values>0` (no calendar → `InpNewsFilter=false`, demo only).

## Step 5: Attach the EA (dry run)

Attach `AIGold` to an XAUUSD M5 chart with `InpUrl=http://<mac-ip>:18765/decide`. Keep the defaults
`InpDryRun=true` (no orders) and `InpAllowLive=false` (the EA refuses to start on a live account).
Expected: `DRYRUN` or `AI NONE` lines, at most one per M5 bar. Stop the bridge: `BRIDGE_ERR`, no order.

## Step 6: Real orders

- Demo account: set `InpDryRun=false`. Expect orders with SL/TP (loss at SL ≤ max($10, 1% of balance)), `SKIP POSITION`,
  `TIME_EXIT` after 12 bars, `SKIP LOSS_STREAK` after 4 losses in a row today, `SKIP ALGO_OFF` with Algo Trading off.
- Live account, only after `scripts/score.sh` prints `GATE: PASS` on demo data: `InpAllowLive=true`, small separate account.
- Gate: n ≥ 100 signals, mean > +0.15R after costs, lower 95% CI > 0, p < 0.05 against random direction,
  max drawdown < 10R, one prompt and model for the whole sample. `GATE: FAIL`: change the rules, start a new sample.

## Stop it

- `touch HALT` on the Mac: the bridge answers NONE. Delete the file to resume.
- MT5 **Algo Trading** button off: the EA opens nothing.
- Ctrl-C on `run.sh`: the EA prints `BRIDGE_ERR` and does not trade.

## Weekly

Run the `ExportM1` and `ExportDeals` scripts in MT5, then `scripts/stats.sh --html` (report in `local/`) and
`scripts/score.sh` on the Mac. The broker drops old M1 bars, and a signal without M1 data can never be scored.

## Windows upkeep

Never sleep, set Windows Update active hours, add MT5 to Startup, keep time sync on.

## If it fails

| You see | Cause | Fix |
|---|---|---|
| `BRIDGE_ERR` | Bridge down, Mac asleep or LAN down | Start `run.sh`, wake the Mac, repeat step 4 |
| HTTP 403 | Client IP not in `ALLOW_IPS` | Add `<windows-ip>` and restart `run.sh` |
| WebRequest error in `PingTest` | URL not in the MT5 whitelist | Step 3, item 1 |
| `port ... is busy` | Another process on the smoke port | `PORT=18767 scripts/smoke.sh fake` |
| `MT5_MQL5 is not set` | Variable missing in this shell | Step 3, item 3 |

## Reference

Agent rules: [AGENTS.md](AGENTS.md). No step here downloads a package; agents must not either.

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

| Script | What |
|---|---|
| `scripts/setup.sh` | Python venv + `claude auth status` |
| `scripts/smoke.sh fake` | Bridge end to end on `127.0.0.1`, no tokens (also runs in CI) |
| `scripts/smoke.sh cli` | One real `claude -p` call: checks structured output, latency, HALT |
| `scripts/deploy-mt5.sh` | Copies `mt5/*.mq5` into `$MT5_MQL5` (required); compile with F7 after |
| `scripts/score.sh [symbol]` | `tools/scoring.py` on `logs/` with `$MT5_MQL5/Files/m1_<symbol>.csv` from `ExportM1` |
| `scripts/stats.sh [args]` | `tools/stats.py` on `logs/` and `$MT5_MQL5/Files`; `SYMBOL` env, default `XAUUSD`; e.g. `--since 2026-11-01` |
