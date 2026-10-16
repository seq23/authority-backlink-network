"""Free-only LLM router (Python twin of scripts/llm/free_router.js).

Owner policy, 11 Oct 2026: "nothing should be paid". Reaches only the $0/$0
OpenRouter models in config/llm_routing.json; every request carries
provider.max_price = 0; a non-zero usage.cost raises FreeRouterCostViolation.
No free model answering is a named stop, never a paid fallback. A disabled or
invalid key is its own named stop (OPENROUTER_KEY_DISABLED_OR_INVALID).
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import time
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "llm_routing.json"
KEY_STOP = "OPENROUTER_KEY_DISABLED_OR_INVALID"
KEY_STOP_DETAIL = "OpenRouter key disabled or invalid; free routing needs an enabled key with a $0 limit"
_KEY_CHECK: dict | None = None


class FreeRouterCostViolation(RuntimeError):
    pass


class FreeRouterDeadlineExceeded(TimeoutError):
    """FREE_ROUTER_DEADLINE_EXCEEDED: a request outlived its wall-clock budget.

    urllib's `timeout=` bounds each socket read, not the request. OpenRouter keeps
    a slow non-streaming request alive by sending whitespace, so every read
    returned inside the timeout and one request held the 16 Oct 2026 selftest
    for five minutes until the job was cancelled. Every request here now carries
    a monotonic deadline checked between reads.
    """


def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def assert_free_config(cfg: dict) -> None:
    pol = cfg.get("policy") or {}
    if pol.get("max_cost_usd") != 0 or pol.get("paid_fallback") is not False:
        raise FreeRouterCostViolation("FREE_ROUTER_COST_VIOLATION: policy must be max_cost_usd 0 and paid_fallback false")
    snap = (cfg.get("pricing_snapshot") or {}).get("models") or {}
    if not cfg.get("free_models"):
        raise FreeRouterCostViolation("FREE_ROUTER_COST_VIOLATION: no free models configured")
    for m in cfg["free_models"]:
        p = snap.get(m) or {}
        if str(p.get("prompt")) != "0" or str(p.get("completion")) != "0":
            raise FreeRouterCostViolation(f"FREE_ROUTER_COST_VIOLATION: {m} is not priced $0/$0 in the committed snapshot")


def _emit(receipt: dict) -> None:
    print("FREE_LLM_RECEIPT " + json.dumps(receipt), flush=True)
    if receipt.get("stop"):
        print(f"NAMED_STOP: {receipt['stop']} - {receipt['stop_detail']}", flush=True)


def _is_key_refusal(status: int | None, message: str) -> bool:
    import re
    if status == 401:
        return True
    return status == 403 and bool(re.search(r"key|disabled|limit|credit|unauthori[sz]ed", message or "", re.I)) \
        and not re.search(r"model|provider|region", message or "", re.I)


def _http(url: str, key: str, body: dict | None, timeout: float) -> tuple[int, dict | str]:
    """One request bounded by `timeout` seconds of WALL-CLOCK time, not per read.

    Raises FreeRouterDeadlineExceeded when the budget runs out, however the
    server behaves (silent, or dripping keep-alive bytes that never end).
    """
    deadline = time.monotonic() + max(float(timeout), 0.0)

    def remaining() -> float:
        left = deadline - time.monotonic()
        if left <= 0:
            raise FreeRouterDeadlineExceeded(f"FREE_ROUTER_DEADLINE_EXCEEDED: {url} gave no complete response within {timeout:.0f}s")
        return left

    u = urllib.parse.urlsplit(url)
    conn_cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(u.hostname, u.port, timeout=remaining())
    data = json.dumps(body).encode() if body is not None else None
    try:
        conn.request("POST" if body is not None else "GET", (u.path or "/") + (f"?{u.query}" if u.query else ""),
                     body=data, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        sock = conn.sock  # getresponse() may detach it from conn; reads still use it
        sock.settimeout(remaining())
        resp = conn.getresponse()
        status, chunks = resp.status, []
        while True:
            sock.settimeout(remaining())
            chunk = resp.read1(65536)
            if not chunk:
                break
            chunks.append(chunk)
        raw = b"".join(chunks).decode("utf-8", "replace")
    except FreeRouterDeadlineExceeded:
        raise
    except (socket.timeout, TimeoutError) as e:
        # Every socket timeout above is set to the budget left, so it firing
        # means the budget is spent: name it rather than leak a bare "timed out".
        raise FreeRouterDeadlineExceeded(f"FREE_ROUTER_DEADLINE_EXCEEDED: {url} gave no complete response within {timeout:.0f}s") from e
    finally:
        conn.close()
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw


# The selftest proves the router answers; it must leave the scan most of the
# workflow's 5-minute job. A healthy free model answers in ~1-2s.
SELFTEST_BUDGET_S = 90

KEY_FIELDS = ("label", "limit", "usage", "is_free_tier", "limit_remaining")


def _check_key(key: str, timeout: float = 20) -> dict:
    """GET /api/v1/auth/key once; keeps only the label/limit/usage fields, never the key."""
    global _KEY_CHECK
    if _KEY_CHECK is None:
        try:
            status, body = _http("https://openrouter.ai/api/v1/auth/key", key, None, timeout)
            data = (body.get("data") or {}) if isinstance(body, dict) else {}
            _KEY_CHECK = {"ok": not _is_key_refusal(status, json.dumps(body)), "http_status": status,
                          "info": {f: data.get(f) for f in KEY_FIELDS}}
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as e:
            _KEY_CHECK = {"ok": True, "http_status": None, "info": None, "note": f"key preflight unreachable: {e}"}
    return _KEY_CHECK


def free_chat(messages: list[dict], *, max_tokens: int = 1500, temperature: float = 0.2,
              purpose: str = "unspecified", timeout: float = 180, key: str | None = None,
              response_format: dict | None = None) -> dict:
    """Returns {"ok": True, "content", "model", "finish_reason", "receipt"} or {"ok": False, "stop", "receipt"}.

    `timeout` is the WALL-CLOCK budget for the whole call (key check and every
    model attempt together). Each non-last model gets half of what is left, the
    last gets the rest, so one stuck model cannot starve the fallbacks and the
    call always returns a named outcome inside the budget.
    """
    started = time.monotonic()
    budget_end = started + float(timeout)
    cfg = load_config()
    assert_free_config(cfg)
    receipt = {"purpose": purpose, "policy": "free_only", "max_cost_usd": 0,
               "at": datetime.now(timezone.utc).isoformat(), "outcome": None, "model": None,
               "cost_usd": None, "key_label": None, "key_info": None, "attempts": []}

    def stop(code: str, detail: str, outcome: str) -> dict:
        receipt.update(outcome=outcome, stop=code, stop_detail=detail,
                       elapsed_s=round(time.monotonic() - started, 2))
        _emit(receipt)
        return {"ok": False, "stop": code, "receipt": receipt}

    key = (key if key is not None else os.environ.get("OPENROUTER_API_KEY", "")).strip()
    if not key:
        return stop("FREE_ROUTER_NO_KEY", "OPENROUTER_API_KEY is not set; no model was called and nothing was paid", "credential_missing")
    kc = _check_key(key, min(20.0, max(budget_end - time.monotonic(), 0.0)))
    receipt["key_label"] = (kc.get("info") or {}).get("label")
    receipt["key_info"] = kc.get("info")
    if not kc["ok"]:
        return stop(KEY_STOP, f"{KEY_STOP_DETAIL} (GET /api/v1/auth/key HTTP {kc['http_status']})", "credential_refused")
    models = cfg["free_models"]
    for i, model in enumerate(models):
        left = budget_end - time.monotonic()
        if left <= 0:
            receipt["attempts"].append({"model": model, "status": "timeout", "error": "FREE_ROUTER_DEADLINE_EXCEEDED: budget spent before this model"})
            continue
        attempt_budget = left if i == len(models) - 1 else left / 2
        body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature,
                "usage": {"include": True}, "provider": {"max_price": {"prompt": 0, "completion": 0, "request": 0}}}
        if response_format:
            body["response_format"] = response_format
        try:
            status, data = _http(cfg["endpoint"], key, body, attempt_budget)
        except FreeRouterDeadlineExceeded as e:
            receipt["attempts"].append({"model": model, "status": "timeout", "error": str(e)[:200]})
            continue
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as e:
            receipt["attempts"].append({"model": model, "status": "error", "error": str(e)[:200]})
            continue
        if not isinstance(data, dict) or status != 200 or data.get("error"):
            msg = str((data.get("error") or {}).get("message", "") if isinstance(data, dict) else data)[:200]
            receipt["attempts"].append({"model": model, "status": "refused", "http_status": status, "error": msg})
            if _is_key_refusal(status, msg):
                return stop(KEY_STOP, f"{KEY_STOP_DETAIL} (HTTP {status} on {model})", "credential_refused")
            continue
        cost = (data.get("usage") or {}).get("cost")
        if cost is not None and float(cost) != 0:
            receipt["attempts"].append({"model": model, "status": "cost_violation", "cost_usd": cost})
            _emit(receipt)
            raise FreeRouterCostViolation(f"FREE_ROUTER_COST_VIOLATION: {model} reported cost {cost} USD; the free-only policy allows 0")
        choice = (data.get("choices") or [{}])[0]
        content = ((choice.get("message") or {}).get("content")) or ""
        if not content.strip():
            receipt["attempts"].append({"model": model, "status": "empty"})
            continue
        receipt["attempts"].append({"model": model, "status": "ok"})
        receipt.update(outcome="free_model_answered", model=data.get("model") or model,
                       cost_usd=None if cost is None else float(cost), elapsed_s=round(time.monotonic() - started, 2))
        _emit(receipt)
        return {"ok": True, "content": content, "model": receipt["model"],
                "finish_reason": choice.get("finish_reason"), "receipt": receipt}
    return stop("NO_FREE_MODEL_ANSWERED",
                f"none of {len(cfg['free_models'])} free models answered; no paid fallback exists by owner policy",
                "no_free_model_answered")


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        free_chat([{"role": "user", "content": "Reply with the single word OK."}], max_tokens=200, temperature=0, purpose="selftest",
                  timeout=SELFTEST_BUDGET_S)
