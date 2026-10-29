import json
import pathlib
import tempfile
import unittest

import server

BODY = ("bar=1767225600;sym=XAUUSD;tf=PERIOD_M15;bid=2650.10;ask=2650.40;atr=5.20\n"
        "# tf\ntime,open,high,low,close,ema20,ema50,ema200,rsi14,atr14\n")


class ToLine(unittest.TestCase):
    def test_buy_formats_with_dot_decimals(self):
        d = {"action": "buy", "sl_atr": 1.5, "tp_rr": 2, "confidence": 72, "reason": "x"}
        self.assertEqual(server.to_line(d, "1"), "BUY;1.50;2.00;72;1")

    def test_bad_inputs_give_none(self):
        bad = [None, {}, {"action": "HOLD"},
               {"action": "BUY", "sl_atr": "x", "tp_rr": 2, "confidence": 70},
               {"action": "SELL", "sl_atr": float("nan"), "tp_rr": 2, "confidence": 70},
               {"action": "SELL", "sl_atr": 1.0, "tp_rr": 2, "confidence": 150},
               {"action": "SELL", "sl_atr": -1.0, "tp_rr": 2, "confidence": 70}]
        for d in bad:
            self.assertEqual(server.to_line(d, "7"), "NONE;0;0;0;7", d)


class Decide(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        server.LOG_DIR = pathlib.Path(self.tmp.name)
        server.HALT_FILE = pathlib.Path(self.tmp.name) / "HALT"

    def tearDown(self):
        self.tmp.cleanup()

    def test_fake_buy_is_logged(self):
        self.assertEqual(server.decide(BODY, ask=server.ask_fake), "BUY;1.50;2.00;80;1767225600")
        rec = json.loads(next(server.LOG_DIR.glob("*.jsonl")).read_text().splitlines()[-1])
        self.assertEqual(rec["bar"], "1767225600")
        self.assertEqual(rec["prompt_sha"], server.PROMPT_SHA)

    def test_ask_error_gives_none(self):
        def boom(_):
            raise TimeoutError
        self.assertEqual(server.decide(BODY, ask=boom), "NONE;0;0;0;1767225600")

    def test_halt_file_gives_none(self):
        server.HALT_FILE.touch()
        self.assertEqual(server.decide(BODY, ask=server.ask_fake), "NONE;0;0;0;1767225600")

    def test_usd_cap_gives_none(self):
        def pricey(_):
            return {"action": "BUY", "sl_atr": 1.5, "tp_rr": 2, "confidence": 80}, {"usd": 99.0}
        server.decide(BODY, ask=pricey)
        self.assertEqual(server.decide(BODY, ask=server.ask_fake), "NONE;0;0;0;1767225600")

    def test_garbage_body_gives_none(self):
        self.assertEqual(server.decide("garbage", ask=server.ask_fake), "NONE;0;0;0;0")


if __name__ == "__main__":
    unittest.main()
