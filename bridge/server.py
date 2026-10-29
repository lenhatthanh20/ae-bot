"""AIGold bridge: the EA posts market data, Claude proposes, the EA decides.

The reply is always HTTP 200 with one line: ACTION;sl_atr;tp_rr;confidence;bar
ACTION is BUY, SELL or NONE. Any error, HALT file or budget stop gives NONE.
"""
import hashlib
import json
import math
import os
import pathlib
import subprocess
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent
PROMPT = (ROOT / "prompt.md").read_text(encoding="utf-8")
PROMPT_SHA = hashlib.sha256(PROMPT.encode()).hexdigest()[:12]
LOG_DIR = ROOT.parent / "logs"
HALT_FILE = ROOT.parent / "HALT"
EMPTY_DIR = ROOT / "empty"  # cwd for claude -p, so no project CLAUDE.md is loaded

MODE = os.environ.get("AI_MODE", "fake")
MODEL = os.environ.get("BRIDGE_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("BRIDGE_EFFORT", "low")
DAILY_USD_CAP = float(os.environ.get("DAILY_USD_CAP", "3"))
PORT = int(os.environ.get("PORT", "8000"))

# USD per 1M tokens (input, output), from the 2026-10 price list. Re-check before trusting cost numbers.
PRICES = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}

SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["BUY", "SELL", "NONE"]},
        "sl_atr": {"type": "number"},
        "tp_rr": {"type": "number"},
        "confidence": {"type": "integer"},
        "reason": {"type": "string"},
    },
    "required": ["action", "sl_atr", "tp_rr", "confidence", "reason"],
    "additionalProperties": False,
}


def parse_request(body):
    """First line: key=value pairs split by ';'. The rest is CSV for the model."""
    head = body.split("\n", 1)[0]
    meta = dict(kv.split("=", 1) for kv in head.strip().split(";") if "=" in kv)
    int(meta["bar"])
    for key in ("bid", "ask", "atr"):
        if not math.isfinite(float(meta[key])):
            raise ValueError(f"bad {key}")
    return meta


def to_line(decision, bar):
    """Shape check only. Range rules live in the EA (single source of truth)."""
    none = f"NONE;0;0;0;{bar}"
    if not isinstance(decision, dict):
        return none
    action = str(decision.get("action", "")).upper()
    if action not in ("BUY", "SELL"):
        return none
    try:
        sl_atr = float(decision["sl_atr"])
        rr = float(decision["tp_rr"])
        conf = int(decision["confidence"])
    except (KeyError, TypeError, ValueError):
        return none
    if not (math.isfinite(sl_atr) and math.isfinite(rr) and sl_atr > 0 and rr > 0 and 0 <= conf <= 100):
        return none
    return f"{action};{sl_atr:.2f};{rr:.2f};{conf};{bar}"


def ask_fake(payload):
    action = os.environ.get("FAKE_ACTION", "BUY")
    return {"action": action, "sl_atr": 1.5, "tp_rr": 2.0, "confidence": 80, "reason": "fake"}, {"usd": 0.0}


_client = None


def ask_api(payload):
    global _client
    import anthropic  # only needed in api mode

    if _client is None:
        # timeout x (retries + 1) must stay under the EA timeout (60 s)
        _client = anthropic.Anthropic(timeout=25.0, max_retries=1)
    # No server-side fallbacks: a refusal must stay NONE, not switch model mid-sample.
    r = _client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=PROMPT,
        messages=[{"role": "user", "content": payload}],
        output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
    )
    pin, pout = PRICES.get(MODEL, (0.0, 0.0))
    usage = {
        "in": r.usage.input_tokens,
        "out": r.usage.output_tokens,
        "stop": r.stop_reason,
        "usd": (r.usage.input_tokens * pin + r.usage.output_tokens * pout) / 1e6,
    }
    if r.stop_reason != "end_turn":  # refusal or max_tokens -> NONE
        return None, usage
    text = next(b.text for b in r.content if b.type == "text")
    return json.loads(text), usage


def ask_cli(payload):
    # Smoke test only. Still loads ~/.claude (global CLAUDE.md, hooks); --bare would drop the subscription login.
    EMPTY_DIR.mkdir(exist_ok=True)
    cmd = [os.environ.get("CLAUDE_BIN", "claude"), "-p", "--model", MODEL,
           "--output-format", "json", "--json-schema", json.dumps(SCHEMA),
           "--system-prompt", PROMPT]
    r = subprocess.run(cmd, input=payload, capture_output=True, text=True, timeout=55, cwd=EMPTY_DIR)
    out = json.loads(r.stdout)
    return out.get("structured_output"), {"usd": out.get("total_cost_usd") or 0.0}


ASKERS = {"fake": ask_fake, "api": ask_api, "cli": ask_cli}


def log_path(now):
    return LOG_DIR / f"decisions-{now:%Y-%m}.jsonl"


def spent_today(now):
    # shortcut: re-reads the monthly log each call; fine at ~50 calls/day, move to a counter if it gets slow
    path, day, total = log_path(now), now.strftime("%Y-%m-%d"), 0.0
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            if rec["ts"].startswith(day):
                total += (rec.get("usage") or {}).get("usd") or 0.0
    return total


def decide(body, ask=None):
    now = datetime.now(timezone.utc)
    rec = {"ts": now.isoformat(timespec="seconds"), "mode": MODE, "model": MODEL,
           "effort": EFFORT, "prompt_sha": PROMPT_SHA}
    bar, t0 = "0", time.monotonic()
    try:
        meta = parse_request(body)
        bar = meta["bar"]
        rec.update(meta)
        if HALT_FILE.exists():
            rec["error"] = "HALT"
        elif spent_today(now) >= DAILY_USD_CAP:
            rec["error"] = "USD_CAP"
        else:
            decision, usage = (ask or ASKERS[MODE])(body)
            rec.update(decision=decision, usage=usage)
    except Exception as e:  # any failure must answer NONE, never break the EA call
        rec["error"] = repr(e)[:300]
    line = f"NONE;0;0;0;{bar}" if "error" in rec else to_line(rec.get("decision"), bar)
    rec.update(line=line, latency_ms=int((time.monotonic() - t0) * 1000), payload=body)
    LOG_DIR.mkdir(exist_ok=True)
    with log_path(now).open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    print(f"{rec['ts']} {line} {rec.get('latency_ms')}ms {rec.get('error', '')}", flush=True)
    return line


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._send(200, "ok")
        else:
            self._send(404, "not found")

    def do_POST(self):
        if self.path != "/decide":
            return self._send(404, "not found")
        size = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(size).decode("utf-8", "replace")
        self._send(200, decide(body))

    def log_message(self, *args):
        pass  # decide() prints one line per call

    def _send(self, code, text):
        data = (text + "\n").encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    print(f"bridge 127.0.0.1:{PORT} mode={MODE} model={MODEL} effort={EFFORT} prompt={PROMPT_SHA}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
