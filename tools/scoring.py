"""Score shadow-mode decisions on M1 bars. Forward (live) data only.

M1 rows are bid prices. BUY enters at the logged ask, SELL at the logged bid.
If SL and TP are both touched in one M1 bar, SL counts first (conservative).
Usage: python3 tools/scoring.py --m1 m1_XAUUSD.csv logs/decisions-*.jsonl
"""
import argparse
import bisect
import csv
import json
import random
import statistics

TF_SEC = {"PERIOD_M5": 300, "PERIOD_M15": 900, "PERIOD_H1": 3600}


def load_m1(path):
    with open(path, newline="") as f:
        rows = sorted((int(r["time"]), float(r["high"]), float(r["low"]), float(r["close"]))
                      for r in csv.DictReader(f))
    return rows, [r[0] for r in rows]


def simulate(m1, times, bar, buy, entry, spread, sl_dist, rr, hold_sec):
    """Return (R, exit_time, exit_type, mfe_R), or None if M1 data does not cover the trade yet.

    exit_type is SL, TP or TIME. mfe_R is the best open profit in R before the exit bar
    (the SL bar is left out: inside one bar the order of high and low is unknown).
    """
    sl = entry - sl_dist if buy else entry + sl_dist
    tp = entry + sl_dist * rr if buy else entry - sl_dist * rr
    i, last, mfe = bisect.bisect_left(times, bar), None, 0.0
    while i < len(m1) and m1[i][0] < bar + hold_sec:
        t, hi, lo, _ = m1[i]
        if (buy and lo <= sl) or (not buy and hi + spread >= sl):
            return -1.0, t, "SL", mfe
        if (buy and hi >= tp) or (not buy and lo + spread <= tp):
            return rr, t, "TP", rr
        mfe = max(mfe, ((hi - entry) if buy else (entry - lo - spread)) / sl_dist)
        last, i = m1[i], i + 1
    if last is None or i == len(m1):
        return None
    exit_px = last[3] if buy else last[3] + spread
    return ((exit_px - entry) if buy else (entry - exit_px)) / sl_dist, last[0], "TIME", mfe


def add_ea_args(ap):
    """EA rules used by the shadow simulation (shared with stats.py)."""
    ap.add_argument("--min-conf", type=int, default=70)
    ap.add_argument("--sl-min", type=float, default=1.0)
    ap.add_argument("--sl-max", type=float, default=2.0)
    ap.add_argument("--rr-min", type=float, default=1.2)
    ap.add_argument("--rr-max", type=float, default=2.0)
    ap.add_argument("--tp-max-atr", type=float, default=3.0)
    ap.add_argument("--min-sl-spreads", type=float, default=6.0)
    ap.add_argument("--hold-bars", type=int, default=12)
    ap.add_argument("--cost", type=float, default=0.0, help="commission per trade, in price units")


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--m1", required=True)
    add_ea_args(ap)
    return ap.parse_args(argv)


def shadow_trades(a, recs, m1, times):
    """Simulate the signals the EA would take. Returns (trades, unscored).

    trades: every scored signal that passes the EA rules, in bar order. taken=True when
    conf >= min_conf (only those hold the one position). unscored: taken-level signals
    that M1 data does not cover.
    """
    trades, busy_until, unscored = [], 0, 0
    for r in sorted(recs, key=lambda r: int(r.get("bar", 0))):
        d = r.get("decision") or {}
        act = str(d.get("action", "")).upper()
        if r.get("error") or act not in ("BUY", "SELL"):
            continue
        sl_atr, rr, conf = float(d["sl_atr"]), float(d["tp_rr"]), int(d["confidence"])
        bar, atr, bid, ask = int(r["bar"]), float(r["atr"]), float(r["bid"]), float(r["ask"])
        spread, sl_dist = ask - bid, sl_atr * atr
        if not (a.sl_min <= sl_atr <= a.sl_max and a.rr_min <= rr <= a.rr_max
                and sl_atr * rr <= a.tp_max_atr and sl_dist >= a.min_sl_spreads * spread):
            continue  # the EA would reject it
        if bar < busy_until:
            continue  # the EA holds one position at a time
        buy, hold = act == "BUY", a.hold_bars * TF_SEC[r["tf"]]
        res = simulate(m1, times, bar, buy, ask if buy else bid, spread, sl_dist, rr, hold)
        opp = simulate(m1, times, bar, not buy, bid if buy else ask, spread, sl_dist, rr, hold)
        taken = conf >= a.min_conf
        if res is None or opp is None:
            unscored += taken
            continue
        cost_r = a.cost / sl_dist
        trades.append({"r": res[0] - cost_r, "flip": opp[0] - cost_r, "conf": conf, "side": act,
                       "exit_time": res[1], "exit": res[2], "mfe": res[3], "rec": r, "taken": taken})
        if taken:
            busy_until = res[1]
    return trades, unscored


def main(argv=None):
    a = parse_args(argv)

    m1, times = load_m1(a.m1)
    recs = [json.loads(l) for p in a.logs for l in open(p, encoding="utf-8")]
    trades, _ = shadow_trades(a, recs, m1, times)
    calib, ai, flip, setups = {}, [], [], set()
    for t in trades:
        calib.setdefault(min(t["conf"] // 10 * 10, 90), []).append(t["r"])
        if t["taken"]:
            ai.append(t["r"])
            flip.append(t["flip"])
            setups.add((t["rec"].get("prompt_sha"), t["rec"].get("model")))

    n = len(ai)
    if n == 0:
        print("no scored signals yet")
        return
    rng = random.Random(1)
    mean = statistics.fmean(ai)
    boots = sorted(statistics.fmean(rng.choices(ai, k=n)) for _ in range(2000))
    lo, hi = boots[50], boots[1949]
    rand = [statistics.fmean(x if rng.random() < 0.5 else y for x, y in zip(ai, flip)) for _ in range(2000)]
    p = sum(m >= mean for m in rand) / len(rand)
    eq = peak = dd = 0.0
    for x in ai:
        eq += x
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    print(f"n={n}  win={sum(x > 0 for x in ai) / n:.0%}  meanR={mean:+.3f}  95%CI=[{lo:+.3f}, {hi:+.3f}]")
    print(f"vs random direction p={p:.3f}  maxDD={dd:.1f}R  total={eq:+.1f}R")
    print("confidence bucket (all confidences, calibration):")
    for b in sorted(calib):
        print(f"  {b:>3}+  n={len(calib[b]):>3}  meanR={statistics.fmean(calib[b]):+.3f}")
    if len(setups) > 1:
        print(f"WARNING: sample mixes prompt/model versions {setups}: not valid evidence")
    ok = n >= 100 and mean > 0.15 and lo > 0 and p < 0.05 and dd < 10 and len(setups) == 1
    print("GATE:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()
