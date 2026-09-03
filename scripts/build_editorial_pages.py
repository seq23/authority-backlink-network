#!/usr/bin/env python3
"""Build the editorial governance pages for all three publications.

Four pages per publication -- masthead, editorial standards, corrections and
contributors -- plus one author page per real contributor in
data/contributors.json (which ships empty, and must stay that way until a real
person agrees to be credited).

Why these pages exist
---------------------
The three publications disclose their affiliation in body prose but have no
masthead, no corrections route, no sourcing standard and no stated AI-use
policy. Those four things are what a reader, a journalist or a search quality
rater actually looks for when deciding whether a site is a publication or a
link surface. The affiliation itself is not the problem -- Wirecutter and
Consumer Reports both disclose commercial relationships openly and are trusted
anyway -- the absence of anywhere to complain to is.

What is derived rather than written
-----------------------------------
The conflict-of-interest list on each masthead is derived at build time from
data/brands.json via `approved_publications`. It is not hand-maintained, so it
cannot drift away from the affiliations the link registry actually permits. Add
a brand to a publication's lane and it appears on that publication's masthead
on the next build.

Validation contract (see docs/EDITORIAL-INDEPENDENCE.md for the full list)
--------------------------------------------------------------------------
Every page emitted here must satisfy the gates that run in `validate:changed`:
  * exactly one <h1>, non-empty <title>, <meta name="description">, lang="en"
  * an <h2>Short answer</h2> heading  (content_pattern: direct_answer)
  * at least one absolute https:// anchor  (content_pattern: conversion_path)
  * no empty <td>/<th>  (content_pattern: no_empty_table_cells)
  * the literal string "Affiliation disclosed."  (hostile_review)
  * the exact regulated-advice sentence, because these pages say "legal" and
    "contract"  (hostile_review sensitive-topic rule)
  * no outbound URL outside the brand registry, the publication domains and
    schema.org  (hostile_review + link_audit)
  * valid JSON-LD  (page_audit INVALID_JSONLD)
`assert_publishable()` at the bottom re-checks all of that before writing, so a
future content edit fails here with a clear message rather than in CI.
"""

import html
import json
import pathlib
import re
import sys
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from byline import entity_for, parent_company, subsidiary_clause  # noqa: E402
from lib.contact_link import mailto_link  # noqa: E402

# The exact sentence hostile_review.py requires on any page mentioning a
# regulated subject. These pages all mention "legal" and "contract", so it is
# unconditional. Do not reword it.
ADVICE_BOUNDARY = ("This page is informational. It is not legal, medical, "
                   "mental-health, immigration, financial, or professional advice.")

# hostile_review.py matches these as naked lowercase substrings. "cure " also
# matches inside "secure ", "procure " and "obscure ", which is why this file
# says "protect" and "keep safe" instead.
BANNED_SUBSTRINGS = ("guaranteed settlement", "guaranteed results", "guaranteed approval",
                     "guaranteed success", "guaranteed healing", "best lawyer", "best dentist",
                     "best civil surgeon", "best equine lawyer", "diagnose you", "cure ",
                     "cures ", "official provider endorsement", "safe for everyone")

