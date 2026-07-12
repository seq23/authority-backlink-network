#!/usr/bin/env python3
"""Shared final-state HTML audit engine for Authority Network v4.5."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SITES_ROOT = ROOT / "sites"
WORD_TARGET_MIN = 450


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_bytes(payload.encode("utf-8"))


def norm_domain(value: str) -> str:
    host = urlparse(value).netloc if value.startswith(("http://", "https://")) else value
    return host.lower().removeprefix("www.").strip("/")


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.h1: list[str] = []
        self.text: list[str] = []
        self.links: list[dict[str, str]] = []
        self.meta: dict[str, str] = {}
        self.canonical = ""
        self.html_lang = ""
        self.schemas: list[object] = []
        self._capture_title = False
        self._capture_h1 = False
        self._capture_script = False
        self._current_link: dict[str, str] | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        amap = {k.lower(): (v or "") for k, v in attrs}
        if tag.lower() == "html":
            self.html_lang = amap.get("lang", "")
        elif tag.lower() == "title":
            self._capture_title = True
            self._buffer = []
        elif tag.lower() == "h1":
            self._capture_h1 = True
            self._buffer = []
        elif tag.lower() == "a":
            self._current_link = {"href": amap.get("href", ""), "anchor": ""}
            self._buffer = []
        elif tag.lower() == "meta":
            key = (amap.get("name") or amap.get("property") or "").lower()
            if key:
                self.meta[key] = amap.get("content", "")
        elif tag.lower() == "link" and amap.get("rel", "").lower() == "canonical":
            self.canonical = amap.get("href", "")
        elif tag.lower() == "script" and amap.get("type", "").lower() == "application/ld+json":
            self._capture_script = True
            self._buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title" and self._capture_title:
            self.title = " ".join(self._buffer).strip()
            self._capture_title = False
        elif tag.lower() == "h1" and self._capture_h1:
            self.h1.append(" ".join(self._buffer).strip())
            self._capture_h1 = False
        elif tag.lower() == "a" and self._current_link is not None:
            self._current_link["anchor"] = " ".join(self._buffer).strip()
            self.links.append(self._current_link)
            self._current_link = None
            self._buffer = []
        elif tag.lower() == "script" and self._capture_script:
            raw = " ".join(self._buffer).strip()
            if raw:
                try:
                    self.schemas.append(json.loads(raw))
                except json.JSONDecodeError:
                    self.schemas.append({"_invalid_jsonld": raw[:200]})
            self._capture_script = False

    def handle_data(self, data: str) -> None:
        clean = " ".join(data.split())
        if clean:
            self.text.append(clean)
            if self._capture_title or self._capture_h1 or self._capture_script or self._current_link is not None:
                self._buffer.append(clean)


@dataclass
class Finding:
    code: str
    severity: str
    message: str
    repairable: bool = False


@dataclass
class PageAudit:
    path: str
    publication: str
    route: str
    source_hash: str
    title: str
    h1: list[str]
    word_count: int
    canonical: str
    meta_description: str
    html_lang: str
    external_links: list[dict[str, str]]
    internal_links: list[dict[str, str]]
    schema_count: int
    duplicate_fingerprint: str
    findings: list[Finding] = field(default_factory=list)
    repair_count: int = 0

    @property
    def status(self) -> str:
        if any(f.severity == "HARD_FAIL" for f in self.findings):
            return "FAIL"
        if any(f.severity == "STRONG_WARNING" for f in self.findings):
            return "PASS_WITH_STRONG_WARNING"
        if any(f.severity == "SOFT_WARNING" for f in self.findings):
            return "PASS_WITH_SOFT_WARNING"
        return "PASS"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status
        return data


def publication_for(path: Path) -> str:
    try:
        return path.relative_to(SITES_ROOT).parts[0]
    except Exception:
        return "unknown"


def route_for(path: Path) -> str:
    pub_root = SITES_ROOT / publication_for(path)
    rel = path.relative_to(pub_root).as_posix()
    return "/" if rel == "index.html" else "/" + rel


def text_fingerprint(text: str) -> str:
    normalized = re.sub(r"\b20\d\d-\d\d-\d\d\b", " ", text.lower())
    normalized = re.sub(r"[^a-z0-9 ]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return sha256_bytes(normalized.encode("utf-8"))


def audit_page(path: Path) -> PageAudit:
    raw = path.read_bytes()
    html = raw.decode("utf-8", errors="replace")
    parser = PageParser()
    parse_error = None
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:  # HTMLParser is permissive; this catches true engine failures.
        parse_error = str(exc)

    text = " ".join(parser.text)
    words = re.findall(r"\b[\w'-]+\b", text)
    external = [x for x in parser.links if x["href"].startswith(("http://", "https://"))]
    internal = [x for x in parser.links if x["href"] and not x["href"].startswith(("http://", "https://", "mailto:", "tel:", "#"))]
    findings: list[Finding] = []

    if parse_error:
        findings.append(Finding("HTML_ENGINE_ERROR", "HARD_FAIL", parse_error))
    if not parser.title:
        findings.append(Finding("MISSING_TITLE", "HARD_FAIL", "Page has no title element."))
    if len(parser.h1) != 1:
        findings.append(Finding("H1_COUNT", "HARD_FAIL", f"Expected exactly one H1; found {len(parser.h1)}."))
    if not parser.meta.get("description"):
        findings.append(Finding("MISSING_META_DESCRIPTION", "STRONG_WARNING", "Meta description is missing.", True))
    if not parser.html_lang:
        findings.append(Finding("MISSING_HTML_LANG", "SOFT_WARNING", "HTML lang attribute is missing.", True))
    if len(words) < WORD_TARGET_MIN:
        findings.append(Finding("LOW_WORD_COUNT", "SOFT_WARNING", f"Word count {len(words)} is below the editorial target {WORD_TARGET_MIN}."))
    if any(isinstance(s, dict) and "_invalid_jsonld" in s for s in parser.schemas):
        findings.append(Finding("INVALID_JSONLD", "HARD_FAIL", "A JSON-LD block is malformed."))

    seen_links: set[tuple[str, str]] = set()
    duplicate_count = 0
    for link in external:
        key = (link["href"].rstrip("/"), link["anchor"].strip().lower())
        if key in seen_links:
            duplicate_count += 1
        seen_links.add(key)
    if duplicate_count:
        findings.append(Finding("DUPLICATE_EXTERNAL_LINK", "STRONG_WARNING", f"Found {duplicate_count} exact duplicate outbound link(s).", True))

    return PageAudit(
        path=path.relative_to(ROOT).as_posix(),
        publication=publication_for(path),
        route=route_for(path),
        source_hash=sha256_bytes(raw),
        title=parser.title,
        h1=parser.h1,
        word_count=len(words),
        canonical=parser.canonical,
        meta_description=parser.meta.get("description", ""),
        html_lang=parser.html_lang,
        external_links=external,
        internal_links=internal,
        schema_count=len(parser.schemas),
        duplicate_fingerprint=text_fingerprint(text),
        findings=findings,
    )


def iter_pages(paths: Iterable[Path] | None = None) -> list[Path]:
    if paths is not None:
        return sorted({p.resolve() for p in paths if p.suffix.lower() == ".html" and p.exists()})
    return sorted(SITES_ROOT.rglob("*.html"))
