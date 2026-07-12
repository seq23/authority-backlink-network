#!/usr/bin/env python3
"""Shared, dependency-free Authority Network primitives."""
from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse


def norm_domain(value: str) -> str:
    raw = str(value or '').strip()
    host = urlparse(raw).netloc if raw.startswith(('http://', 'https://')) else raw
    host = host.lower().strip().strip('/')
    return host[4:] if host.startswith('www.') else host


def brand_domains(brand: dict) -> set[str]:
    values = brand.get('domains') or [brand.get('domain', '')]
    return {norm_domain(v) for v in values if norm_domain(v)}


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