# validate_published_tree_purity.py HARD_FAILs on these phrases anywhere in a
# published file.
OPERATOR_MARKERS = ("owner / operator view", "backlink operations", "backlink ledger rows")


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def load(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def host_of(url: str) -> str:
    netloc = urlparse(url).netloc if str(url).startswith("http") else str(url)
    return netloc.lower().replace("www.", "").strip("/")


# --------------------------------------------------------------- allowlist

def allowed_hosts(publications: list, brands: list) -> set:
    """Every host this build is permitted to emit an absolute URL for.

    Mirrors the union hostile_review.py enforces. Kept here so a bad link fails
    at build time with the offending URL named, rather than as an opaque
    external_domain_not_in_registry row in an audit report.
    """
    hosts = {"schema.org", "clarity.ms", "www.clarity.ms"}
    hosts |= {host_of(p["working_domain"]) for p in publications}
    for brand in brands:
        for domain in (brand.get("domains") or [brand.get("domain", "")]):
            if domain:
                hosts.add(host_of(domain))
    return hosts


# ------------------------------------------------------------------ chrome

HEADER_RE = re.compile(r"<header>.*?</header>", re.S | re.I)


def site_header(folder: str, pub_title: str, home: str) -> str:
    """Reuse the publication's own masthead from index.html.

    Lifted rather than rebuilt so these pages cannot drift away from the rest of
    the site, and so a later navigation change picks them up for free. The tag
    must stay a bare <header> with no attributes: build_demand_shape_pages.py
    reads it with the same regex and exits if it cannot match.
    """
    index = ROOT / folder / "index.html"
    if index.exists():
        found = HEADER_RE.search(index.read_text(encoding="utf-8"))
        if found:
            return found.group(0)
    return f'<header><strong>{esc(pub_title)}</strong><nav><a href="{esc(home)}">{esc(pub_title)}</a></nav></header>'


def editorial_footer(pub_title: str, domain: str, editor_addr: str) -> str:
    """The governance footer, identical to the one install_editorial_chrome.py
    puts on every other page. Bare <footer> tag -- see site_header()."""
    home = f"https://{domain}"
    links = [
        ("Masthead", f"{home}/masthead"),
        ("Editorial standards", f"{home}/editorial-standards"),
        ("Corrections", f"{home}/corrections"),
        ("Contributors", f"{home}/contributors"),
    ]
    items = "".join(f'<li><a href="{esc(u)}">{esc(t)}</a></li>' for t, u in links)
    # Wrapped by lib.contact_link so Cloudflare's Email Address Obfuscation
    # leaves it alone. An unwrapped mailto: is rewritten at the edge into
    # /cdn-cgi/l/email-protection, which the origin 404s -- one broken internal
    # link on every published page. See scripts/lib/contact_link.py.
    items += f'<li>{mailto_link(editor_addr)}</li>'
    return (
        "<footer>"
        f'<ul class="editorial-nav">{items}</ul>'
        f'<p class="byline" data-byline="publisher">{esc(pub_title)} is written and '
        f"edited by <strong>{esc(entity_for(pub_title))}</strong>{esc(subsidiary_clause())}. Pages here "
        f"carry that byline and no other: this publication names no individual author, "
        f"and never attributes a page to someone who did not write it.</p>"
        f"<p>{esc(entity_for(pub_title))} is under common ownership with several of the projects this "
        f"publication cites. Those citations are labelled on the page and carry "
        f"<code>rel=\"sponsored nofollow\"</code>, so they pass no ranking signal. "
        f"<strong>Affiliation disclosed.</strong> No fake rankings, no paid placement, "
        f"and no listing that can be bought.</p>"
        f"<p>&copy; 2026 {esc(pub_title)}. {esc(ADVICE_BOUNDARY)}</p>"
        "</footer>"
    )


def page_shell(*, title: str, description: str, url: str, folder: str, pub_title: str,
               domain: str, editor_addr: str, schema: dict, body: str) -> str:
    home = f"https://{domain}"
    crumb = (
        '<nav class="breadcrumb" data-nav="breadcrumb" aria-label="Breadcrumb">'
        f'<a href="{esc(home)}/">{esc(pub_title)}</a>'
        '<span class="breadcrumb__sep"> / </span>'
        f'<span aria-current="page">{esc(title)}</span></nav>'
    )
    return (
        '<!doctype html>\n<html lang="en">\n<head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{esc(title)} | {esc(pub_title)}</title>"
        f'<meta name="description" content="{esc(description)}">'
        f'<link rel="canonical" href="{esc(url)}">'
        '<link rel="stylesheet" href="/styles.css">'
        '<script type="application/ld+json">'
        + json.dumps(schema, ensure_ascii=False) +
        "</script></head>\n<body>\n"
        + site_header(folder, pub_title, home + "/") +
        '<main class="page">' + crumb + '<article class="policy">'
        + body +
        "</article></main>\n"
        + editorial_footer(pub_title, domain, editor_addr) +
        "\n</body>\n</html>\n"
    )


def org_schema(pub_title: str, home: str, mission: str) -> dict:
    return {"@type": "Organization", "name": pub_title, "url": home,
            "@id": home + "/#publisher", "description": mission}


def web_page_schema(kind: str, name: str, url: str, description: str,
                    pub_title: str, home: str, mission: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@graph": [
            org_schema(pub_title, home, mission),
            {"@type": kind, "name": name, "url": url, "@id": url,
             "description": description,
             "publisher": {"@id": home + "/#publisher"},
             "isPartOf": {"@type": "WebSite", "name": pub_title, "url": home}},
        ],
    }


