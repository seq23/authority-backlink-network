#!/usr/bin/env python3
"""The free router must finish inside its wall-clock budget, whatever the server does.

16 Oct 2026, Journalist Query Scan run 38900376756: the selftest's first model
(nemotron-3-ultra) held the connection open for five minutes and only then
returned HTTP 200 with the error body "The operation was aborted"; the second
model answered at once, and the job's timeout cancelled the step 0.02s after
the receipt printed. OpenRouter keeps a slow non-streaming request alive by
sending whitespace. urllib's `timeout=` is a per-socket-read timeout, so every
read succeeded within it and the request had no wall-clock bound at all.

Each scenario runs free_chat in a child process under a hard timeout, against a
local stub that drips keep-alive whitespace and never finishes (the old code
hangs here until the hard timeout kills it), and asserts the router returns a
named outcome promptly. Fails on zero scenarios.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import textwrap
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARD_TIMEOUT_S = 20  # per scenario; a correct router returns in ~2-4s


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *a):  # keep test output to the verdict lines
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        model = body.get("model", "")
        if model.startswith("silent"):
            time.sleep(30)  # accepts the request, never sends a byte
            return
        if model.startswith("drip"):
            # Headers at once, then one keep-alive byte every 0.2s, forever.
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                while True:
                    self.wfile.write(b" ")
                    self.wfile.flush()
                    time.sleep(0.2)
            except (BrokenPipeError, ConnectionResetError, OSError):
                return
        payload = json.dumps({"model": model, "usage": {"cost": 0},
                              "choices": [{"finish_reason": "stop", "message": {"content": "OK"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


CHILD = textwrap.dedent("""
    import json, sys
    sys.path.insert(0, sys.argv[1])
    import free_router as fr
    endpoint, models, timeout = sys.argv[2], json.loads(sys.argv[3]), float(sys.argv[4])
    real = fr.load_config()
    snap = {m: {"prompt": "0", "completion": "0", "request": "0"} for m in models}
    fr.load_config = lambda: {**real, "endpoint": endpoint, "free_models": models,
                              "pricing_snapshot": {"models": snap}}
    fr._KEY_CHECK = {"ok": True, "http_status": 200, "info": {"label": "stub"}}
    r = fr.free_chat([{"role": "user", "content": "hi"}], purpose="deadline_test", timeout=timeout, key="stub")
    print("RESULT " + json.dumps({"ok": r["ok"], "stop": r.get("stop"), "model": r.get("model"),
                                  "attempts": r["receipt"]["attempts"]}), flush=True)
""")

SCENARIOS = [
    # (name, models, budget seconds, expected ok, expected stop, expected model)
    ("every model drips forever -> named stop inside the budget",
     ["drip-a", "drip-b"], 2, False, "NO_FREE_MODEL_ANSWERED", None),
    ("first model drips, second answers -> answered inside the budget",
     ["drip-a", "fast-b"], 3, True, None, "fast-b"),
    ("first model silent, second answers -> answered inside the budget",
     ["silent-a", "fast-b"], 3, True, None, "fast-b"),
]


def main() -> int:
    if not SCENARIOS:
        print("FAIL: zero scenarios")
        return 1
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    endpoint = f"http://127.0.0.1:{srv.server_address[1]}/v1/chat"
    failures = 0
    for name, models, budget, want_ok, want_stop, want_model in SCENARIOS:
        t0 = time.monotonic()
        try:
            p = subprocess.run([sys.executable, "-c", CHILD, str(ROOT / "scripts" / "llm"), endpoint,
                                json.dumps(models), str(budget)],
                               capture_output=True, text=True, timeout=HARD_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            print(f"FAIL [{name}]: free_chat still running after {HARD_TIMEOUT_S}s with a {budget}s budget (hang)")
            failures += 1
            continue
        took = time.monotonic() - t0
        line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
        if p.returncode != 0 or line is None:
            print(f"FAIL [{name}]: exit {p.returncode}; stderr tail: {p.stderr[-400:]}")
            failures += 1
            continue
        r = json.loads(line[len("RESULT "):])
        problems = []
        if r["ok"] is not want_ok:
            problems.append(f"ok={r['ok']}")
        if r["stop"] != want_stop:
            problems.append(f"stop={r['stop']}")
        if want_model and r["model"] != want_model:
            problems.append(f"model={r['model']}")
        if not any(a.get("status") == "timeout" for a in r["attempts"]):
            problems.append(f"no attempt recorded as timeout: {r['attempts']}")
        if took > budget + 5:
            problems.append(f"took {took:.1f}s for a {budget}s budget")
        if problems:
            print(f"FAIL [{name}]: " + "; ".join(problems))
            failures += 1
        else:
            print(f"PASS [{name}] in {took:.1f}s")
    srv.shutdown()
    print(json.dumps({"status": "FAIL" if failures else "PASS", "scenarios": len(SCENARIOS),
                      "hard_failures": failures}))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
