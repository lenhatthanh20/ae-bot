"""Statistics report: AI prompts, decisions, EA funnel, real and shadow trade results, loss analysis.

Inputs: bridge logs (required), EA events CSV, deals CSV (ExportDeals), M1 CSV (ExportM1).
Missing optional files only hide their sections. Text, HTML and JSON all render one report dict.
Usage: python3 tools/stats.py logs/decisions-*.jsonl [--events E.csv] [--deals D.csv] [--m1 M1.csv]
       [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--setup SHA|all] [--html [PATH]] [--json PATH]
"""
import argparse
import bisect
import csv
import json
import math
import os
import statistics
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

import scoring

VERSION = 1
SKIP_AFTER_AI = ("BAR_CHANGED", "DRIFT")
BAR_EVENTS = ("SKIP", "BRIDGE_ERR", "AI_NONE", "REJECT", "DRYRUN", "ORDER")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats_report.html")


def utc(t):
    return datetime.fromtimestamp(int(t), timezone.utc)


def day_of(t):
    # shortcut: MT5 times are server time, not UTC; day filters on them can be a few hours off
    return utc(t).strftime("%Y-%m-%d")


def in_range(day, a):
    return (not a.since or day >= a.since) and (not a.until or day <= a.until)


def setup_id(r):
    return f"{r.get('prompt_sha')}/{r.get('model')}"


def action(r):
    return r.get("line", "NONE").split(";")[0]


