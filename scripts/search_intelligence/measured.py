"""Shared reads for the measured search loop (data/search_intelligence/).

One place for: the site list, the URL -> file mapping, query tokenisation, and
the publishing-freeze rule "is this brief's subject measured?". Read by
build_search_plan.py, apply_strengthening.py, authority_v4_autopilot.py (the
freeze) and scripts/validators/validate_search_intelligence.py, so the rule the
generator applies is the rule the validator recomputes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
SI = ROOT / "data" / "search_intelligence"
FREEZE_PATH = SI / "publishing_freeze.json"
HELD_PATH = SI / "held_pages.json"
STOP = set("""a an and are as at be by can do does for from how i in is it of on or the to what when where which who
why will with you your my me we our us this that these those vs versus about into than then there their its it's
near best top get""".split())


def read_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def sites() -> list[dict]:
    return read_json(SI / "sites.json")["sites"]


def site_for_folder(folder_name: str) -> dict | None:
    """folder_name is the last path part (founder-operator) or the full sites/... path."""
    name = folder_name.rstrip("/").split("/")[-1]
    return next((s for s in sites() if s["folder"].split("/")[-1] == name), None)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower())).strip()


def tokens(text: str) -> list[str]:
    out = []
    for t in norm(text).split():
        if len(t) < 3 or t in STOP:
            continue
        out.append(t[:-1] if len(t) > 4 and t.endswith("s") and not t.endswith("ss") else t)
    return out


def route_of(url: str) -> str:
    return urlsplit(url).path or "/"


def file_for_route(site: dict, route: str) -> Path | None:
    """The published file a URL path is served from on Cloudflare Pages, or None."""
    folder = ROOT / site["folder"]
    r = route.split("?")[0].split("#")[0]
    if r in ("", "/"):
        cands = [folder / "index.html"]
    else:
        rel = r.strip("/")
        cands = [folder / rel] if rel.endswith(".html") else [folder / f"{rel}.html", folder / rel / "index.html"]
    return next((c for c in cands if c.is_file()), None)


def redirect_rules(site: dict) -> dict[str, str]:
    p = ROOT / site["folder"] / "_redirects"
    rules = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 2 and not line.lstrip().startswith("#"):
                rules[parts[0].rstrip("/") or "/"] = parts[1]
    return rules


def freeze() -> dict:
    return read_json(FREEZE_PATH, {"enabled": False})


def targets(host: str) -> list[dict]:
    return (read_json(SI / host / "target_query_set.json", {}) or {}).get("targets", [])


def measured_target(host: str, subject: str) -> dict | None:
    """The measured target whose query this subject answers, or None.

    A target matches when it has at least two content tokens and every one of
    them appears in the subject (title + cluster). The best match is the one
    with the most impressions. A subject with no such target is unmeasured and
    the freeze holds it.
    """
    have = set(tokens(subject))
    best = None
    for t in targets(host):
        need = set(tokens(t["query"]))
        if len(need) >= 2 and need <= have and (best is None or t["impressions"] > best["impressions"]):
            best = t
    return best
