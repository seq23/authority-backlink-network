#!/usr/bin/env python3
"""Single source of truth for the editorial byline on every publication.

Why this file exists
--------------------
The byline used to be one person's name, repeated across three publications that
present themselves as independent of one another. Three independent publications
do not share a sole author, so the byline was the weakest ownership signal in the
network. Worse, it disagreed with itself: 552 pages carried
`"author": {"@type": "Organization"}` in JSON-LD while the visible attribution
named a person.

Each publication now has its own editorial company, named after the publication.
The visible attribution and the JSON-LD author are BOTH that company, so the two
can no longer disagree.

The name is derived, never hand-written
---------------------------------------
    entity_for(pub_title) == f"{pub_title} {entity_suffix}"

with `entity_suffix` read from data/editorial.json. Four separate emitters need
this string -- the chrome installer's footer, the masthead builder, the daily
autopilot's JSON-LD and the cluster-article generator's JSON-LD -- and four
hand-written copies would drift. Deriving it means a page's visible byline and
its JSON-LD author are the same expression evaluated twice.

What may and may not be asserted here
-------------------------------------
Exactly one factual claim is published about these entities, supplied by the
owner: each publication has its own editorial company, named after it.

No parent company is named anywhere -- not in the byline, the masthead, the
footer or JSON-LD (no parentOrganization). The owner withdrew the parent-company
claim on 11 Oct 2026; validate_no_parent_company.py fails the build if one
reappears in published output.

Nothing else about them is known, so nothing else is stated. No staff name, job
title, credential, headshot, biography, registration number, incorporation date,
address, phone number or award appears here or anywhere the generators reach. An
organisational byline is not a licence to invent an organisation's paperwork; if
a caller wants a detail this module does not expose, the answer is that the fact
does not exist yet, not that it should be composed.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

DEFAULT_EDITORIAL_PATH = "data/editorial.json"


@lru_cache(maxsize=8)
def _publisher_entity(editorial_path: str = DEFAULT_EDITORIAL_PATH) -> str:
    """entity_suffix from data/editorial.json."""
    with open(editorial_path, encoding="utf-8") as fh:
        editorial = json.load(fh)
    entity = editorial.get("publisher_entity")
    if not entity:
        raise SystemExit(
            f"{editorial_path}: no publisher_entity block. The byline is derived "
            "from it; refusing to fall back to a hardcoded name."
        )
    if "parent_company" in entity:
        raise SystemExit(
            f"{editorial_path}: publisher_entity.parent_company is withdrawn (owner, 11 Oct "
            "2026). Each publication's editorial company is published with no parent."
        )
    suffix = (entity.get("entity_suffix") or "").strip()
    if not suffix:
        raise SystemExit(f"{editorial_path}: publisher_entity.entity_suffix is empty.")
    return suffix


def _resolve(editorial_path: str) -> str:
    # Callers run from several working directories. Accept the path as given,
    # then fall back to the repo root next to this file.
    if os.path.exists(editorial_path):
        return _publisher_entity(editorial_path)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return _publisher_entity(os.path.join(root, editorial_path))


def entity_suffix(editorial_path: str = DEFAULT_EDITORIAL_PATH) -> str:
    return _resolve(editorial_path)


def entity_for(pub_title: str, editorial_path: str = DEFAULT_EDITORIAL_PATH) -> str:
    """The editorial company that publishes `pub_title`.

    This is the byline. It is also the JSON-LD author name and the name on the
    masthead -- one expression, so the three cannot disagree.
    """
    return f"{pub_title.strip()} {entity_suffix(editorial_path)}"



if __name__ == "__main__":  # pragma: no cover - operator convenience
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    pubs = json.loads((root / "data/publications.json").read_text(encoding="utf-8"))
    for pub in pubs:
        print(f"{pub['id']:<14} {entity_for(pub['title'])}")
