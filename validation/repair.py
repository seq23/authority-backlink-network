#!/usr/bin/env python3
"""Bounded generated-page repair. One pass only; never invent facts."""
from __future__ import annotations

import html
import re
from pathlib import Path


def _description_from_html(source: str) -> str:
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", source, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", h1.group(1) if h1 else "Practical planning resource")
    text = " ".join(html.unescape(text).split())
    return (text[:150].rstrip(" .") + ".") if text else "Practical planning resource."


def repair_once(path: Path, finding_codes: set[str]) -> list[str]:
    """Repair only deterministic mechanical defects on generated daily pages."""
    if "/daily/" not in path.as_posix():
        return []
    source = path.read_text(encoding="utf-8")
    original = source
    repairs: list[str] = []

    if "MISSING_HTML_LANG" in finding_codes and re.search(r"<html(?![^>]*\blang=)", source, flags=re.I):
        source = re.sub(r"<html([^>]*)>", lambda m: f'<html lang="en"{m.group(1)}>', source, count=1, flags=re.I)
        repairs.append("added_html_lang")

    if "MISSING_META_DESCRIPTION" in finding_codes and not re.search(r'<meta\s+[^>]*name=["\']description["\']', source, flags=re.I):
        desc = html.escape(_description_from_html(source), quote=True)
        tag = f'<meta name="description" content="{desc}">'
        if re.search(r"</head>", source, flags=re.I):
            source = re.sub(r"</head>", tag + "\n</head>", source, count=1, flags=re.I)
            repairs.append("added_meta_description")

    if "DUPLICATE_EXTERNAL_LINK" in finding_codes:
        seen: set[tuple[str, str]] = set()
        pattern = re.compile(r'(<a\s+[^>]*href=["\'](https?://[^"\']+)["\'][^>]*>)(.*?)(</a>)', re.I | re.S)
        def dedupe(match: re.Match[str]) -> str:
            key = (match.group(2).rstrip("/"), re.sub(r"<[^>]+>", "", match.group(3)).strip().lower())
            if key in seen:
                repairs.append("removed_duplicate_external_link")
                return re.sub(r"<[^>]+>", "", match.group(3))
            seen.add(key)
            return match.group(0)
        source = pattern.sub(dedupe, source)

    if source != original:
        path.write_text(source, encoding="utf-8")
    return repairs