# ------------------------------------------------------------------- pages

def masthead_page(pub, ed, pubed, brands, editor_addr, corrections_addr) -> tuple:
    domain = pub["working_domain"]
    home = f"https://{domain}"
    url = f"{home}/masthead"
    title = "Masthead and ownership"
    entity = ed["publisher_entity"]
    byline = entity_for(pub["title"])

    # Derived, not hand-written: the brands this publication's link registry
    # actually permits it to cite.
    affiliated = [b for b in brands if pub["id"] in b.get("approved_publications", [])]
    rows = "".join(
        f"<tr><td>{esc(b['name'])}</td>"
        f"<td>{esc(b.get('category') or 'Affiliated project')}</td>"
        f"<td>Commonly owned</td></tr>"
        for b in sorted(affiliated, key=lambda x: x["name"].lower())
    ) or "<tr><td>None</td><td>No affiliated project is cited by this publication</td>"\
         "<td>Not applicable</td></tr>"

    body = f"""<h1>Who is responsible for {esc(pub['title'])}</h1>
<p class="dek">Ownership, accountability and how to reach the desk about anything on this site.</p>
<h2>Short answer</h2>
<p>{esc(pub['title'])} is written, edited and published by <strong>{esc(byline)}</strong>, the
editorial company for this publication{esc(subsidiary_clause())}. That company is the byline on
every page here. It is under common ownership with several of the projects this publication
cites, which is disclosed here, in every page footer, and next to every affiliated link, because
a reader who finds out later has been misled, and a reader who is told up front can weigh it.</p>

<h2>Responsible publisher</h2>
<div class="policy">
<dl>
<dt>{esc(entity['role'])}</dt>
<dd>{esc(byline)}. Accountable for what this publication says, for correcting it when it
is wrong, and for the standards on the <a href="{esc(home)}/editorial-standards">sourcing
and AI-use standards</a> page.</dd>
<dt>Corporate relationship</dt>
<dd>{esc(byline)} is the editorial company for {esc(pub['title'])} and nothing else. Every
publication in this group has an editorial company of its own{esc(subsidiary_clause())}. No other
corporate detail is published here: this page states the relationship and stops, rather than
dressing it up with particulars that nobody has established.</dd>
<dt>Named staff</dt>
<dd>None. This publication does not name individual editors or writers, does not publish staff
biographies or credentials, and does not put a personal byline on a page. Where that changes, a
named contributor will appear on the <a href="{esc(home)}/contributors">contributors page</a>
with a profile they control, and only on the pages they actually wrote.</dd>
<dt>What this publication covers</dt>
<dd>{esc(ed['publications'][pub['id']]['beat'])}.</dd>
<dt>Who it is written for</dt>
<dd>{esc(ed['publications'][pub['id']]['audience'])}.</dd>
<dt>Editorial contact</dt>
<dd>{mailto_link(editor_addr)}</dd>
<dt>Corrections</dt>
<dd>{mailto_link(corrections_addr)} &mdash; see the
<a href="{esc(home)}/corrections">corrections policy and log</a>.</dd>
</dl>
</div>

<h2>Ownership and commercial relationships</h2>
<p>{esc(entity['note'])}</p>
<p>{esc(entity['accountability'])}</p>
<p>The three publications in this group each have their own editorial company, and those
companies are commonly owned. They are therefore not independent of each other and do not claim
to be. What they are independent of is any payment for coverage: nothing on this site can be
bought, and no listing, mention or placement is for sale at any price.</p>
<p>The projects below are commonly owned with this publication. Where a page cites one, the
citation is labelled on the page and carries <code>rel="sponsored nofollow"</code> so it passes
no ranking signal to the destination. This publication publishes no rankings, no awards and no
scored comparisons, so an affiliated project cannot be ranked above anything.</p>
<table>
<thead><tr><th>Affiliated project</th><th>What it is</th><th>Relationship</th></tr></thead>
<tbody>{rows}</tbody>
</table>

<h2>What this publication will not do</h2>
<ul>
<li>It will not accept payment to include, exclude, rank or remove anything.</li>
<li>It will not publish a review, rating or award. It does not run any.</li>
<li>It will not attribute a quote to a person who did not say it.</li>
<li>It will not present an affiliated project as an independent recommendation.</li>
<li>It will not exchange links with another site for the purpose of ranking.</li>
</ul>

<h2>How to reach the desk</h2>
<p>Editorial questions, corrections, pitches and complaints all reach {esc(byline)} at the
addresses above. {esc(ed['corrections_policy']['response_target'])} If you believe a page here is wrong,
the <a href="{esc(home)}/corrections">corrections page</a> is the fastest route and the one that
produces a public record.</p>
<p>{esc(ADVICE_BOUNDARY)}</p>"""

    schema = web_page_schema("AboutPage", title, url,
                             "Ownership, accountability and editorial contact.",
                             pub["title"], home, pub.get("mission", ""))
    # The responsible party is the editorial company, not a person. There is no
    # Person node anywhere in this build: naming one would mean naming somebody,
    # and nobody has agreed to be named. `name` here is byte-identical to the
    # visible footer byline and to the JSON-LD author on every article, because
    # all three call byline.entity_for() -- the disagreement this replaces had
    # 552 pages claiming an Organization author under a person's visible byline.
    publisher_node = {
        "@type": "Organization", "name": byline,
        "@id": home + "/masthead#publisher-entity",
        "description": f"The editorial company that writes, edits and publishes {pub['title']}.",
    }
    parent = parent_company()
    if parent:
        publisher_node["parentOrganization"] = {"@type": "Organization", "name": parent}
    schema["@graph"].append(publisher_node)
    schema["@graph"][0]["publishingPrinciples"] = home + "/editorial-standards"
    return "masthead.html", url, title, \
        "Ownership, accountability and editorial contact for " + pub["title"] + ".", schema, body


