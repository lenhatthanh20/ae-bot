# tools/compare_models.py - run from the repo root: .venv/bin/python tools/compare_models.py logs/decisions-2026-11.jsonl
import json
import sys

sys.path.insert(0, "bridge")
import server  # noqa: E402

recs = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
recs = [r for r in recs if r.get("mode") == "cli" and "payload" in r][-20:]
for model in ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"):
    server.MODEL = model
    out = [server.ask_cli(r["payload"]) for r in recs]
    acts = "".join((d or {}).get("action", "E")[0] for d, _ in out)
    print(f"{model:20} {acts}  usd={sum(u['usd'] for _, u in out):.3f}")
