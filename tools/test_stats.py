import contextlib
import io
import json
import os
import re
import tempfile
import unittest

import scoring
import stats

DAY = 86400
T0 = 1793836800  # 2026-11-05 00:00 UTC, a Thursday


def rec(bar, action="BUY", conf=80, sha="aaa", model="m", usd=0.1, latency=1000, error=None,
        reason="trend pullback", sl_atr=1.5, rr=1.5):
    ts = scoring_ts(bar)
    r = {"ts": ts, "mode": "cli", "model": model, "prompt_sha": sha, "bar": str(bar),
         "tf": "PERIOD_M5", "bid": "100.0", "ask": "100.1", "atr": "1.0", "latency_ms": latency}
    if error:
        r.update(error=error, line=f"NONE;0;0;0;{bar}")
        return r
    r.update(decision={"action": action, "sl_atr": sl_atr, "tp_rr": rr, "confidence": conf, "reason": reason},
             usage={"usd": usd})
    r["line"] = f"{action};{sl_atr:.2f};{rr:.2f};{conf};{bar}" if action != "NONE" else f"NONE;0;0;0;{bar}"
    return r


def scoring_ts(bar):
    return stats.utc(bar).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def write(d, name, text):
    p = os.path.join(d, name)
    with open(p, "w") as f:
        f.write(text)
    return p


def write_logs(d, recs):
    return write(d, "log.jsonl", "".join(json.dumps(r) + "\n" for r in recs))


def write_m1(d, start, end):
    return write(d, "m1.csv", "time,high,low,close\n" + "".join(
        f"{t},100.1,99.9,100\n" for t in range(start, end, 60)))


def trade(r, side="BUY", conf=80, exit="SL", mfe=None, ts="2026-11-05T08:00:00+00:00", reason="x"):
    return {"r": r, "side": side, "conf": conf, "exit": exit, "mfe": mfe, "ts": ts, "reason": reason,
            "sl_atr": 1.5, "tp_rr": 1.5}


def run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        stats.main(argv)
    return out.getvalue()


class Prompts(unittest.TestCase):
    def test_counts_errors_and_cost(self):
        b = T0 + 8 * 3600
        recs = [rec(b, usd=0.1, latency=1000), rec(b + 300, "NONE", usd=0.25, latency=3000),
                rec(b + 600, error="HALT", latency=1), rec(b + 900, error="USD_CAP", latency=2),
                rec(b + DAY, error="RuntimeError('claude exit 1')", latency=55000)]
        p = stats.prompt_stats(recs)
        self.assertEqual(p["calls"], 5)
        self.assertEqual(p["errors"], {"HALT": 1, "USD_CAP": 1, "other": 1})
        self.assertAlmostEqual(p["cost"], 0.35)
        self.assertEqual([(x["day"], x["calls"]) for x in p["per_day"]], [("2026-11-05", 4), ("2026-11-06", 1)])
        self.assertEqual(p["latency"]["max"], 55000)

    def test_decisions(self):
        b = T0 + 8 * 3600
        d = stats.decision_stats([rec(b), rec(b + 300, "SELL", conf=72), rec(b + 600, "NONE"),
                                  rec(b + 900, error="HALT")])
        self.assertEqual(d["total"], {"BUY": 1, "SELL": 1, "NONE": 1})
        self.assertEqual(d["conf_buckets"], {"70": 1, "80": 1})


class Funnel(unittest.TestCase):
    def test_adds_up(self):
        ev = [{"bar": 1, "event": e, "detail": x} for e, x in [
            ("SKIP", "HOURS"), ("SKIP", "NEWS"), ("BRIDGE_ERR", "http=-1"), ("AI_NONE", ""),
            ("REJECT", "CONF BUY conf=60"), ("REJECT", "RR SELL conf=80"), ("REJECT", "CONF SELL conf=50"),
            ("SKIP", "DRIFT"), ("DRYRUN", "BUY"), ("ORDER", "ok BUY rc=10009"), ("ORDER", "fail SELL rc=10006"),
            ("TIME_EXIT", "ticket=5 held=12 friday=false")]]
        f = stats.funnel(ev)
        self.assertEqual(f["reject"], {"CONF": 2, "RR": 1})
        self.assertEqual(f["skip_before_ai"], {"HOURS": 1, "NEWS": 1})
        self.assertEqual(f["skip_after_ai"], {"DRIFT": 1})
        self.assertEqual((f["dryrun"], f["order_ok"], f["order_fail"]), (1, 1, 1))
        self.assertEqual(f["ai_signals"], 3 + 1 + 1 + 1 + 1)
        self.assertEqual(f["bars"], 11)