def standards_page(pub, ed, pubed, editor_addr, corrections_addr) -> tuple:
    domain = pub["working_domain"]
    home = f"https://{domain}"
    url = f"{home}/editorial-standards"
    title = "Editorial standards"
    ai = ed["ai_use"]

    sourcing = "".join(f"<li>{esc(s)}</li>" for s in pubed["sourcing"])
    ai_does = "".join(f"<li>{esc(s)}</li>" for s in ai["does"])
    ai_not = "".join(f"<li>{esc(s)}</li>" for s in ai["does_not"])

    body = f"""<h1>Editorial standards for {esc(pub['title'])}</h1>
<p class="dek">How pages here are sourced, how they are produced, what is disclosed, and where
this publication stops.</p>
<h2>Short answer</h2>
<p>Pages are sourced from primary documents and named people, produced with substantial
automated assistance that is described in full below, and disclosed as affiliated wherever they
cite a commonly owned project. This publication does not rank, does not review, and does not
sell placement.</p>

<h2>Sourcing standard</h2>
<ul>{sourcing}</ul>
<p>Where a page cannot meet that standard it says what is not known instead of filling the gap.
A page that would have to guess at a figure states that the figure is not published.</p>

<h2 id="ai-use">{esc(ai['headline'])}</h2>
<p><strong>{esc(ai['summary'])}</strong></p>
<p>This is stated plainly because the alternative -- implying that every page is hand-written and
hand-checked -- would be false. What the automated system does:</p>
<ul>{ai_does}</ul>
<p>What it does not do, and what no page on this site contains:</p>
<ul>{ai_not}</ul>
<p>{esc(ai['commitment'])}</p>

<h2>Affiliation and conflicts of interest</h2>
<p>{esc(pub['disclosure'])}</p>
<p>Every affiliated citation is labelled where it appears, carries
<code>rel="sponsored nofollow"</code>, and is listed by name on the
<a href="{esc(home)}/masthead">ownership disclosure</a>. Affiliation determines nothing about placement,
because there is no placement to determine: this publication runs no rankings, no scored
comparisons and no awards. A reader who distrusts an affiliated citation can disregard it and
the surrounding page still answers the question it asked.</p>
<p>Nobody can pay to appear here, and nobody can pay to be removed. There is no advertising
relationship, no sponsored post, and no arrangement in which a third party sees a page before
it publishes.</p>

<h2>What this publication does not publish</h2>
<ul>
<li>Rankings, ratings, scores, awards and "best of" lists of any kind.</li>
<li>Reviews written without the reviewer having used the thing.</li>
<li>Quotes, testimonials, case studies or survey figures that were not obtained.</li>
<li>Anonymous expert attribution. A source is named or the claim is dropped.</li>
<li>Content produced in exchange for a link, a payment or a reciprocal mention.</li>
</ul>

<h2>Where this publication stops</h2>
<p>{esc(pubed['stance'])}</p>
<p>{esc(ADVICE_BOUNDARY)}</p>

<h2>Corrections</h2>
<p>{esc(ed['corrections_policy']['promise'])} Write to
{mailto_link(corrections_addr)}, or read the full
<a href="{esc(home)}/corrections">corrections policy</a>. General editorial contact is
{mailto_link(editor_addr)}.</p>"""

    schema = web_page_schema("WebPage", title, url,
                             "Sourcing, production, AI use, affiliation and corrections policy.",
                             pub["title"], home, pub.get("mission", ""))
    return "editorial-standards.html", url, title, \
        "Sourcing standards, AI-use disclosure, conflict-of-interest policy and corrections "\
        "policy for " + pub["title"] + ".", schema, body


