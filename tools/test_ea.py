"""Static checks on the EA source and README. MQL5 cannot run here, so check names and log formats."""
import re
import unittest
from pathlib import Path

import stats

ROOT = Path(__file__).resolve().parent.parent
EA = (ROOT / "mt5" / "AIGold.mq5").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


class EaSource(unittest.TestCase):
    def test_removed_names(self):
        for name in ("InpMaxDriftAtr", "InpLots", "InpMaxTradesPerDay", "TRADES_DAY", "InpMaxDailyLossPct",
                     "InpMaxDrawdownPct", "DailyLossHit", "TradesToday", "g_gvDay", "g_gvEq", "g_gvPeak",
                     "DAILY_LOSS", "MAX_DD", '"RISK"'):
            self.assertNotIn(name, EA, name)
        for name in ("InpMaxDriftAtr", "InpLots", "InpMaxTradesPerDay", "TRADES_DAY"):
            self.assertNotIn(name, README, name)

    def test_new_inputs(self):
        for name, val in (("InpMaxAdverseSl", "0.2"), ("InpMaxFavorSl", "0.5"), ("InpMaxLossUsd", "10.0"),
                          ("InpMaxLossStreak", "4"), ("InpMaxRiskPct", "1.0")):
            self.assertRegex(EA, rf"input\s+\w+\s+{name}\s*=\s*{re.escape(val)};")
        self.assertIn('"LOSS_STREAK"', EA)
        self.assertIn('"LOSS_USD"', EA)
        self.assertIn("SKIP LOSS_STREAK", README)

    def test_drift_after_validate(self):
        tick = EA[EA.index("void OnTick()"):]
        self.assertLess(tick.index("Validate("), tick.index("DRIFT"))
        self.assertLess(tick.index("DRIFT"), tick.index("Execute("))


class EventFormats(unittest.TestCase):
    def test_new_details_still_count(self):
        ev = [{"bar": 1, "event": e, "detail": x} for e, x in [
            ("SKIP", "DRIFT BUY drift=0.25"), ("SKIP", "LOSS_STREAK"), ("REJECT", "LOSS_USD SELL conf=80"),
            ("DRYRUN", "BUY conf=80 drift=0.15 lots=0.02 loss=8.00"),
            ("ORDER", "ok SELL rc=10009 fill=2000.00 conf=75 drift=-0.40 lots=0.12 loss=48.00")]]
        f = stats.funnel(ev)
        self.assertEqual(f["skip_after_ai"], {"DRIFT": 1})
        self.assertEqual(f["skip_before_ai"], {"LOSS_STREAK": 1})
        self.assertEqual(f["reject"], {"LOSS_USD": 1})
        self.assertEqual((f["dryrun"], f["order_ok"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