class TradeStats(unittest.TestCase):
    def test_hand_sample(self):
        s = stats.trade_stats([trade(x) for x in (1, -1, -1, 2, -1)])
        self.assertEqual(s["n"], 5)
        self.assertAlmostEqual(s["win"], 0.4)
        self.assertAlmostEqual(s["pf"], 1.0)
        self.assertEqual(s["equity"], [1, 0, -1, 1, 0])
        self.assertEqual(s["max_dd"], 2)
        self.assertEqual(s["max_loss_streak"], 2)
        self.assertAlmostEqual(s["avg_win"], 1.5)
        self.assertAlmostEqual(s["avg_loss"], -1.0)

    def test_no_losses_gives_no_pf(self):
        self.assertIsNone(stats.trade_stats([trade(1)])["pf"])


class Losses(unittest.TestCase):
    def test_exit_excursion_and_worst(self):
        long_reason = "</b>" + "y" * 300
        L = stats.loss_analysis([trade(-1, exit="SL", mfe=0.2), trade(-1, exit="SL", mfe=0.8),
                                 trade(-0.4, exit="TIME", mfe=None, reason=long_reason),
                                 trade(-1.2, side="SELL", exit="FRIDAY", mfe=0.0), trade(2, exit="TP", mfe=2)])
        self.assertEqual(L["n"], 4)
        self.assertEqual(L["by_exit"], {"SL": 2, "TIME": 1, "FRIDAY": 1})
        self.assertEqual(L["excursion"], {"never_in_profit": 2, "gave_back": 1, "unknown": 1})
        self.assertEqual(L["worst"][0]["r"], -1.2)
        self.assertEqual(len([w for w in L["worst"] if len(w["reason"]) == 160]), 1)
        self.assertEqual(L["by_side"], {"BUY": 3, "SELL": 1})


class Real(unittest.TestCase):
    def test_join_by_bar_and_unmatched(self):
        b = T0 + 8 * 3600
        recs = [rec(b, sl_atr=1.5)]
        deals = [  # matched: opened 40 s into the bar, lost the full SL; unmatched: no bridge record
            {"position": 7, "open_time": b + 40, "close_time": b + 900, "type": "BUY", "lots": 0.01,
             "open_price": 100.1, "close_price": 98.6, "sl": 98.6, "tp": 102.35, "profit": -1.5,
             "commission": 0.0, "swap": 0.0, "close_reason": "SL"},
            {"position": 8, "open_time": b + 3 * 3600, "close_time": b + 4 * 3600, "type": "SELL", "lots": 0.01,
             "open_price": 100.0, "close_price": 99.0, "sl": 101.0, "tp": 98.5, "profit": 1.0,
             "commission": 0.0, "swap": 0.0, "close_reason": "EXPERT"}]
        trades, unmatched = stats.real_trades(deals, recs, [], None)
        self.assertEqual(len(trades), 1)
        self.assertAlmostEqual(trades[0]["r"], -1.0)
        self.assertEqual((trades[0]["exit"], trades[0]["conf"]), ("SL", 80))
        self.assertEqual([u["position"] for u in unmatched], [8])

    def test_net_r_and_friday_exit(self):
        b = T0 + 8 * 3600
        deals = [{"position": 7, "open_time": b, "close_time": b + 900, "type": "SELL", "lots": 0.01,
                  "open_price": 100.0, "close_price": 99.0, "sl": 102.0, "tp": 97.0, "profit": 2.0,
                  "commission": -0.2, "swap": 0.0, "close_reason": "EXPERT"}]
        ev = [{"bar": b, "event": "TIME_EXIT", "detail": "ticket=7 held=3 friday=true"}]
        trades, _ = stats.real_trades(deals, [rec(b, "SELL")], ev, None)
        self.assertAlmostEqual(trades[0]["r"], 0.5 * 1.8 / 2.0)
        self.assertEqual(trades[0]["exit"], "FRIDAY")