def corrections_page(pub, ed, corrections_addr) -> tuple:
    domain = pub["working_domain"]
    home = f"https://{domain}"
    url = f"{home}/corrections"
    title = "Corrections policy and log"
    cp = ed["corrections_policy"]

    qualifies = "".join(f"<li>{esc(s)}</li>" for s in cp["what_qualifies"])
    does_not = "".join(f"<li>{esc(s)}</li>" for s in cp["what_does_not"])

    entries = pubed_corrections(ed, pub["id"])
    if entries:
        log = "".join(
            f'<li><time datetime="{esc(e["date"])}">{esc(e["date"])}</time>'
            f'<p><a href="{esc(e["url"])}">{esc(e["page"])}</a> &mdash; {esc(e["what_changed"])}</p></li>'
            for e in entries)
        log_html = f'<ul class="corrections-log">{log}</ul>'
    else:
        log_html = ('<p class="empty-state">No corrections have been issued for this '
                    'publication yet. When one is, it appears here with the date, the page and '
                    'what changed. An empty log is a statement that nothing has been corrected, '
                    'not that nothing has been reported.</p>')

    body = f"""<h1>Corrections policy and log for {esc(pub['title'])}</h1>
<p class="dek">How to report an error, what happens next, and every correction this publication
has issued.</p>
<h2>Short answer</h2>
<p>Write to {mailto_link(corrections_addr)} with the page
address and what is wrong. {esc(cp['response_target'])} {esc(cp['promise'])}</p>

<div class="contact-block">
<p><strong>Corrections address:</strong>
{mailto_link(corrections_addr)}</p>
<p>Include the page address, the statement you believe is wrong, and -- if you have one -- the
source that shows what is correct. You do not need to be the subject of the page to report an
error on it.</p>
</div>

<h2>What gets corrected</h2>
<ul>{qualifies}</ul>

<h2>What does not get changed on request</h2>
<ul>{does_not}</ul>
<p>A request in the second category still gets a reply. It just does not get a silent edit.</p>

<h2>How a correction is handled</h2>
<ol>
<li>The report is acknowledged. {esc(cp['response_target'])}</li>
<li>The claim is checked against the source the page relied on.</li>
<li>If the page is wrong it is fixed, and a note is added to the page itself saying what was
changed and when.</li>
<li>The correction is added to the log below with the date and the page.</li>
<li>If the page is not wrong, the reporter is told why, with the source.</li>
</ol>
<p>Corrections are not made silently. A page that has been materially corrected says so. This
matters more than it sounds: a publication that quietly edits its errors is indistinguishable
from one that never had any, and that is not a claim this site is willing to imply.</p>

<h2>Correction log</h2>
{log_html}

<h2>Related</h2>
<p>The full <a href="{esc(home)}/editorial-standards">statement of editorial standards</a>
covers sourcing, automated production and affiliation. The
<a href="{esc(home)}/masthead">ownership disclosure</a> names who is responsible.</p>
<p>{esc(ADVICE_BOUNDARY)}</p>"""

    schema = web_page_schema("WebPage", title, url,
                             "How to report an error and every correction issued.",
                             pub["title"], home, pub.get("mission", ""))
    return "corrections.html", url, title, \
        "How to report an error in " + pub["title"] + ", and the full log of corrections "\
        "issued.", schema, body


