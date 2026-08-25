#!/usr/bin/env python3
"""Single source of truth for which outbound links are affiliated.

Affiliation is resolved from data/brands.json, the same file link_audit.py reads.
Deliberately not a second list: two lists drift, and a drifted list here means a
followed link from a self-owned publication to a client money site.

Followed links between self-owned properties are what Semrush flagged as a PBN
anchor pattern across 13 domains. Manual action notices for that go to the
*client's* Search Console, not ours, which is why this is enforced rather than
advised.

rel="sponsored nofollow" costs nothing in AI search: LLMs do not compute PageRank,
and citation runs on mention and corroboration, which a nofollowed link delivers
in full.
"""
from __future__ import annotations
import json, os
from functools import lru_cache
from urllib.parse import urlparse

REL_VALUE = "sponsored nofollow"


@lru_cache(maxsize=1)
def affiliated_domains(brands_path: str = "data/brands.json") -> frozenset[str]:
    if not os.path.exists(brands_path):
        return frozenset()
    with open(brands_path, encoding="utf-8") as fh:
        brands = json.load(fh)
    out = set()
    for b in brands if isinstance(brands, list) else brands.get("brands", []):
        b = b or {}
        # Mirror link_audit.brand_domains exactly: a brand may declare a plural
        # 'domains' list (the wedding brand owns four). Reading only 'domain' here
        # silently under-scoped affiliation and left 42 followed links behind.
        for d in (b.get("domains") or [b.get("domain", "")]):
            if d:
                out.add(str(d).strip().lower().lstrip(".").removeprefix("www."))
    return frozenset(out)


def host_of(url: str) -> str:
    try:
        h = urlparse(url if "//" in str(url) else "https://" + str(url)).hostname or ""
    except Exception:
        return ""
    return h.lower().removeprefix("www.")


def is_affiliated(url: str) -> bool:
    """True only for absolute http(s) links to a domain listed in brands.json.

    Relative links, anchors, mailto, stylesheets and canonicals never match,
    because none of them resolve to an affiliated host.
    """
    u = str(url or "").strip()
    if not u or u.startswith(("#", "/", "mailto:", "tel:", "javascript:")):
        return False
    if not u.lower().startswith(("http://", "https://")):
        return False
    return host_of(u) in affiliated_domains()


def rel_attr(url: str, existing: str = "") -> str:
    """Return a rel=... attribute string, or '' when the link is not affiliated.

    Existing rel tokens are preserved and de-duplicated rather than overwritten.
    """
    if not is_affiliated(url):
        return ""
    tokens = [t for t in str(existing or "").split() if t]
    for t in REL_VALUE.split():
        if t not in tokens:
            tokens.append(t)
    return ' rel="' + " ".join(tokens) + '"'
