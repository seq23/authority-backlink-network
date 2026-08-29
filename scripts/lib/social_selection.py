#!/usr/bin/env python3
"""One answer to "which queued post goes out next, and what exactly does it say".

Why this module exists
----------------------
One thing consumes the social queue: scripts/social_publisher.py. It can send a
post through a platform's own API or hand it to a declared delivery route --
Buffer, for X -- and those two lanes must select the same post, in the same
order, with the same characters. If each kept its own idea of ordering and its
own idea of how a body becomes post text, the route would carry different posts
from the ones the API would have sent: two components each keeping their own
list, with no link between them.

So the ordering and the text rendering live here once, and every lane uses
them. A post handed to Buffer is, by construction, the same post in the same
order that the API would have sent.

There used to be a third consumer, a copy-paste sheet the owner posted from by
hand. It was retired on 2026-08-29 -- she said she would never post from it --
so Buffer is now the whole of X's distribution.

Nothing in here opens a network connection or mutates the queue.
"""
from __future__ import annotations

import re
from collections import defaultdict

# Kept in step with POSTABLE_STATUSES in scripts/social_publisher.py and
# scripts/lib/social_platforms.py.
POSTABLE_STATUSES = {"queued_for_auto_post", "approved_for_auto_post"}

PLATFORM_ORDER = ("linkedin", "x")

# Conservative trim for X. URL length is platform-normalized; keep it simple.
X_MAX_CHARS = 275
X_TRIM_TO = 272


def append_url(body, item):
    url = item.get("source_url") or item.get("target_url") or ""
    if url and url not in body:
        return (body.rstrip() + "\n\n" + url).strip()
    return (body or "").strip()


def trim_x(text):
    if len(text) <= X_MAX_CHARS:
        return text
    return text[:X_TRIM_TO].rstrip() + "…"


def post_text(item):
    """The exact string that would be sent to the platform for this entry.

    The drafts sheet renders this, not the raw body, so what the owner pastes is
    character-for-character what the API would have posted.

    The X length trim takes it out of the BODY, never out of the URL. Trimming
    the assembled string cut the link instead, because the URL is last: two of
    the first eight drafts ever generated ended
    "...-mistakes-to-avoid-before-you\u2026", which is a post with a dead link -
    no click, no citation, no backlink, and nothing to show for the slot it
    spent. The whole point of these posts is the URL at the end of them.
    """
    body = (item.get("body", "") or "").strip()
    url = item.get("source_url") or item.get("target_url") or ""
    if item.get("platform") != "x":
        return append_url(body, item)
    if not url or url in body:
        return trim_x(append_url(body, item))
    room = X_MAX_CHARS - len(url) - 2
    if room < 1:
        # A URL that fills the post on its own. Send the link alone rather than
        # a mangled one.
        return url
    if len(body) > room:
        body = body[:room - 1].rstrip() + "\u2026"
    return (body + "\n\n" + url).strip()


def normalize(text):
    text = re.sub(r"https?://\S+", "", text or "")
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def jaccard_text(a, b):
    wa = set(re.findall(r"[a-z]{4,}", normalize(a)))
    wb = set(re.findall(r"[a-z]{4,}", normalize(b)))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def brand_of(item):
    return item.get("brand") or item.get("domain") or "unknown"


def eligible_in_priority_order(queue, policy, today, today_ordinal,
                               platforms=PLATFORM_ORDER):
    """Indices of postable entries, highest value first.

    Verbatim the selection scripts/social_publisher.py has always used, lifted
    out so the drafts lane cannot drift from it:

      * round-robin across brands within a platform, so one brand sitting at the
        top of the file cannot take every slot;
      * brands with fewer prior posts relative to their configured quota surface
        first (weighted_posted_score), which is what stops portfolio starvation;
      * the brand start position rotates by date ordinal, so the same brand is
        not always first;
      * within a brand, entries never attempted come before entries already
        attempted, today's pages before older ones, and entries carrying a URL
        before entries without one.
    """
    quotas = (policy or {}).get("brand_quotas", {})
    if not isinstance(quotas, dict):
        quotas = {}

    def brand_weight(brand):
        try:
            return float(quotas.get(brand, 1.0))
        except (TypeError, ValueError):
            return 1.0

    seen_order = {}
    posted_by_brand_platform = defaultdict(int)
    for item in queue:
        brand = brand_of(item)
        seen_order.setdefault(brand, len(seen_order))
        if item.get("status") == "posted":
            posted_by_brand_platform[(item.get("platform"), brand)] += 1

    def weighted_posted_score(platform, brand):
        return posted_by_brand_platform[(platform, brand)] / max(brand_weight(brand), 0.01)

    def item_priority(i):
        item = queue[i]
        return (
            item.get("last_attempt_at", ""),
            0 if item.get("date") == today else 1,
            0 if item.get("source_url") else 1,
            i,
        )

    groups = defaultdict(list)
    for i, item in enumerate(queue):
        if item.get("status") not in POSTABLE_STATUSES:
            continue
        groups[(item.get("platform"), brand_of(item))].append(i)
    for key in groups:
        groups[key].sort(key=item_priority)

    ordered = []
    for platform in platforms:
        brand_keys = [key for key in groups if key[0] == platform]
        rotation_offset = today_ordinal % max(len(brand_keys), 1)
        brand_keys.sort(key=lambda key: (
            weighted_posted_score(key[0], key[1]),
            (seen_order.get(key[1], 9999) - rotation_offset) % max(len(brand_keys), 1),
            key[1],
        ))
        more = True
        while more:
            more = False
            for key in brand_keys:
                group = groups[key]
                if group:
                    ordered.append(group.pop(0))
                    more = True
    return ordered