def pubed_corrections(ed, pub_id) -> list:
    """Corrections are logged in data/editorial.json under the publication.

    Returns [] today. Each entry needs date, page, url and what_changed.
    """
    return ed["publications"][pub_id].get("corrections", [])


def contributors_page(pub, ed, contributors, pitch_addr) -> tuple:
    domain = pub["working_domain"]
    home = f"https://{domain}"
    url = f"{home}/contributors"
    title = "Contributors and bylines"
    cpol = ed["contributor_policy"]

    mine = [c for c in contributors if pub["id"] in c.get("publications", [])]
    if mine:
        cards = "".join(
            f'<div class="author-card"><h3>'
            f'<a href="{esc(home)}/contributors/{esc(c["id"])}">{esc(c["name"])}</a></h3>'
            f'<p class="note">{esc(c["role"])}</p><p>{esc(c["bio"])}</p></div>'
            for c in sorted(mine, key=lambda x: x["name"].lower()))
        listing = cards
    else:
        listing = (f'<p class="empty-state">{esc(cpol["status"])} There is no contributor list '
                   f'below because there are no contributors, and inventing one would be the '
                   f'fastest way to make everything else on this page worthless.</p>')

    reqs = "".join(f"<li>{esc(s)}</li>" for s in cpol["requirements"])

    body = f"""<h1>Contributors and byline policy</h1>
<p class="dek">Who writes for {esc(pub['title'])}, how bylines are used, and how to write for it.</p>
<h2>Short answer</h2>
<p>Every page here is bylined <strong>{esc(entity_for(pub['title']))}</strong>, the editorial
company for this publication. {esc(cpol['status'])} When a named person writes for this
publication they get a byline on their own work and an author page, and nothing else carries
their name.</p>

<h2>Current contributors</h2>
{listing}

<h2>How bylines work here</h2>
<p>{esc(cpol['credit'])}</p>
<p>Pages produced by the automated system described in the
<a href="{esc(home)}/editorial-standards">statement of editorial standards</a> do not carry a
personal byline, because no person wrote them. They are attributed to
{esc(entity_for(pub['title']))}, which is answerable for them as an organisation. That
distinction is the whole point of having a byline system at all: a person's name on a page has
to mean that person is answerable for it, or it means nothing. The same name appears in this
page's machine-readable metadata as the author, so an automated reader and a human reader are
told the same thing.</p>

<h2>What a contributor needs</h2>
<ul>{reqs}</ul>
<p>A contributor keeps the copyright in their own work and can have it removed if the
relationship ends. Their author page links to a profile they control, so the credit follows them
rather than being trapped here.</p>

<h2>What this publication offers</h2>
<ul>
<li>A byline, an author page, and a link to a profile the contributor controls.</li>
<li>Editing for accuracy and scope, not for search placement.</li>
<li>No obligation to mention, cite or favour any affiliated project. A contributor who wants
nothing to do with the affiliated projects can write a page that cites none of them.</li>
<li>A published correction if this publication gets something wrong in their work.</li>
</ul>

<h2>How to write for this publication</h2>
<p>Write to {mailto_link(pitch_addr)} with the question you want
to answer, why you are the person to answer it, and where your work can be read. Pitches that
are really link requests are declined, and a pitch that offers a payment in either direction is
declined automatically.</p>
<p>{esc(ADVICE_BOUNDARY)}</p>"""

    schema = web_page_schema("CollectionPage", title, url,
                             "Byline policy and current contributors.",
                             pub["title"], home, pub.get("mission", ""))
    return "contributors.html", url, title, \
        "Byline policy, contributor requirements and how to write for " + pub["title"] + ".", \
        schema, body


