import unittest

import contextlib
import io
import json
import os
import tempfile

import scoring
from scoring import simulate

# M1 rows: (time, high, low, close), bid prices
BAR, HOLD = 1000, 600


def m1(rows):
    return rows, [r[0] for r in rows]


class Simulate(unittest.TestCase):
    def test_buy_hits_tp(self):
        rows, t = m1([(1000, 101, 99.5, 100.5), (1060, 104.5, 100, 104), (1660, 104, 104, 104)])
        self.assertEqual(simulate(rows, t, BAR, True, 100.0, 0.2, 2.0, 2.0, HOLD), (2.0, 1060, "TP", 2.0))

    def test_sl_counts_first_when_both_hit_in_one_bar(self):
        rows, t = m1([(1000, 105, 97, 100), (1660, 100, 100, 100)])
        self.assertEqual(simulate(rows, t, BAR, True, 100.0, 0.2, 2.0, 2.0, HOLD), (-1.0, 1000, "SL", 0.0))

    def test_sell_sl_uses_ask(self):
        # bid high 101.9 + spread 0.2 = ask 102.1 >= SL 102
        rows, t = m1([(1000, 101.9, 99.5, 100), (1660, 100, 100, 100)])
        self.assertEqual(simulate(rows, t, BAR, False, 100.0, 0.2, 2.0, 2.0, HOLD), (-1.0, 1000, "SL", 0.0))

    def test_time_exit_at_last_close(self):
        rows, t = m1([(1000, 101, 99.5, 100.5), (1060, 101, 100, 101), (1660, 101, 101, 101)])
        self.assertEqual(simulate(rows, t, BAR, True, 100.0, 0.2, 2.0, 2.0, HOLD), (0.5, 1060, "TIME", 0.5))

    def test_sl_after_favorable_move_keeps_excursion(self):
        rows, t = m1([(1000, 101.5, 99.5, 101), (1060, 101, 97.9, 98), (1660, 98, 98, 98)])
        self.assertEqual(simulate(rows, t, BAR, True, 100.0, 0.2, 2.0, 2.0, HOLD), (-1.0, 1060, "SL", 0.75))

    def test_not_enough_data_gives_none(self):
        rows, t = m1([(1000, 101, 99.5, 100.5)])
        self.assertIsNone(simulate(rows, t, BAR, True, 100.0, 0.2, 2.0, 2.0, HOLD))


class Main(unittest.TestCase):
    def test_defaults_match_ea_m5_profile(self):
        a = scoring.parse_args(["--m1", "x.csv", "log.jsonl"])
        self.assertEqual((a.sl_min, a.sl_max, a.rr_min, a.rr_max, a.tp_max_atr, a.hold_bars),
                         (1.0, 2.0, 1.2, 2.0, 3.0, 12))

    def test_scores_m5_record(self):
        with tempfile.TemporaryDirectory() as d:
            m1p, logp = os.path.join(d, "m1.csv"), os.path.join(d, "log.jsonl")
            with open(m1p, "w") as f:
                f.write("time,high,low,close\n")
                f.writelines(f"{t},100.1,99.9,100\n" for t in range(0, 7200, 60))
            rec = {"bar": 0, "tf": "PERIOD_M5", "atr": 1.0, "bid": 100.0, "ask": 100.1,
                   "decision": {"action": "BUY", "sl_atr": 1.5, "tp_rr": 1.5, "confidence": 80}}
            with open(logp, "w") as f:
                f.write(json.dumps(rec) + "\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                scoring.main(["--m1", m1p, logp])
            self.assertIn("n=1", out.getvalue())


class ShadowTrades(unittest.TestCase):
    def test_one_position_at_a_time_and_unscored(self):
        rows, t = m1([(x, 100.1, 99.9, 100) for x in range(0, 7200, 60)])
        d = {"action": "BUY", "sl_atr": 1.5, "tp_rr": 1.5, "confidence": 80}
        base = {"tf": "PERIOD_M5", "atr": 1.0, "bid": 100.0, "ask": 100.1, "decision": d}
        recs = [dict(base, bar=0), dict(base, bar=300),  # 300: still in the first position
                dict(base, bar=7200),  # after the M1 data: not scored
                dict(base, bar=0, error="HALT")]
        a = scoring.parse_args(["--m1", "x.csv", "log.jsonl"])
        trades, unscored = scoring.shadow_trades(a, recs, rows, t)
        self.assertEqual([x["rec"]["bar"] for x in trades if x["taken"]], [0])
        self.assertEqual(trades[0]["exit"], "TIME")
        self.assertEqual(unscored, 1)


if __name__ == "__main__":
    unittest.main()