def conf_bucket(conf):
    return min(int(conf) // 10 * 10, 90)


def pct(xs, q):
    s = sorted(xs)
    return s[max(0, math.ceil(q * len(s)) - 1)] if s else None


# ---- loading


def load_logs(paths):
    recs = [json.loads(l) for p in paths for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
    return sorted(recs, key=lambda r: r.get("ts", ""))


def filter_range(recs, a):
    return [r for r in recs if in_range(r.get("ts", "")[:10], a)]


def load_events(paths):
    out = []
    for p in paths:
        with open(p, newline="") as f:
            out += [dict(r, bar=int(r["bar"])) for r in csv.DictReader(f)]
    return out


def load_deals(path):
    num = ("lots", "open_price", "close_price", "sl", "tp", "profit", "commission", "swap")
    with open(path, newline="") as f:
        return [dict(r, position=int(r["position"]), open_time=int(r["open_time"]), close_time=int(r["close_time"]),
                     **{k: float(r[k]) for k in num}) for r in csv.DictReader(f)]


# ---- sections


def setups(recs):
    """Setup id -> its records, ordered by first use."""
    out = {}
    for r in recs:
        out.setdefault(setup_id(r), []).append(r)
    return out


def prompt_stats(recs):
    days, src, errors, lat = {}, Counter(), {"HALT": 0, "USD_CAP": 0, "other": 0}, []
    for r in recs:
        d = days.setdefault(r.get("ts", "")[:10], {"day": r.get("ts", "")[:10], "calls": 0, "cost": 0.0, "errors": 0})
        usd = (r.get("usage") or {}).get("usd") or 0.0
        d["calls"] += 1
        d["cost"] += usd
        src[(r.get("mode"), r.get("model"), r.get("prompt_sha"))] += 1
        err = r.get("error")
        if err:
            d["errors"] += 1
            errors[err if err in ("HALT", "USD_CAP") else "other"] += 1
        if err not in ("HALT", "USD_CAP") and r.get("latency_ms") is not None:
            lat.append(r["latency_ms"])  # real AI calls only (stops answer in ~0 ms)
    return {"calls": len(recs), "cost": sum(d["cost"] for d in days.values()), "errors": errors,
            "per_day": sorted(days.values(), key=lambda d: d["day"]),
            "by_source": [{"mode": m, "model": mo, "prompt_sha": s, "calls": n} for (m, mo, s), n in src.items()],
            "latency": {"p50": pct(lat, 0.5), "p95": pct(lat, 0.95), "max": max(lat, default=None)}}


def decision_stats(recs):
    total, days, buckets = Counter({"BUY": 0, "SELL": 0, "NONE": 0}), {}, Counter()
    for r in recs:
        if r.get("error"):
            continue
        act, day = action(r), r.get("ts", "")[:10]
        total[act] += 1
        days.setdefault(day, Counter({"BUY": 0, "SELL": 0, "NONE": 0}))[act] += 1
        if act != "NONE":
            buckets[str(conf_bucket(r["line"].split(";")[3]))] += 1
    n = sum(total.values())
    return {"total": dict(total), "pct": {k: v / n for k, v in total.items()} if n else {},
            "per_day": [dict(c, day=d) for d, c in sorted(days.items())],
            "conf_buckets": dict(sorted(buckets.items(), key=lambda kv: int(kv[0])))}


def funnel(events):
    """EA outcome per handled bar. ai_signals = reject + skip_after_ai + dryrun + order_ok + order_fail."""
    f = {"bars": 0, "skip_before_ai": Counter(), "bridge_err": 0, "ai_none": 0, "reject": Counter(),
         "skip_after_ai": Counter(), "dryrun": 0, "order_ok": 0, "order_fail": 0, "time_exit": 0, "close_fail": 0}
    for e in events:
        ev, why = e["event"], (e.get("detail") or "").split(" ")[0]
        f["bars"] += ev in BAR_EVENTS
        if ev == "SKIP":
            f["skip_after_ai" if why in SKIP_AFTER_AI else "skip_before_ai"][why] += 1
        elif ev == "REJECT":
            f["reject"][why] += 1
        elif ev == "ORDER":
            f["order_ok" if why == "ok" else "order_fail"] += 1
        elif ev.lower() in f:
            f[ev.lower()] += 1
    f = {k: dict(v) if isinstance(v, Counter) else v for k, v in f.items()}
    f["ai_signals"] = (sum(f["reject"].values()) + sum(f["skip_after_ai"].values())
                       + f["dryrun"] + f["order_ok"] + f["order_fail"])
    return f


def trade_row(rec, r, exit, mfe):
    d = rec.get("decision") or {}
    return {"r": r, "side": action(rec), "conf": int(d.get("confidence", 0)), "sl_atr": d.get("sl_atr"),
            "tp_rr": d.get("tp_rr"), "exit": exit, "mfe": mfe, "ts": rec["ts"], "setup": setup_id(rec),
            "reason": str(d.get("reason", ""))}


def excursion(m1, times, start, end, buy, entry, spread, sl_dist):
    """Best open profit in R over M1 bars that end before `end`. None if M1 does not cover the trade."""
    if not m1 or times[0] > start or times[-1] < end:
        return None
    lo_i, hi_i = bisect.bisect_left(times, start - start % 60), bisect.bisect_left(times, end - 60)
    best = 0.0
    for _, hi, lo, _ in m1[lo_i:hi_i]:
        best = max(best, ((hi - entry) if buy else (entry - lo - spread)) / sl_dist)
    return best


def real_trades(deals, recs, events, m1):
    """Closed positions joined to the bridge record of their M5 bar. Returns (trades, unmatched)."""
    by_bar = {int(r["bar"]): r for r in recs if r.get("bar") and action(r) != "NONE"}
    friday = {}
    for e in events:
        if e["event"] == "TIME_EXIT":
            kv = dict(x.split("=", 1) for x in e.get("detail", "").split() if "=" in x)
            friday[int(kv.get("ticket", 0))] = kv.get("friday") == "true"
    trades, unmatched = [], []
    for d in sorted(deals, key=lambda d: d["open_time"]):
        buy, sl_dist = d["type"] == "BUY", abs(d["open_price"] - d["sl"])
        rec = by_bar.get(d["open_time"] - d["open_time"] % 300)
        if rec is None or d["sl"] == 0:
            unmatched.append({"position": d["position"], "open_time": d["open_time"], "side": d["type"],
                              "profit": d["profit"], "why": "no SL" if d["sl"] == 0 else "no bridge record"})
            continue
        r = ((d["close_price"] - d["open_price"]) if buy else (d["open_price"] - d["close_price"])) / sl_dist
        if d["profit"]:
            r *= (d["profit"] + d["commission"] + d["swap"]) / d["profit"]  # money per R = profit / r
        reason = d["close_reason"]
        exit = (reason if reason in ("SL", "TP") else
                ("FRIDAY" if friday.get(d["position"]) else "TIME") if reason == "EXPERT" else "OTHER")
        spread = float(rec["ask"]) - float(rec["bid"])
        mfe = excursion(m1[0], m1[1], d["open_time"], d["close_time"], buy, d["open_price"], spread, sl_dist) \
            if m1 else None
        trades.append(trade_row(rec, r, exit, mfe))
    return trades, unmatched


def group(trades, key, order=None):
    g = {}
    for t in trades:
        g.setdefault(key(t), []).append(t["r"])
    keys = order(g) if order else sorted(g)
    return [{"key": k, "n": len(g[k]), "win": sum(x > 0 for x in g[k]) / len(g[k]), "mean": statistics.fmean(g[k])}
            for k in keys]


def hour(t):
    return int(t["ts"][11:13])


def weekday(t):
    return WEEKDAYS[date.fromisoformat(t["ts"][:10]).weekday()]


def trade_stats(trades):
    rs = [t["r"] for t in trades]
    wins, losses = [x for x in rs if x > 0], [x for x in rs if x < 0]
    eq = peak = dd = 0.0
    equity, drawdown, streak, worst_streak = [], [], 0, 0
    for x in rs:
        eq += x
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
        equity.append(eq)
        drawdown.append(eq - peak)
        streak = streak + 1 if x < 0 else 0
        worst_streak = max(worst_streak, streak)
    n = len(rs)
    return {"n": n, "win": len(wins) / n if n else None, "mean": statistics.fmean(rs) if n else None,
            "total": eq, "pf": sum(wins) / -sum(losses) if losses else None,
            "avg_win": statistics.fmean(wins) if wins else None,
            "avg_loss": statistics.fmean(losses) if losses else None,
            "max_dd": dd, "max_loss_streak": worst_streak, "r": rs, "equity": equity, "drawdown": drawdown,
            "by": {"side": group(trades, lambda t: t["side"]), "hour": group(trades, hour),
                   "weekday": group(trades, weekday, lambda g: [w for w in WEEKDAYS if w in g]),
                   "conf": group(trades, lambda t: conf_bucket(t["conf"]))}}


def loss_analysis(trades):
    L = [t for t in trades if t["r"] < 0]
    exc = Counter("unknown" if t["mfe"] is None else "gave_back" if t["mfe"] >= 0.5 else "never_in_profit"
                  for t in L)
    worst = sorted(L, key=lambda t: t["r"])[:10]
    return {"n": len(L), "by_exit": dict(Counter(t["exit"] for t in L)), "excursion": dict(exc),
            "by_side": dict(Counter(t["side"] for t in L)), "by_hour": dict(sorted(Counter(map(hour, L)).items())),
            "by_conf": dict(sorted(Counter(conf_bucket(t["conf"]) for t in L).items())),
            "worst": [{k: t[k] for k in ("ts", "side", "conf", "sl_atr", "tp_rr", "exit", "r", "mfe")}
                      | {"reason": t["reason"][:160]} for t in worst]}


def results(trades, **extra):
    return trade_stats(trades) | {"losses": loss_analysis(trades)} | extra


def short(s):
    return {"n": s["n"], "win": s["win"], "mean": s["mean"]}


# ---- report


def build_report(a):
    inputs, missing = {"logs": a.logs}, []
    for name in ("m1", "deals"):
        p = getattr(a, name)
        if p and os.path.exists(p):
            inputs[name] = p
        else:
            missing.append(p or f"{name} CSV (--{name})")
    inputs["events"] = [p for p in a.events if os.path.exists(p)]
    missing += [p for p in a.events if not os.path.exists(p)] or ([] if a.events else ["events CSV (--events)"])
    inputs["missing"] = missing

    recs = filter_range(load_logs(a.logs), a)
    groups = setups(recs)
    latest = setup_id(recs[-1]) if recs else None
    if a.setup == "all":
        sid, sel = "all", recs
        warning = f"sample mixes prompt/model versions {sorted(groups)}: not valid evidence" if len(groups) > 1 else None
    else:
        match = [k for k in groups if k.startswith(a.setup)] if a.setup else [latest] if latest else []
        if len(match) > 1:
            raise SystemExit(f"--setup {a.setup} matches {match}: use prompt_sha/model")
        if a.setup and not match:
            raise SystemExit(f"--setup {a.setup}: no such setup in {sorted(groups)}")
        sid, sel, warning = (match[0], groups[match[0]], None) if match else (None, [], None)

    m1 = scoring.load_m1(inputs["m1"]) if "m1" in inputs else None
    events = [e for e in load_events(inputs["events"]) if in_range(day_of(e["bar"]), a)]
    bars = [int(r["bar"]) for r in sel if int(r.get("bar") or 0) > 0]
    if sid != "all" and bars:
        events = [e for e in events if min(bars) <= e["bar"] <= max(bars)]

    real_all = unmatched = None
    if "deals" in inputs:
        deals = [d for d in load_deals(inputs["deals"]) if in_range(day_of(d["open_time"]), a)]
        real_all, unmatched = real_trades(deals, recs, events, m1)

    def shadow(rs):
        trades, unscored = scoring.shadow_trades(a, rs, *m1)
        return [trade_row(t["rec"], t["r"], t["exit"], t["mfe"]) for t in trades if t["taken"]], unscored

    rows = []
    for k, rs in groups.items():
        row = {"id": k, "first": rs[0]["ts"][:10], "last": rs[-1]["ts"][:10], "calls": len(rs),
               "signals": sum(action(r) != "NONE" and not r.get("error") for r in rs)}
        if m1:
            row["shadow"] = short(trade_stats(shadow(rs)[0]))
        if real_all is not None:
            row["real"] = short(trade_stats([t for t in real_all if t["setup"] == k]))
        rows.append(row)

    rep = {"version": VERSION, "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "range": {"since": a.since, "until": a.until,
                     "first": recs[0]["ts"][:10] if recs else None, "last": recs[-1]["ts"][:10] if recs else None},
           "setup": {"id": sid, "latest": latest, "warning": warning}, "inputs": inputs, "setups": rows,
           "prompts": prompt_stats(recs), "decisions": decision_stats(sel),
           "funnel": funnel(events) if inputs["events"] else None, "real": None, "shadow": None}
    if real_all is not None:
        rep["real"] = results([t for t in real_all if sid == "all" or t["setup"] == sid], unmatched=unmatched)
    if m1:
        trades, unscored = shadow(sel)
        rep["shadow"] = results(trades, unscored=unscored)
    return rep


# ---- renderers


def f(x, fmt):
    return "-" if x is None else format(x, fmt)


def counts(d):
    return "  ".join(f"{k}={v}" for k, v in d.items()) or "-"


def render_text(rep):
    out = []
    p, d, st = rep["prompts"], rep["decisions"], rep["setup"]
    rg = rep["range"]
    out.append(f"setup={st['id']}  days={rg['first']}..{rg['last']}  since={rg['since'] or '-'}  until={rg['until'] or '-'}")
    if rep["inputs"]["missing"]:
        out.append("missing inputs (sections hidden): " + ", ".join(rep["inputs"]["missing"]))
    if st["warning"]:
        out.append("WARNING: " + st["warning"])
    out.append("\nSETUPS")
    for s in rep["setups"]:
        line = f"  {s['id']:<32} {s['first']}..{s['last']}  calls={s['calls']}  signals={s['signals']}"
        for src in ("shadow", "real"):
            if src in s:
                line += f"  {src} n={s[src]['n']} win={f(s[src]['win'], '.0%')} meanR={f(s[src]['mean'], '+.3f')}"
        out.append(line)
    lat = p["latency"]
    out += ["\nPROMPTS (all setups)",
            f"  calls={p['calls']}  cost=${p['cost']:.2f}  errors: {counts(p['errors'])}",
            f"  latency ms p50={f(lat['p50'], 'd')} p95={f(lat['p95'], 'd')} max={f(lat['max'], 'd')}"]
    out += [f"  {s['mode']}/{s['model']}/{s['prompt_sha']}: {s['calls']}" for s in p["by_source"]]
    out += [f"  {x['day']}  calls={x['calls']:>4}  errors={x['errors']:>3}  cost=${x['cost']:.2f}" for x in p["per_day"]]
    out += ["\nDECISIONS (setup)", "  " + "  ".join(f"{k}={v} ({d['pct'].get(k, 0):.0%})" for k, v in d["total"].items()),
            "  confidence (BUY/SELL): " + counts({f"{k}+": v for k, v in d["conf_buckets"].items()})]
    out += [f"  {x['day']}  BUY={x['BUY']:>3}  SELL={x['SELL']:>3}  NONE={x['NONE']:>3}" for x in d["per_day"]]
    fu = rep["funnel"]
    if fu:
        out += ["\nFUNNEL (EA events)",
                f"  bars={fu['bars']}  skip before AI: {counts(fu['skip_before_ai'])}",
                f"  bridge_err={fu['bridge_err']}  ai_none={fu['ai_none']}  ai_signals={fu['ai_signals']}",
                f"  reject: {counts(fu['reject'])}", f"  skip after AI: {counts(fu['skip_after_ai'])}",
                f"  dryrun={fu['dryrun']}  order_ok={fu['order_ok']}  order_fail={fu['order_fail']}"
                f"  time_exit={fu['time_exit']}  close_fail={fu['close_fail']}"]
    for src in ("real", "shadow"):
        s = rep[src]
        if s is None:
            continue
        out.append(f"\nRESULTS {src.upper()}" + (f"  (not scored, no M1 data: {s['unscored']})" if src == "shadow" else ""))
        out.append(f"  n={s['n']}  win={f(s['win'], '.0%')}  meanR={f(s['mean'], '+.3f')}  total={s['total']:+.1f}R"
                   f"  PF={f(s['pf'], '.2f')}  avgWin={f(s['avg_win'], '+.2f')}  avgLoss={f(s['avg_loss'], '+.2f')}"
                   f"  maxDD={s['max_dd']:.1f}R  lossStreak={s['max_loss_streak']}")
        for dim, rows in s["by"].items():
            out.append(f"  by {dim}: " + "  ".join(f"{r['key']}:n={r['n']},{r['win']:.0%},{r['mean']:+.2f}" for r in rows))
        L = s["losses"]
        out += [f"  LOSSES n={L['n']}  exit: {counts(L['by_exit'])}  excursion: {counts(L['excursion'])}",
                f"    side: {counts(L['by_side'])}  hour: {counts(L['by_hour'])}  conf: {counts(L['by_conf'])}"]
        for w in L["worst"]:
            out.append(f"    {w['ts'][:16]} {w['side']:<4} conf={w['conf']} sl={w['sl_atr']} rr={w['tp_rr']}"
                       f" {w['exit']:<6} R={w['r']:+.2f}  {w['reason']}")
        for u in s.get("unmatched") or []:
            out.append(f"  UNMATCHED position={u['position']} open={utc(u['open_time']):%Y-%m-%d %H:%M} "
                       f"{u['side']} profit={u['profit']:+.2f} ({u['why']})")
    return "\n".join(out)


def render_html(rep):
    with open(TEMPLATE, encoding="utf-8") as fh:
        page = fh.read()
    return page.replace("/*REPORT*/", json.dumps(rep).replace("</", "<\\/"))


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--events", action="append", default=[])
    ap.add_argument("--deals")
    ap.add_argument("--m1")
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--setup", help="prompt_sha (prefix), prompt_sha/model, or all; default: latest")
    ap.add_argument("--html", nargs="?", const=f"local/stats-{date.today()}.html")
    ap.add_argument("--json")
    scoring.add_ea_args(ap)
    return ap.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)
    rep = build_report(a)
    print(render_text(rep))
    for path, text in ((a.html, render_html), (a.json, lambda r: json.dumps(r, indent=1))):
        if path:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text(rep))
            print(f"wrote {path}")


if __name__ == "__main__":
    main()