def author_page(contributor, pub, ed, allowed) -> tuple:
    """One page per real contributor. Never called today -- contributors[] is empty."""
    domain = pub["working_domain"]
    home = f"https://{domain}"
    cid = contributor["id"]
    url = f"{home}/contributors/{cid}"
    name = contributor["name"]

    # sameAs points at domains this build is not otherwise allowed to emit.
    # Refuse loudly rather than shipping a page that HARD_FAILs hostile_review
    # with an unhelpful message.
    for profile in contributor.get("sameAs", []):
        host = host_of(profile)
        if host not in allowed:
            raise SystemExit(
                f"\ncontributor '{cid}': sameAs host '{host}' is not allowlisted.\n"
                f"  scripts/hostile_review.py scans the whole raw file including JSON-LD and\n"
                f"  will HARD_FAIL on this URL: {profile}\n"
                f"  Register the domain before adding this contributor. See\n"
                f"  docs/EDITORIAL-INDEPENDENCE.md -> 'Adding a real contributor'.\n")

    creds = contributor.get("credentials") or []
    creds_html = ("<h2>Credentials</h2><ul>"
                  + "".join(f"<li>{esc(c)}</li>" for c in creds) + "</ul>") if creds else ""
    disc = contributor.get("disclosures") or []
    disc_html = ("<h2>Disclosures</h2><ul>"
                 + "".join(f"<li>{esc(d)}</li>" for d in disc) + "</ul>") if disc else \
                ("<h2>Disclosures</h2><p>This contributor has declared no commercial interest in "
                 "the subjects they cover here.</p>")
    links = contributor.get("sameAs", [])
    links_html = ('<p class="author-card__links">'
                  + " &middot; ".join(f'<a href="{esc(u)}" rel="nofollow">{esc(host_of(u))}</a>'
                                      for u in links) + "</p>") if links else ""

    body = f"""<h1>{esc(name)}</h1>
<p class="dek">{esc(contributor['role'])} at {esc(pub['title'])}.</p>
<h2>Short answer</h2>
<p>{esc(contributor['bio'])}</p>
<div class="author-card"><h3>{esc(name)}</h3>
<p class="note">{esc(contributor['role'])} &middot; contributing since
{esc(contributor.get('since', 'this year'))}</p>{links_html}</div>
{creds_html}
{disc_html}
<h2>About this byline</h2>
<p>This page exists so a byline on {esc(pub['title'])} points at an accountable person. Pages
carrying this byline were written by {esc(name)}. Pages without a personal byline were not, and
are attributed to the publication instead -- see the
<a href="{esc(home)}/editorial-standards">statement of editorial standards</a> for how those
are produced.</p>
<p>{esc(ADVICE_BOUNDARY)}</p>"""

    schema = web_page_schema("ProfilePage", name, url,
                             contributor["bio"], pub["title"], home, pub.get("mission", ""))
    person = {"@type": "Person", "name": name, "@id": url + "#person",
              "jobTitle": contributor["role"], "description": contributor["bio"],
              "url": url}
    if links:
        person["sameAs"] = links
    schema["@graph"].append(person)
    schema["@graph"][1]["mainEntity"] = {"@id": url + "#person"}
    return f"contributors/{cid}.html", url, name, contributor["bio"][:300], schema, body


# -------------------------------------------------------------- publishing

