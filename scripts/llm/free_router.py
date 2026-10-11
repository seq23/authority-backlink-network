"""Free-only LLM router (Python twin of scripts/llm/free_router.js).

Owner policy, 11 Oct 2026: "nothing should be paid". Reaches only the $0/$0
OpenRouter models in config/llm_routing.json; every request carries
provider.max_price = 0; a non-zero usage.cost raises FreeRouterCostViolation.
No free model answering is a named stop, never a paid fallback. A disabled or
invalid key is its own named stop (OPENROUTER_KEY_DISABLED_OR_INVALID).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "llm_routing.json"
KEY_STOP = "OPENROUTER_KEY_DISABLED_OR_INVALID"
KEY_STOP_DETAIL = "OpenRouter key disabled or invalid; free routing needs an enabled key with a $0 limit"
_KEY_CHECK: dict | None = None


class FreeRouterCostViolation(RuntimeError):
    pass


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


def _http(url: str, key: str, body: dict | None, timeout: int) -> tuple[int, dict | str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        status = e.code
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw


KEY_FIELDS = ("label", "limit", "usage", "is_free_tier", "limit_remaining")


def _check_key(key: str) -> dict:
    """GET /api/v1/auth/key once; keeps only the label/limit/usage fields, never the key."""
    global _KEY_CHECK
    if _KEY_CHECK is None:
        try:
            status, body = _http("https://openrouter.ai/api/v1/auth/key", key, None, 20)
            data = (body.get("data") or {}) if isinstance(body, dict) else {}
            _KEY_CHECK = {"ok": not _is_key_refusal(status, json.dumps(body)), "http_status": status,
                          "info": {f: data.get(f) for f in KEY_FIELDS}}
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            _KEY_CHECK = {"ok": True, "http_status": None, "info": None, "note": f"key preflight unreachable: {e}"}
    return _KEY_CHECK


def free_chat(messages: list[dict], *, max_tokens: int = 1500, temperature: float = 0.2,
              purpose: str = "unspecified", timeout: int = 180, key: str | None = None,
              response_format: dict | None = None) -> dict:
    """Returns {"ok": True, "content", "model", "finish_reason", "receipt"} or {"ok": False, "stop", "receipt"}."""
    cfg = load_config()
    assert_free_config(cfg)
    receipt = {"purpose": purpose, "policy": "free_only", "max_cost_usd": 0,
               "at": datetime.now(timezone.utc).isoformat(), "outcome": None, "model": None,
               "cost_usd": None, "key_label": None, "key_info": None, "attempts": []}

    def stop(code: str, detail: str, outcome: str) -> dict:
        receipt.update(outcome=outcome, stop=code, stop_detail=detail)
        _emit(receipt)
        return {"ok": False, "stop": code, "receipt": receipt}

    key = (key if key is not None else os.environ.get("OPENROUTER_API_KEY", "")).strip()
    if not key:
        return stop("FREE_ROUTER_NO_KEY", "OPENROUTER_API_KEY is not set; no model was called and nothing was paid", "credential_missing")
    kc = _check_key(key)
    receipt["key_label"] = (kc.get("info") or {}).get("label")
    receipt["key_info"] = kc.get("info")
    if not kc["ok"]:
        return stop(KEY_STOP, f"{KEY_STOP_DETAIL} (GET /api/v1/auth/key HTTP {kc['http_status']})", "credential_refused")
    for model in cfg["free_models"]:
        body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature,
                "usage": {"include": True}, "provider": {"max_price": {"prompt": 0, "completion": 0, "request": 0}}}
        if response_format:
            body["response_format"] = response_format
        try:
            status, data = _http(cfg["endpoint"], key, body, timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
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
                       cost_usd=None if cost is None else float(cost))
        _emit(receipt)
        return {"ok": True, "content": content, "model": receipt["model"],
                "finish_reason": choice.get("finish_reason"), "receipt": receipt}
    return stop("NO_FREE_MODEL_ANSWERED",
                f"none of {len(cfg['free_models'])} free models answered; no paid fallback exists by owner policy",
                "no_free_model_answered")


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        free_chat([{"role": "user", "content": "Reply with the single word OK."}], max_tokens=200, temperature=0, purpose="selftest")