class Report(unittest.TestCase):
    def test_only_logs_names_missing_files(self):
        with tempfile.TemporaryDirectory() as d:
            logp = write_logs(d, [rec(T0 + 8 * 3600)])
            out = run([logp, "--m1", os.path.join(d, "nope.csv"), "--deals", os.path.join(d, "nope2.csv")])
        self.assertIn("PROMPTS", out)
        self.assertIn("DECISIONS", out)
        self.assertIn("nope.csv", out)
        self.assertIn("nope2.csv", out)
        self.assertIn("events", out)

    def test_shadow_matches_scoring(self):
        with tempfile.TemporaryDirectory() as d:
            m1p = write_m1(d, T0, T0 + DAY)
            recs = [rec(T0 + 8 * 3600), rec(T0 + 8 * 3600 + 300, "SELL"), rec(T0 + 10 * 3600, "SELL", conf=75),
                    rec(T0 + 11 * 3600, conf=60), rec(T0 + 12 * 3600, "NONE")]
            logp = write_logs(d, recs)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                scoring.main(["--m1", m1p, logp])
            m = re.search(r"n=(\d+)\s+win=(\d+)%\s+meanR=([-+.\d]+)", out.getvalue())
            sh = stats.build_report(stats.parse_args([logp, "--m1", m1p]))["shadow"]
        self.assertEqual(sh["n"], int(m.group(1)))
        self.assertEqual(round(sh["win"] * 100), int(m.group(2)))
        self.assertEqual(f"{sh['mean']:+.3f}", m.group(3))
        self.assertEqual(sh["n"], 2)

    def test_setups(self):
        with tempfile.TemporaryDirectory() as d:
            logp = write_logs(d, [rec(T0 + 8 * 3600, sha="old"), rec(T0 + DAY + 8 * 3600, sha="new"),
                                  rec(T0 + DAY + 9 * 3600, "SELL", sha="new")])
            rep = stats.build_report(stats.parse_args([logp]))
            self.assertEqual(len(rep["setups"]), 2)
            self.assertEqual(rep["setup"]["id"], "new/m")
            self.assertIsNone(rep["setup"]["warning"])
            self.assertEqual(rep["decisions"]["total"]["BUY"], 1)
            rep = stats.build_report(stats.parse_args([logp, "--setup", "old"]))
            self.assertEqual(rep["decisions"]["total"]["BUY"], 1)
            self.assertEqual(rep["decisions"]["total"]["SELL"], 0)
            rep = stats.build_report(stats.parse_args([logp, "--setup", "all"]))
            self.assertIn("mixes", rep["setup"]["warning"])
            self.assertEqual(rep["decisions"]["total"]["BUY"], 2)

    def test_since_until(self):
        with tempfile.TemporaryDirectory() as d:
            b = T0 + 8 * 3600
            logp = write_logs(d, [rec(b), rec(b + DAY), rec(b + 2 * DAY)])
            evp = write(d, "ev.csv", "time,bar,event,detail\n" + "".join(
                f"{x},{x},SKIP,HOURS\n" for x in (b, b + DAY, b + 2 * DAY)))
            dp = write(d, "deals.csv", "position,open_time,close_time,type,lots,open_price,close_price,sl,tp,"
                       "profit,commission,swap,close_reason\n" + "".join(
                           f"{i},{x},{x + 600},BUY,0.01,100.1,98.6,98.6,102.35,-1.5,0,0,SL\n"
                           for i, x in enumerate((b, b + DAY, b + 2 * DAY))))
            rep = stats.build_report(stats.parse_args(
                [logp, "--events", evp, "--deals", dp, "--since", "2026-11-06", "--until", "2026-11-06"]))
        self.assertEqual(rep["prompts"]["calls"], 1)
        self.assertEqual(sum(rep["decisions"]["total"].values()), 1)
        self.assertEqual(rep["funnel"]["bars"], 1)
        self.assertEqual(rep["real"]["n"], 1)
        self.assertEqual(rep["real"]["unmatched"], [])

    def test_json_and_text_agree(self):
        with tempfile.TemporaryDirectory() as d:
            logp = write_logs(d, [rec(T0 + 8 * 3600, usd=0.5), rec(T0 + 9 * 3600, error="HALT")])
            jp = os.path.join(d, "r.json")
            out = run([logp, "--json", jp])
            with open(jp) as f:
                rep = json.loads(f.read())
        self.assertEqual(rep["version"], stats.VERSION)
        self.assertEqual(rep["prompts"]["calls"], 2)
        self.assertIn("calls=2", out)
        self.assertIn("cost=$0.50", out)

    def test_html_escapes_reason(self):
        evil = "</script><b>x</b>"
        with tempfile.TemporaryDirectory() as d:
            m1p = write_m1(d, T0, T0 + DAY)
            logp = write_logs(d, [rec(T0 + 8 * 3600, reason=evil)])
            hp = os.path.join(d, "sub", "r.html")
            run([logp, "--m1", m1p, "--html", hp])
            with open(hp) as f:
                html = f.read()
        self.assertNotIn(evil, html)
        self.assertIn("<\\/script><b>x<\\/b>", html)
        self.assertEqual(html.count("</script>"), html.count("<script"))
        self.assertNotIn("innerHTML", html)


if __name__ == "__main__":
    unittest.main()
