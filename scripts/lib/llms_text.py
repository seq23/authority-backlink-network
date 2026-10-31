"""The one renderer of a publication's /llms.txt.

Two writers emit llms.txt -- scripts/deterministic_build.py and the autopilot's
update_sitemap() in scripts/authority_v4_autopilot.py -- and until 31 Oct 2026
each held its own copy of a 180-byte f-string that said only "This site contains
editorial resource pages". An answer engine reading it learned nothing about who
publishes the site, what it covers, or what its standards are (authority audit,
30 Oct 2026). Both now call render() here, so the two cannot drift.

Everything in the file is derived, never typed:
  * the entity name and description from data/entities/<domain>.json (the same
    record the JSON-LD is held to by validate_entity_graph);
  * the beats from the publication's own topic hubs (sites/<folder>/topics/*.html,
    each hub's <h1>), so a new hub is listed the day it is built;
  * the editorial policy URL from the entity record.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")


def beats(folder: Path) -> list[tuple[str, str]]:
    """(hub path, hub heading) for every topic hub of the publication."""
    out = []
    for hub in sorted((folder / "topics").glob("*.html")):
        m = H1_RE.search(hub.read_text(encoding="utf-8"))
        if m:
            out.append((f"/topics/{hub.stem}", html.unescape(TAG_RE.sub("", m.group(1))).strip()))
    return out


def render(pub: dict, domain: str, newest: str, root: Path | None = None) -> str:
    root = root or ROOT
    entity = json.loads((root / "data/entities" / f"{domain}.json").read_text(encoding="utf-8"))
    home = f"https://{domain}"
    lines = [
        f"# {pub['title']}",
        "",
        f"> {pub['definition'].strip()}",
        "",
        f"Publisher: {entity['name']}. {entity['description']}",
        f"Editorial policy: {entity['editorial_policy']}",
        f"Masthead: {home}/masthead",
        f"Corrections: {home}/corrections",
        f"Updated: {newest}",
        "",
        "## Beats",
        "",
    ]
    hub_list = beats(root / pub["folder"])
    lines += [f"- [{name}]({home}{path})" for path, name in hub_list] or ["- (no topic hubs yet)"]
    lines += ["", f"Sitemap: {home}/sitemap.xml", ""]
    return "\n".join(lines)
