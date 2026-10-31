#!/usr/bin/env python3
"""entity_backlink_watch self-heals the way it says it does, on a temp copy with a fake network.

  dead sameAs                         -> removed with --write, kept without it
  pending profile resolving + link-back -> promoted into sameAs
  pending profile resolving, no link-back -> stays pending
  server-rendered profile, no link-back -> NAMED STOP naming the field to edit
  JS-rendered profile                 -> `unverifiable`, never `ok`
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import entity_backlink_watch as w  # noqa: E402

SITE = "example-library.test"
PAGES = {
    "https://dead.example/profile": (404, ""),
    "https://www.facebook.com/nolink": (200, "<html>no site here</html>"),
    "https://www.instagram.com/lib": (200, "<html></html>"),
    "https://github.com/lib": (200, f"<a href='https://{SITE}/'>site</a>"),
    "https://www.pinterest.com/unlinked": (200, "<html></html>"),
}


def fake(url):
    return PAGES.get(url, (0, ""))


def main() -> int:
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        ent = Path(tmp) / "entities"
        ent.mkdir()
        entity = {"sameAs": ["https://dead.example/profile", "https://www.facebook.com/nolink", "https://www.instagram.com/lib"],
                  "profiles_pending": ["https://github.com/lib", "https://www.pinterest.com/unlinked"]}
        (ent / f"{SITE}.json").write_text(json.dumps(entity))
        w.ENTITIES, w.REPORT = ent, Path(tmp) / "report.json"
        dry = w.watch(False, fake)
        if json.loads((ent / f"{SITE}.json").read_text()) != entity:
            failures.append("dry run modified the entity file")
        states = {r["url"]: r["state"] for r in dry["entities"][0]["sameAs"]}
        if states != {"https://dead.example/profile": "dead", "https://www.facebook.com/nolink": "missing_link_back",
                      "https://www.instagram.com/lib": "unverifiable"}:
            failures.append(f"states wrong: {states}")
        if not any("facebook.com/nolink" in s and "Page > About > Website" in s for s in dry["named_stops"]):
            failures.append("missing link-back did not produce a named stop with the field to edit")
        w.watch(True, fake)
        healed = json.loads((ent / f"{SITE}.json").read_text())
        if healed["sameAs"] != ["https://www.facebook.com/nolink", "https://www.instagram.com/lib", "https://github.com/lib"]:
            failures.append(f"self-heal sameAs wrong: {healed['sameAs']}")
        if healed["profiles_pending"] != ["https://www.pinterest.com/unlinked"]:
            failures.append(f"self-heal pending wrong: {healed['profiles_pending']}")
    print(json.dumps({"test": "entity_backlink_watch", "status": "FAIL" if failures else "PASS", "cases": 5,
                      "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
