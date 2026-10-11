#!/usr/bin/env python3
"""No parent company is named anywhere the publications publish.

Owner decision, 11 Oct 2026: the three publications are each published by their
own editorial company and name no parent. This blocks on, in published output
(every file under sites/):

  * the string "Spry Labs" (any case) -- byline, footer, masthead, llms*.txt,
    sitemaps, JSON-LD, anywhere;
  * a "parentOrganization" key in any JSON-LD;
  * an editorial-company sentence calling itself "a subsidiary" (the withdrawn
    byline wording -- ordinary uses, such as a credit bureau described as a
    subsidiary on the consumer-reporting directory, are not ownership claims).

and at the source, so the next build cannot reintroduce it:

  * data/editorial.json declaring publisher_entity.parent_company;
  * "Spry Labs" in any generator under scripts/ or in data/*.json -- except
    data/publications.json `retired_disclosures`, the list of withdrawn
    sentences install_editorial_chrome.py uses to repair old pages, and
    data/back_catalogue_decision.json, a dated record of past decisions.

Rule 0: scanning zero published files is a FAIL.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAME = re.compile(r"spry\s+labs", re.I)
PARENT = re.compile(r'"parentOrganization"\s*:', re.I)
SUBSIDIARY = re.compile(r"editorial company[^.<]{0,80}\bsubsidiary\b", re.I)
TEXT_EXT = {".html", ".txt", ".xml", ".json", ".webmanifest", ".md"}
SELF = Path(__file__).resolve()


def main() -> int:
    failures: list[str] = []
    scanned = 0
    for path in sorted((ROOT / "sites").rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXT:
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(ROOT).as_posix()
        for rx, what in ((NAME, "names Spry Labs"), (PARENT, "has a JSON-LD parentOrganization"),
                         (SUBSIDIARY, "calls its editorial company a subsidiary")):
            n = len(rx.findall(text))
            if n:
                failures.append(f"output {rel}: {what} ({n}x)")

    editorial = json.loads((ROOT / "data/editorial.json").read_text(encoding="utf-8"))
    if "parent_company" in editorial.get("publisher_entity", {}):
        failures.append("source data/editorial.json: publisher_entity.parent_company is declared")

    pubs = json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))
    for pub in pubs:
        live = {k: v for k, v in pub.items() if k != "retired_disclosures"}
        if NAME.search(json.dumps(live)):
            failures.append(f"source data/publications.json: publication {pub['id']} names Spry Labs "
                            "outside retired_disclosures")
    for path in sorted((ROOT / "scripts").rglob("*")) + sorted((ROOT / "data").glob("*.json")):
        if not path.is_file() or path.resolve() == SELF or path.suffix not in {".py", ".js", ".mjs", ".json"}:
            continue
        if path.name in {"publications.json", "back_catalogue_decision.json"} or "__pycache__" in path.parts:
            continue
        if NAME.search(path.read_text(encoding="utf-8", errors="ignore")):
            failures.append(f"source {path.relative_to(ROOT)}: names Spry Labs")

    if not scanned:
        failures.append("rule0: scanned zero published files under sites/")
    print(json.dumps({"validator": "no_parent_company", "status": "FAIL" if failures else "PASS",
                      "hard_failures": len(failures), "published_files_scanned": scanned,
                      "failures": failures[:40]}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
