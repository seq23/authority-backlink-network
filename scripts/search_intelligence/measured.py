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


# Owner exceptions to the publishing freeze (publishing_freeze.json
# `owner_exceptions`). The freeze itself is not loosened: an exception is a
# named, dated record of the owner's own words that lets at most `max_articles`
# pages linking ONE brand publish without a measured query, on ONE host, on or
# after the day she decided it. An entry may also name `slugs`: then only pages
# whose filename slug (after the YYYY-MM-DD- date) is listed may claim it, and
# the list must be exactly max_articles long. A page claims an exception by its released
# record in held_pages.json carrying `owner_exception: <id>`; anything else
# dated on/after `since` still needs a measured query with impressions.
EXCEPTION_FIELDS = ("id", "brand_id", "target_domain", "host", "max_articles", "decided", "owner_words")


def exception_problems(exc: dict) -> list[str]:
    """Why an owner-exception entry is not a usable record, or []."""
    out = [f"owner_exception {exc.get('id', '?')}: missing {k}" for k in EXCEPTION_FIELDS if not exc.get(k)]
    if not out:
        n = exc["max_articles"]
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            out.append(f"owner_exception {exc['id']}: max_articles must be a positive integer")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(exc["decided"])):
            out.append(f"owner_exception {exc['id']}: decided must be an ISO date")
        if "slugs" in exc:
            slugs = exc["slugs"]
            if (not isinstance(slugs, list) or not slugs or len(set(slugs)) != len(slugs)
                    or not all(isinstance(x, str) and x for x in slugs)):
                out.append(f"owner_exception {exc['id']}: slugs must be a non-empty list of distinct page slugs")
            elif isinstance(n, int) and len(slugs) != n:
                out.append(f"owner_exception {exc['id']}: names {len(slugs)} slug(s) but max_articles is {n}")
    return out


def freeze_violations(fz: dict, released: list[dict], pages: list[tuple[str, str, str]]) -> list[str]:
    """Every way the dated daily pages break the publishing freeze.

    pages: (rel_path, host, page_html) for each daily page. A page dated
    on/after `since` passes only with a released record that carries a measured
    query with impressions, or one that names a valid owner exception whose
    brand, host and date it matches, whose target domain it links, and whose
    article cap it stays inside.
    """
    if fz.get("enabled") is not True:
        return []
    fail: list[str] = []
    since = fz.get("since", "")
    exceptions = {}
    for exc in fz.get("owner_exceptions", []) or []:
        problems = exception_problems(exc)
        fail += problems
        if not problems:
            exceptions[exc["id"]] = exc
    by_path = {r.get("path"): r for r in released}
    used: dict[str, list[str]] = {}
    for rel, host, page in pages:
        day = Path(rel).name[:10]
        if day < since:
            continue
        r = by_path.get(rel)
        if r and r.get("measured_query") and (r.get("impressions") or 0) > 0:
            continue
        exc_id = (r or {}).get("owner_exception")
        if not exc_id:
            fail.append(f"freeze: {rel} was published on/after {since} without a measured query in held_pages.json")
            continue
        exc = exceptions.get(exc_id)
        if exc is None:
            fail.append(f"freeze: {rel} claims owner exception {exc_id!r}, which publishing_freeze.json does not hold")
            continue
        domain = re.escape(exc["target_domain"])
        why = []
        if r.get("target_brand_id") != exc["brand_id"]:
            why.append(f"brand {r.get('target_brand_id')!r} is not {exc['brand_id']!r}")
        if host != exc["host"]:
            why.append(f"host {host!r} is not {exc['host']!r}")
        if day < exc["decided"]:
            why.append(f"dated {day}, before the owner decided on {exc['decided']}")
        if not re.search(rf'href="https?://(?:www\.)?{domain}[/"]', page):
            why.append(f"does not link {exc['target_domain']}")
        if "slugs" in exc and Path(rel).stem[11:] not in exc["slugs"]:
            why.append(f"slug {Path(rel).stem[11:]!r} is not one of the {len(exc['slugs'])} page(s) the owner named")
        if why:
            fail.append(f"freeze: {rel} is outside owner exception {exc_id}: " + "; ".join(why))
            continue
        used.setdefault(exc_id, []).append(rel)
    for exc_id, rels in used.items():
        cap = exceptions[exc_id]["max_articles"]
        if len(rels) > cap:
            fail.append(f"freeze: owner exception {exc_id} allows {cap} article(s); {len(rels)} claim it: {sorted(rels)}")
    return fail
