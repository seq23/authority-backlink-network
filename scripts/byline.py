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
Exactly two factual claims are published about these entities, and both were
supplied by the owner:

  1. Each publication has its own editorial company, named after it.
  2. That company is a subsidiary of Spry Labs.

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
def _publisher_entity(editorial_path: str = DEFAULT_EDITORIAL_PATH) -> tuple:
    """(entity_suffix, parent_company) from data/editorial.json.

    Returns a tuple rather than the dict so it stays hashable under lru_cache.
    """
    with open(editorial_path, encoding="utf-8") as fh:
        editorial = json.load(fh)
    entity = editorial.get("publisher_entity")
    if not entity:
        raise SystemExit(
            f"{editorial_path}: no publisher_entity block. The byline is derived "
            "from it; refusing to fall back to a hardcoded name."
        )
    suffix = (entity.get("entity_suffix") or "").strip()
    parent = (entity.get("parent_company") or "").strip()
    if not suffix:
        raise SystemExit(f"{editorial_path}: publisher_entity.entity_suffix is empty.")
    return suffix, parent


def _resolve(editorial_path: str) -> tuple:
    # Callers run from several working directories. Accept the path as given,
    # then fall back to the repo root next to this file.
    if os.path.exists(editorial_path):
        return _publisher_entity(editorial_path)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return _publisher_entity(os.path.join(root, editorial_path))


def entity_suffix(editorial_path: str = DEFAULT_EDITORIAL_PATH) -> str:
    return _resolve(editorial_path)[0]


def parent_company(editorial_path: str = DEFAULT_EDITORIAL_PATH) -> str:
    """The company these editorial companies are subsidiaries of. May be ''."""
    return _resolve(editorial_path)[1]


def entity_for(pub_title: str, editorial_path: str = DEFAULT_EDITORIAL_PATH) -> str:
    """The editorial company that publishes `pub_title`.

    This is the byline. It is also the JSON-LD author name and the name on the
    masthead -- one expression, so the three cannot disagree.
    """
    return f"{pub_title.strip()} {entity_suffix(editorial_path)}"


def subsidiary_clause(editorial_path: str = DEFAULT_EDITORIAL_PATH) -> str:
    """', a subsidiary of Spry Labs' -- or '' if no parent is recorded.

    Returned with the leading comma so a caller can drop it into a sentence and
    still read correctly when no parent company is on file.
    """
    parent = parent_company(editorial_path)
    return f", a subsidiary of {parent}" if parent else ""


if __name__ == "__main__":  # pragma: no cover - operator convenience
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    pubs = json.loads((root / "data/publications.json").read_text(encoding="utf-8"))
    for pub in pubs:
        print(f"{pub['id']:<14} {entity_for(pub['title'])}{subsidiary_clause()}")
