#!/usr/bin/env python3
"""Single source of truth for which outbound links are affiliated, and how they are marked.

Affiliation is resolved from data/brands.json, the same file link_audit.py reads.

Which affiliated links are FOLLOWED is resolved from data/portfolio-link-policy.json
(owner decision, 11 Oct 2026): links to the owner's own portfolio domains are
plain editorial links with no rel at all. Every other affiliated destination --
the client properties in brands.json (Hicks Consulting, Dianne's Place), whose
Search Console is not ours to risk -- keeps rel="sponsored nofollow", and so does
any URL matching the policy's affiliate-tag patterns (Amazon tags and the like).

rel_attr() below is the ONE rule that writes rel on a generated outbound link;
every generator calls it, and validate_portfolio_link_policy.py checks the
published output against the same two lists.
"""
from __future__ import annotations
import json, os
from functools import lru_cache
from urllib.parse import urlparse

REL_VALUE = "sponsored nofollow"
# Tokens that withhold ranking credit. None of them may sit on a portfolio link.
WITHHOLDING_TOKENS = frozenset({"nofollow", "sponsored", "ugc"})
POLICY_PATH = "data/portfolio-link-policy.json"


def _repo_path(rel: str) -> str:
    if os.path.exists(rel):
        return rel
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), rel)


@lru_cache(maxsize=1)
def link_policy() -> dict:
    with open(_repo_path(POLICY_PATH), encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def portfolio_domains() -> frozenset[str]:
    """The owner's portfolio domains: links to these are followed."""
    return frozenset(str(d).strip().lower().removeprefix("www.")
                     for d in link_policy().get("owner_portfolio_domains", []) if d)


def is_portfolio(url: str) -> bool:
    u = str(url or "").strip()
    if not u.lower().startswith(("http://", "https://")):
        return False
    return host_of(u) in portfolio_domains()


def is_paid_affiliate_url(url: str) -> bool:
    """A tagged affiliate/paid URL (Amazon tag=, network click-through, ...)."""
    import re
    u = str(url or "")
    return any(re.search(p, u, re.I) for p in link_policy().get("nofollow_required_url_patterns", []))


def nofollow_required(url: str) -> bool:
    """True when the link must carry rel="sponsored nofollow".

    A tagged affiliate URL always does, even on a portfolio host. Otherwise an
    affiliated (brands.json) destination does unless it is on the owner's
    portfolio list.
    """
    if is_paid_affiliate_url(url):
        return True
    return is_affiliated(url) and not is_portfolio(url)


@lru_cache(maxsize=1)
def affiliated_domains(brands_path: str = "data/brands.json") -> frozenset[str]:
    brands_path = _repo_path(brands_path)
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


def rel_tokens_for(url: str, existing: str = "") -> list[str]:
    """The rel tokens a link to `url` must carry, merging `existing`.

    Portfolio links lose nofollow/sponsored/ugc and keep anything else (noopener);
    links that require it gain "sponsored nofollow"; everything else is untouched.
    """
    tokens = [t for t in str(existing or "").split() if t]
    if nofollow_required(url):
        for t in REL_VALUE.split():
            if t not in tokens:
                tokens.append(t)
    elif is_portfolio(url):
        tokens = [t for t in tokens if t.lower() not in WITHHOLDING_TOKENS]
    return tokens


def rel_attr(url: str, existing: str = "") -> str:
    """Return a rel=... attribute string, or '' when the link needs none.

    Portfolio links are followed and get no rel. Client and tagged affiliate
    links get rel="sponsored nofollow". Existing tokens are preserved.
    """
    if not (is_affiliated(url) or is_portfolio(url) or is_paid_affiliate_url(url)):
        return ""
    tokens = rel_tokens_for(url, existing)
    return (' rel="' + " ".join(tokens) + '"') if tokens else ""
