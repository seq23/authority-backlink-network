#!/usr/bin/env python3
"""Every page describes its editorial company exactly as data/entities/<domain>.json does.

Authority audit, 30 Oct 2026: all three publications published
`sameAs: ["https://<own host>/contributors", "https://<own host>/about"]` -- the
site vouching for itself, which gives a search engine or an answer engine
nothing outside the site to reconcile the entity against. The entity is now
defined once, in data/entities/<domain>.json, and this check holds the published
tree to it.

Blocks (HARD_FAIL):

  entity file
    * missing for a publication, or its name is not the byline entity
      (scripts/byline.py entity_for), or its @id / url / logo / editorial_policy
      sit on another host;
    * a sameAs or profiles_pending URL on the site's own host (self-reference)
      or on another publication of this network (the network vouching for
      itself is still self-reference);
    * a URL that is in both sameAs and profiles_pending;
    * a parentOrganization (owner decision, 11 Oct 2026: no parent is named).

  every published page, every Organization node naming this publication or its
  editorial company
    * sameAs differs from the entity file's sameAs (absent == empty);
    * any sameAs URL on the site's own host;
  and every node naming the editorial company itself
    * logo differs from the entity file's logo;
    * a description, where present, differs from the entity file's.

  llms.txt names the entity, carries its description and the editorial policy
  URL, and /editorial-policy is served (a _redirects rule or a page).

  the weekly watch itself: .github/workflows/entity-backlink-watch.yml exists at
  exactly that name (the owner's Search Readiness checklist, item k6, looks the
  workflow up by file name: the file used to be entity-authority-watch.yml and
  k6 read as "no entity-backlink-watch workflow" while the watch was running
  every week), carries a schedule and workflow_dispatch, and runs
  scripts/entity_backlink_watch.py. Its cron fires on Sunday, so a green run
  always exists before the Monday 06:00 Central audit reads it.

Rule 0: zero publications, or zero Organization nodes checked, is a FAIL.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from lib import head_seo as hs  # noqa: E402
from byline import entity_for  # noqa: E402


def host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def check_entity(pub: dict, domains: set[str], failures: list[str]) -> dict | None:
    domain = pub["working_domain"]
    path = ROOT / hs.ENTITY_DIR / f"{domain}.json"
    rel = path.relative_to(ROOT).as_posix()
    if not path.exists():
        failures.append(f"{rel}: missing")
        return None
    entity = json.loads(path.read_text(encoding="utf-8"))
    if entity.get("name") != entity_for(pub["title"]):
        failures.append(f"{rel}: name {entity.get('name')!r} is not the byline entity {entity_for(pub['title'])!r}")
    for key in ("@id", "url", "logo", "editorial_policy"):
        if host(str(entity.get(key, ""))) != domain:
            failures.append(f"{rel}: {key} {entity.get(key)!r} is not on {domain}")
    if not str(entity.get("description", "")).strip():
        failures.append(f"{rel}: no description")
    if entity.get("parentOrganization"):
        failures.append(f"{rel}: parentOrganization is set; the publications name no parent (owner, 11 Oct 2026)")
    same_as, pending = entity.get("sameAs"), entity.get("profiles_pending")
    if not isinstance(same_as, list) or not isinstance(pending, list):
        failures.append(f"{rel}: sameAs and profiles_pending must both be lists")
        return None
    for field, urls in (("sameAs", same_as), ("profiles_pending", pending)):
        for url in urls:
            entry = url if isinstance(url, str) else url.get("url", "")
            if not entry.startswith("https://"):
                failures.append(f"{rel}: {field} entry {url!r} is not an https URL")
            elif host(entry) in domains:
                failures.append(f"{rel}: {field} {entry} is on a network host -- self-reference, not an identity")
    # Search Readiness item k3: at least one independently hosted profile that
    # really resolves. Until 31 Oct 2026 all three entity files shipped
    # `sameAs: []`, so c1 read "Organization lacks sameAs" and k3 read "no
    # external profile" on every page of every publication for as long as the
    # audit had run. An empty sameAs was allowed here because the alternative
    # was inventing a profile; the real answer was the one the passing grid
    # sites already use -- this network's own public source repository, which
    # resolves and names each publication. Empty is now a release failure, so
    # the identity cannot quietly go back to vouching for nothing.
    if not same_as:
        failures.append(
            f"{rel}: sameAs is empty -- the editorial company has no independent profile to be "
            f"reconciled against (Search Readiness k3). Add a real, resolving, externally hosted "
            f"profile that names {domain}; a profile not yet claimed goes in profiles_pending.")
    pending_urls = {p if isinstance(p, str) else p.get("url") for p in pending}
    for url in set(same_as) & pending_urls:
        failures.append(f"{rel}: {url} is in both sameAs and profiles_pending")
    return entity


WATCH_WORKFLOW = ".github/workflows/entity-backlink-watch.yml"
WATCH_SCRIPT = "scripts/entity_backlink_watch.py"


def check_watch_workflow(failures: list[str]) -> int:
    """k6 finds the weekly watch by file name, so the name is part of the contract."""
    path = ROOT / WATCH_WORKFLOW
    if not path.exists():
        others = sorted(p.name for p in (ROOT / ".github/workflows").glob("*entity*"))
        failures.append(f"{WATCH_WORKFLOW}: missing"
                        + (f" (found {', '.join(others)}: the checklist reads this one by name)" if others else ""))
        return 0
    text = path.read_text(encoding="utf-8")
    crons = re.findall(r"^\s*-\s*cron:\s*['\"]([^'\"]+)['\"]", text, re.M)
    if "schedule:" not in text or not crons:
        failures.append(f"{WATCH_WORKFLOW}: no schedule")
    if "workflow_dispatch" not in text:
        failures.append(f"{WATCH_WORKFLOW}: no workflow_dispatch")
    if WATCH_SCRIPT not in text:
        failures.append(f"{WATCH_WORKFLOW}: does not run {WATCH_SCRIPT}")
    for cron in crons:
        parts = cron.split()
        if len(parts) != 5 or parts[4] not in {"0", "7", "SUN", "sun"}:
            failures.append(f"{WATCH_WORKFLOW}: cron {cron!r} does not fire on Sunday; the Monday "
                            "06:00 Central audit needs a green run already recorded")
    return len(crons)


def main() -> int:
    failures: list[str] = []
    crons = check_watch_workflow(failures)
    pubs = json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))
    domains = {p["working_domain"] for p in pubs}
    entities = {}
    for pub in pubs:
        entity = check_entity(pub, domains, failures)
        if entity:
            entities[pub["working_domain"]] = entity

    checked_nodes = 0
    pages = 0
    for pub, folder, path, rel, text in hs.published_pages(ROOT):
        domain = pub["working_domain"]
        entity = entities.get(domain)
        if entity is None:
            continue
        pages += 1
        company = entity["name"].casefold()
        ours = {company, pub["title"].casefold()}
        want = list(entity["sameAs"])
        for node in hs.jsonld_nodes(text):
            if "Organization" not in hs.node_types(node):
                continue
            name = str(node.get("name", "")).casefold()
            if name not in ours:
                continue
            checked_nodes += 1
            got = node.get("sameAs") or []
            got = [got] if isinstance(got, str) else list(got)
            if got != want:
                failures.append(f"{rel}: Organization {node.get('name')!r} sameAs {got} != entity file {want}")
            for url in got:
                if host(url) == domain:
                    failures.append(f"{rel}: Organization {node.get('name')!r} sameAs {url} is this site's own host")
            if name == company:
                if node.get("logo") and node["logo"] != entity["logo"]:
                    failures.append(f"{rel}: editorial company logo {node['logo']!r} != entity file {entity['logo']!r}")
                if node.get("description") and node["description"] != entity["description"]:
                    failures.append(f"{rel}: editorial company description differs from the entity file")

    for pub in pubs:
        domain = pub["working_domain"]
        entity = entities.get(domain)
        if not entity:
            continue
        folder = ROOT / pub["folder"]
        llms = folder / "llms.txt"
        text = llms.read_text(encoding="utf-8") if llms.exists() else ""
        for needle, what in ((entity["name"], "the entity name"), (entity["description"], "the entity description"),
                             (entity["editorial_policy"], "the editorial policy URL"), ("## Beats", "the beats")):
            if needle not in text:
                failures.append(f"{pub['folder']}/llms.txt: lacks {what}")
        redirects = folder / "_redirects"
        served = (folder / "editorial-policy.html").exists() or (
            redirects.exists() and re.search(r"^/editorial-policy\s+\S+\s+30[1278]\b",
                                             redirects.read_text(encoding="utf-8"), re.M))
        if not served:
            failures.append(f"{pub['folder']}: /editorial-policy is not served (no page, no _redirects rule)")

    if not entities:
        failures.append("Rule 0: no publication entity checked")
    if checked_nodes == 0:
        failures.append("Rule 0: zero Organization nodes checked across the published tree")
    status = "FAIL" if failures else "PASS"
    print(json.dumps({"validator": "entity_graph", "status": status, "publications": len(entities),
                      "pages": pages, "organization_nodes": checked_nodes,
                      "watch_workflow": WATCH_WORKFLOW, "watch_crons": crons,
                      "failures": failures[:50], "failure_count": len(failures)}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
