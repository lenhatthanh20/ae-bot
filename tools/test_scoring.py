import unittest

from scoring import simulate

# M1 rows: (time, high, low, close), bid prices
BAR, HOLD = 1000, 600


def m1(rows):
    return rows, [r[0] for r in rows]


class Simulate(unittest.TestCase):
    def test_buy_hits_tp(self):
        rows, t = m1([(1000, 101, 99.5, 100.5), (1060, 104.5, 100, 104), (1660, 104, 104, 104)])
        self.assertEqual(simulate(rows, t, BAR, True, 100.0, 0.2, 2.0, 2.0, HOLD), (2.0, 1060))

    def test_sl_counts_first_when_both_hit_in_one_bar(self):
        rows, t = m1([(1000, 105, 97, 100), (1660, 100, 100, 100)])
        self.assertEqual(simulate(rows, t, BAR, True, 100.0, 0.2, 2.0, 2.0, HOLD), (-1.0, 1000))

    def test_sell_sl_uses_ask(self):
        # bid high 101.9 + spread 0.2 = ask 102.1 >= SL 102
        rows, t = m1([(1000, 101.9, 99.5, 100), (1660, 100, 100, 100)])
        self.assertEqual(simulate(rows, t, BAR, False, 100.0, 0.2, 2.0, 2.0, HOLD), (-1.0, 1000))

    def test_time_exit_at_last_close(self):
        rows, t = m1([(1000, 101, 99.5, 100.5), (1060, 101, 100, 101), (1660, 101, 101, 101)])
        self.assertEqual(simulate(rows, t, BAR, True, 100.0, 0.2, 2.0, 2.0, HOLD), (0.5, 1060))

    def test_not_enough_data_gives_none(self):
        rows, t = m1([(1000, 101, 99.5, 100.5)])
        self.assertIsNone(simulate(rows, t, BAR, True, 100.0, 0.2, 2.0, 2.0, HOLD))


if __name__ == "__main__":
    unittest.main()
