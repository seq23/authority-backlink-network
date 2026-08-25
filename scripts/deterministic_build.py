#!/usr/bin/env python3
"""Clean deterministic rebuild parity for governed derived site artifacts."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import re
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
PUBLICATIONS = json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))
BUILD_DATE = os.getenv("BUILD_DATE", "2026-01-01")


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    tmp.replace(path)


def build_into(out: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for pub in sorted(PUBLICATIONS, key=lambda x: x["id"]):
        source = ROOT / pub["folder"]
        target = out / pub["folder"]
        target.mkdir(parents=True, exist_ok=True)
        # data/publications.json stores the host under "working_domain". Reading
        # only "domain"/"default_domain" yielded None for every publication, and
        # the f-strings below turned that into a literal "https://None/..." for
        # every URL - so all three sitemaps and llms.txt files shipped pointing at
        # an unresolvable host. Google reported 355 errors on
        # professionalresourcelibrary.com; the other two had not been re-read yet.
        domain = pub.get("working_domain") or pub.get("domain") or pub.get("default_domain")
        if not domain:
            # Never emit a sitemap addressed to a host we could not resolve. A
            # loud build failure is recoverable; a silently broken sitemap is
            # invisible until someone reads Search Console months later.
            raise SystemExit(
                f'publication {pub.get("id")!r} has no domain '
                '(expected "working_domain" in data/publications.json)')
        html_files = sorted(source.rglob("*.html"), key=lambda p: p.relative_to(source).as_posix())
        urls = []
        for page in html_files:
            rel = page.relative_to(source).as_posix()
            text = page.read_text(encoding="utf-8", errors="ignore")
            if rel.startswith("agency/") or re.search(r'<meta[^>]+name=["\']robots["\'][^>]+content=["\'][^"\']*noindex', text, re.I):
                continue
            loc = f"https://{domain}/" if rel == "index.html" else f"https://{domain}/{rel}"
            urls.append(f"<url><loc>{escape(loc)}</loc><lastmod>{BUILD_DATE}</lastmod></url>")
        sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n"
        llms = f"# {domain}\n\nThis site contains editorial resource pages for humans and answer engines. Updated {BUILD_DATE}.\n\nSitemap: https://{domain}/sitemap.xml\n"
        for name, value in (("sitemap.xml", sitemap), ("llms.txt", llms)):
            path = target / name
            atomic_text(path, value)
            hashes[f'{pub["folder"]}/{name}'] = hashlib.sha256(value.encode()).hexdigest()
    return hashes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="Write deterministic derived artifacts into the repository.")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        first = build_into(Path(a))
        second = build_into(Path(b))
        differences = [k for k in sorted(set(first) | set(second)) if first.get(k) != second.get(k)]
        if differences:
            print(json.dumps({"status": "FAIL", "differences": differences}, indent=2))
            raise SystemExit(1)
        if args.write:
            built = Path(a)
            for rel in first:
                src = built / rel
                dst = ROOT / rel
                atomic_text(dst, src.read_text(encoding="utf-8"))
        print(json.dumps({"status": "PASS", "build_date": BUILD_DATE, "artifacts": len(first), "differences": []}, indent=2))


if __name__ == "__main__":
    main()
