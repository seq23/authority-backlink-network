#!/usr/bin/env python3
"""Hostile fixtures for validation cache safety."""
from __future__ import annotations
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validation import cache

original_root = cache.CACHE_ROOT
original_objects = cache.OBJECTS
original_index = cache.INDEX
original_version = cache.VERSION_FILE

with tempfile.TemporaryDirectory() as td:
    base = Path(td) / ".validation-cache"
    cache.CACHE_ROOT = base
    cache.OBJECTS = base / "objects"
    cache.INDEX = base / "page-index.json"
    cache.VERSION_FILE = base / "version"
    fp = cache.fingerprint("page", {"dep": "1"}, "release", True)
    result = {"status": "PASS", "path": "sites/test.html", "proof": "ok"}
    cache.put("sites/test.html", fp, result)
    assert cache.get("sites/test.html", fp) is not None, "expected cache hit"
    assert cache.get("sites/test.html", cache.fingerprint("changed", {"dep": "1"}, "release", True)) is None, "changed page must miss"
    assert cache.get("sites/test.html", cache.fingerprint("page", {"dep": "2"}, "release", True)) is None, "dependency change must miss"
    # A result produced without repair must never satisfy a repairing run. Before
    # allow_repair joined the key, `release --no-repair` cached an un-repaired
    # page and the next repairing `release` hit that entry and repaired nothing.
    assert cache.get("sites/test.html", cache.fingerprint("page", {"dep": "1"}, "release", False)) is None, \
        "a no-repair result must not satisfy a repairing run"
    try:
        cache.put("bad", fp, {"status": "FAIL"})
        raise AssertionError("FAIL result was cached")
    except ValueError:
        pass
    index = cache.load_index()
    obj = cache.OBJECTS / index["sites/test.html"]["object_hash"][:2] / f'{index["sites/test.html"]["object_hash"]}.json'
    obj.write_text("{broken", encoding="utf-8")
    assert cache.get("sites/test.html", fp) is None, "corrupt object must be discarded"

cache.CACHE_ROOT = original_root
cache.OBJECTS = original_objects
cache.INDEX = original_index
cache.VERSION_FILE = original_version
print(json.dumps({"status": "PASS", "fixtures": 5}, indent=2))
