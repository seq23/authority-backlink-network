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


def _object_path(object_hash: str) -> Path:
    return OBJECTS / object_hash[:2] / f"{object_hash}.json"


def _drop_object(object_hash: str | None) -> None:
    """Delete a superseded receipt.

    get() resolves objects only through the index, so once an entry stops
    pointing at an object hash nothing can ever read it again. Leaving it on
    disk is pure dead weight.
    """
    if not object_hash:
        return
    try:
        _object_path(object_hash).unlink()
    except OSError:
        pass


def prune(dry_run: bool = False) -> dict:
    """Mark-and-sweep the object store against the index.

    The index holds exactly one object hash per page, so every revalidation of a
    changed page stranded the receipt it replaced and nothing ever collected it.
    That is how 3,129 objects accumulated behind 569 live entries - about 82%
    unreachable, since get() can only reach an object the index still names.

    put() now drops what it displaces, so this sweep exists for the cases it
    cannot see: pages deleted from the site, entries removed by a rotated epoch,
    and receipts stranded by an interrupted run.
    """
    index = load_index()
    live = {entry.get("object_hash") for entry in index.values() if isinstance(entry, dict)}
    live.discard(None)

    scanned = removed = kept = reclaimed = 0
    if OBJECTS.exists():
        for shard in sorted(OBJECTS.iterdir()):
            if not shard.is_dir():
                continue
            for obj in sorted(shard.iterdir()):
                if not obj.is_file():
                    continue
                scanned += 1
                if obj.stem in live and obj.suffix == ".json":
                    kept += 1
                    continue
                try:
                    size = obj.stat().st_size
                except OSError:
                    size = 0
                if not dry_run:
                    try:
                        obj.unlink()
                    except OSError:
                        continue
                removed += 1
                reclaimed += size
            # Drop shard directories the sweep emptied rather than leaving stubs.
            if not dry_run:
                try:
                    if not any(shard.iterdir()):
                        shard.rmdir()
                except OSError:
                    pass

    return {
        "status": "PASS",
        "mode": "dry-run" if dry_run else "apply",
        "epoch": VALIDATION_EPOCH,
        "live_entries": len(index),
        "live_objects": len(live),
        "objects_scanned": scanned,
        "objects_kept": kept,
        "objects_removed": removed,
        "bytes_reclaimed": reclaimed,
    }


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
    atomic_write(_object_path(object_hash), json.dumps(receipt, indent=2, sort_keys=True).encode() + b"\n")
    index = load_index()
    # The index keeps only the current object per page, so whatever it pointed at
    # before this write becomes unreachable the moment the index is saved. Not
    # deleting it is what let the store grow to 3,129 objects behind 569 entries.
    prior = index.get(path) or {}
    prior_hash = prior.get("object_hash") if isinstance(prior, dict) else None
    index[path] = {"fingerprint": fp, "object_hash": object_hash}
    save_index(index)
    # Only after the index no longer references it, so an interrupted put cannot
    # leave a live entry pointing at a deleted object.
    if prior_hash and prior_hash != object_hash:
        _drop_object(prior_hash)
    return receipt


def clear() -> None:
    if not CACHE_ROOT.exists():
        return
    import shutil
    shutil.rmtree(CACHE_ROOT)
