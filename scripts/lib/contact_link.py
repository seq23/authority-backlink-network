#!/usr/bin/env python3
"""The one way this network is allowed to publish an editorial email address.

What went wrong
---------------
Every published page carries the governance footer, and the last item in that
footer is the editorial contact address, written as a plain `mailto:` anchor:

    <li><a href="mailto:editor@memphisvendorlibrary.com">editor@...</a></li>

The three publications are served by Cloudflare with **Email Address
Obfuscation** switched on at the zone. That feature rewrites every `mailto:`
anchor in the HTML response, at the edge, into:

    <a href="/cdn-cgi/l/email-protection#<hex>">[email&nbsp;protected]</a>

plus an `email-decode.min.js` that restores the real address in the browser.
The rewrite happens AFTER the origin, so it is invisible in this repository and
in every static check that reads `sites/`.

`/cdn-cgi/l/email-protection` only resolves when the URL fragment is present,
and fragments are never sent to a server. A crawler that does not execute
JavaScript therefore requests `https://<domain>/cdn-cgi/l/email-protection`
and gets **HTTP 404**. Confirmed 2026-09-03 against all three live origins.

The result: one broken internal link on every single page of every publication.
Measured on the live sites the same day --

    professionalresourcelibrary.com   421 of 421 pages
    memphisvendorlibrary.com          105 of 105 pages
    founderoperatorlibrary.com        105 of 105 pages

which is exactly what Ahrefs reported as "Page has links to broken page" on the
2026-09-03 01:08-01:39 UTC crawl, and is why site health collapsed to 4, 13 and
12. Nothing in `sites/` was wrong. The origin HTML is clean; the CDN broke it.

The fix
-------
Cloudflare's documented per-element opt-out is a pair of HTML comments. Anything
between them is left alone by the obfuscator:

    <!--email_off-->  ...  <!--/email_off-->

So this module is the only place in the repository that renders an email
address, and it always renders it inside those markers. Import `mailto_link()`
rather than writing `<a href="mailto:...">` by hand -- the guard
`scripts/validators/validate_internal_links_resolve.py` reads THIS module's
markers and fails any published page carrying an unwrapped `mailto:`.

Why keep the address on every page at all
-----------------------------------------
The alternative fix -- drop the contact address from the per-page footer and
leave it only on /masthead and /corrections -- also removes the broken link, and
was rejected. A reachable named editor on every page is the point of the
governance footer (docs/EDITORIAL-INDEPENDENCE.md); it is an asset for exactly
the readers, journalists and quality raters those pages were built for. The
defect was never the address. It was the edge rewriting it into a 404.

Why not just switch obfuscation off at the zone
-----------------------------------------------
That needs a Cloudflare API credential the repository does not hold, so it would
be a NAMED STOP rather than a fix, and it would also disable obfuscation for
every address on the zone. The opt-out is per element, needs no credential, and
lives in the generator that caused the problem.
"""
from __future__ import annotations

import html

# Cloudflare Email Address Obfuscation opt-out markers. These are HTML comments,
# so they are inert to every other consumer of the markup: browsers, parsers,
# page_audit.py and the hostile reviewer all ignore them.
EMAIL_OFF_OPEN = "<!--email_off-->"
EMAIL_OFF_CLOSE = "<!--/email_off-->"


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def mailto_link(address: str, label: str | None = None) -> str:
    """An email anchor the CDN will not rewrite into /cdn-cgi/l/email-protection.

    `label` defaults to the address itself, which is what every footer wants.
    """
    if not address or "@" not in str(address):
        raise ValueError(f"mailto_link() needs a real address, got {address!r}")
    text = esc(label if label is not None else address)
    return (
        f"{EMAIL_OFF_OPEN}"
        f'<a href="mailto:{esc(address)}">{text}</a>'
        f"{EMAIL_OFF_CLOSE}"
    )


def is_wrapped(markup: str, start: int, end: int) -> bool:
    """Is the anchor at markup[start:end] inside an email_off region?

    Used by the guard. Looks backwards for the nearest marker: if the closest
    thing behind the anchor is an opening marker, the anchor is protected.
    """
    before = markup[:start]
    opened = before.rfind(EMAIL_OFF_OPEN)
    closed = before.rfind(EMAIL_OFF_CLOSE)
    if opened == -1 or opened < closed:
        return False
    return markup.find(EMAIL_OFF_CLOSE, end) != -1