def assert_publishable(rel_path: str, page: str) -> None:
    """Re-check the gates before writing. A failure here names the page."""
    low = page.lower()
    problems = []

    if page.count("<h1") != 1:
        problems.append(f"needs exactly one <h1>, found {page.count('<h1')}")
    if not re.search(r"<title>[^<]+</title>", page):
        problems.append("missing a non-empty <title>")
    if 'name="description"' not in page:
        problems.append("missing <meta name=\"description\">")
    if 'lang="en"' not in page:
        problems.append("missing lang=\"en\"")
    if not re.search(r"<h[23][^>]*>\s*(?:Quick|Direct|Short)\s+answer", page, re.I):
        problems.append("missing the 'Short answer' heading (content_pattern: direct_answer)")
    if not re.search(r'<a[^>]+href="https?://', page, re.I):
        problems.append("no absolute https anchor (content_pattern: conversion_path)")
    if re.search(r"<t[dh][^>]*>\s*</t[dh]>", page, re.I):
        problems.append("has an empty <td>/<th> (content_pattern: no_empty_table_cells)")
    if "affiliation disclosed" not in low:
        problems.append("missing the literal 'Affiliation disclosed' (hostile_review)")
    if ("not legal, medical, mental-health, immigration, financial, or professional advice"
            not in low):
        problems.append("missing the regulated-advice sentence (hostile_review)")
    for phrase in BANNED_SUBSTRINGS:
        if phrase in low:
            problems.append(f"contains banned substring {phrase!r} (hostile_review)")
    for marker in OPERATOR_MARKERS:
        if marker in low:
            problems.append(f"contains operator marker {marker!r} (published_tree_purity)")
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        try:
            json.loads(block)
        except json.JSONDecodeError as exc:
            problems.append(f"invalid JSON-LD: {exc}")

    words = len(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)[\s\S]*?</\1>", " ", page)).split())
    if words < 450:
        problems.append(f"only {words} words; page_audit warns under 450")

    if problems:
        raise SystemExit(f"\n{rel_path} is not publishable:\n" +
                         "".join(f"  - {p}\n" for p in problems))


def main() -> int:
    write = "--write" in sys.argv
    publications = load("data/publications.json")
    brands = load("data/brands.json")
    ed = load("data/editorial.json")
    contributors = load("data/contributors.json")["contributors"]
    allowed = allowed_hosts(publications, brands)

    written, unchanged = [], []

    for pub in publications:
        pid = pub["id"]
        if pid not in ed["publications"]:
            raise SystemExit(f"data/editorial.json has no entry for publication '{pid}'")
        pubed = ed["publications"][pid]
        domain = pub["working_domain"]
        pre = pubed["contact_prefixes"]
        editor_addr = f"{pre['editor']}@{domain}"
        corrections_addr = f"{pre['corrections']}@{domain}"
        pitch_addr = f"{pre['pitch']}@{domain}"

        builders = [
            masthead_page(pub, ed, pubed, brands, editor_addr, corrections_addr),
            standards_page(pub, ed, pubed, editor_addr, corrections_addr),
            corrections_page(pub, ed, corrections_addr),
            contributors_page(pub, ed, contributors, pitch_addr),
        ]
        for c in contributors:
            if pid in c.get("publications", []):
                builders.append(author_page(c, pub, ed, allowed))

        for rel_name, url, title, description, schema, body in builders:
            page = page_shell(title=title, description=description, url=url,
                              folder=pub["folder"], pub_title=pub["title"], domain=domain,
                              editor_addr=editor_addr, schema=schema, body=body)
            target = ROOT / pub["folder"] / rel_name
            rel_path = str(target.relative_to(ROOT))

            # Nothing this build emits may point outside the allowlist.
            for found in re.findall(r'https?://[^\s"\'<>)]+', page):
                host = host_of(found)
                if host not in allowed:
                    raise SystemExit(f"{rel_path}: outbound host '{host}' is not allowlisted "
                                     f"({found})")
            assert_publishable(rel_path, page)

            if target.exists() and target.read_text(encoding="utf-8") == page:
                unchanged.append(rel_path)
                continue
            if write:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(page, encoding="utf-8")
            written.append(rel_path)

    print(json.dumps({
        "mode": "write" if write else "check",
        "written": written, "unchanged": len(unchanged),
        "contributors": len(contributors),
    }, indent=2))
    if not write and written:
        print("\n(dry run -- pass --write to apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
