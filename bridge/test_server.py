import json
import pathlib
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

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


class AskCli(unittest.TestCase):
    def run_with(self, result):
        calls = []
        def fake_run(cmd, **kw):
            calls.append(cmd)
            return result
        with mock.patch.object(server.subprocess, "run", fake_run):
            out = server.ask_cli(BODY)
        return out, calls[0]

    def test_returns_structured_output(self):
        stdout = json.dumps({"subtype": "success", "total_cost_usd": 0.05,
                             "structured_output": {"action": "SELL"}})
        (decision, usage), cmd = self.run_with(subprocess.CompletedProcess([], 0, stdout, ""))
        self.assertEqual(decision, {"action": "SELL"})
        self.assertEqual(usage, {"usd": 0.05, "stop": "success"})
        self.assertIn("--safe-mode", cmd)
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")

    def test_nonzero_exit_raises_with_stderr(self):
        with self.assertRaisesRegex(RuntimeError, "not logged in"):
            self.run_with(subprocess.CompletedProcess([], 1, "", "not logged in"))


class ClientAllowed(unittest.TestCase):
    def test_default_allows_localhost_only(self):
        self.assertEqual(server.ALLOW_IPS, {"127.0.0.1"})
        self.assertTrue(server.client_allowed("127.0.0.1"))
        self.assertFalse(server.client_allowed("192.0.2.10"))

    def test_lan_list(self):
        with mock.patch.object(server, "ALLOW_IPS", server.parse_ips(" 127.0.0.1, 192.0.2.10 ,")):
            self.assertTrue(server.client_allowed("192.0.2.10"))
            self.assertTrue(server.client_allowed("127.0.0.1"))
            self.assertFalse(server.client_allowed("192.0.2.11"))
            self.assertFalse(server.client_allowed(""))


class HandlerAllowlist(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        server.LOG_DIR = pathlib.Path(self.tmp.name) / "logs"
        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def call(self, path, body=None):
        try:
            with urllib.request.urlopen(self.url + path, data=body, timeout=5) as r:
                return r.status, r.read().decode().strip()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode().strip()

    def test_allowed_client_gets_answer(self):
        self.assertEqual(self.call("/health"), (200, "ok"))

    def test_rejected_client_gets_403_without_work(self):
        asked = mock.Mock(side_effect=AssertionError("ask called"))
        with mock.patch.object(server, "ALLOW_IPS", {"192.0.2.10"}), \
             mock.patch.dict(server.ASKERS, {server.MODE: asked}):
            self.assertEqual(self.call("/health")[0], 403)
            self.assertEqual(self.call("/decide", BODY.encode())[0], 403)
        asked.assert_not_called()
        self.assertFalse(server.LOG_DIR.exists())


if __name__ == "__main__":
    unittest.main()
