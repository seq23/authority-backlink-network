#!/usr/bin/env python3
"""Single content-addressed validation cache. Cache accelerates proof; it never decides truth."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_ROOT = ROOT / ".validation-cache"
OBJECTS = CACHE_ROOT / "objects"
INDEX = CACHE_ROOT / "page-index.json"
VERSION_FILE = CACHE_ROOT / "version"
CACHE_SCHEMA = "authority-validation-cache-v1"
VALIDATION_EPOCH = os.getenv("VALIDATION_EPOCH", "v4.5.0")


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        tmp.write(data)
        tmp.flush()
        os.fsync(tmp.fileno())
        temp = Path(tmp.name)
    temp.replace(path)


def initialize() -> None:
    OBJECTS.mkdir(parents=True, exist_ok=True)
    atomic_write(VERSION_FILE, f"{CACHE_SCHEMA}:{VALIDATION_EPOCH}\n".encode())
    if not INDEX.exists():
        atomic_write(INDEX, b"{}\n")


def load_index() -> dict:
    initialize()
    try:
        value = json.loads(INDEX.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_index(index: dict) -> None:
    atomic_write(INDEX, json.dumps(index, indent=2, sort_keys=True).encode() + b"\n")


def fingerprint(page_hash: str, dependencies: dict, profile: str) -> str:
    return digest({
        "schema": CACHE_SCHEMA,
        "epoch": VALIDATION_EPOCH,
        "page_hash": page_hash,
        "dependencies": dependencies,
        "profile": profile,
    })


def get(path: str, fp: str) -> dict | None:
    index = load_index()
    object_hash = index.get(path, {}).get("object_hash")
    if not object_hash:
        return None
    object_path = OBJECTS / object_hash[:2] / f"{object_hash}.json"
    try:
        receipt = json.loads(object_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if receipt.get("fingerprint") != fp:
        return None
    if receipt.get("status") not in {"PASS", "PASS_WITH_SOFT_WARNING", "PASS_WITH_STRONG_WARNING"}:
        return None
    if digest(receipt.get("result")) != receipt.get("result_hash"):
        return None
    return receipt


def put(path: str, fp: str, result: dict) -> dict:
    status = result.get("status")
    if status not in {"PASS", "PASS_WITH_SOFT_WARNING", "PASS_WITH_STRONG_WARNING"}:
        raise ValueError("Only successful proof may be cached")
    receipt = {
        "schema": CACHE_SCHEMA,
        "epoch": VALIDATION_EPOCH,
        "fingerprint": fp,
        "status": status,
        "result_hash": digest(result),
        "result": result,
    }
    object_hash = digest(receipt)
    object_path = OBJECTS / object_hash[:2] / f"{object_hash}.json"
    atomic_write(object_path, json.dumps(receipt, indent=2, sort_keys=True).encode() + b"\n")
    index = load_index()
    index[path] = {"fingerprint": fp, "object_hash": object_hash}
    save_index(index)
    return receipt


def clear() -> None:
    if not CACHE_ROOT.exists():
        return
    import shutil
    shutil.rmtree(CACHE_ROOT)
