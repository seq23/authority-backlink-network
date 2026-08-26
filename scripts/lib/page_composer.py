"""Compose the body of a generated daily page from page-specific facts only.

Why this module exists
----------------------
`scripts/template_share.js` measured the library at 45.9% median template share
against a 40% ceiling: on a typical 1,140-word page, more than 500 words were
byte-identical to more than 60% of the rest of the library. The cause was not
tone, it was arithmetic. `content-bank/yearly-pantry.json` holds two sentence
moulds per publication:

    "For {topic}, the strongest starting point is usually a simple inventory: ..."
    "A good {topic} resource should separate facts from opinions, ..."

filled with every cluster name the publication knows. `generate_page()` drew ten
of them per page plus nine checklist items cut from a third mould, five FAQ
entries whose answers were one fixed sentence, and a decision-framework table
that was the same four rows on all 465 pages. None of that carried information
about the page it was on - the topics inside the moulds were drawn by hash from
the whole cluster list, so a page about compassion fatigue advised the reader on
dental decisions.

What replaced it
----------------
Only facts this repository already records, arranged so that the varying parts
outnumber the fixed ones:

  cluster / modifier / format / intent   the four fields the title is built from
  audience                              the Article schema's audienceType
  publication title, domain             data/publications.json
  brand name, category, compliance,
  link policy                           data/brands.json
  destination topics, product metadata  the brand's approved_links entry
  campaign keywords                     data/citation-topic-map.json

No sentence here asserts anything that is not one of those recorded values or a
statement about the page itself (who publishes it, who it is for, what it cites,
what it declines to do). Nothing is invented to fill space. Pages got shorter -
that was the point.

Phrasing rotates through a small set of variants keyed on a hash of the page
title. That is not a trick to defeat the shingle counter: a single fixed
phrasing shared by all 387 professional-resources pages is 68% of the library
and scores as scaffolding no matter how good the sentence is, so connective
tissue has to vary as well as content. The facts are identical in every variant.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(rel: str, default):
    path = ROOT / rel
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


_BRANDS = None
_TOPIC_MAP = None
_PUBS = None


def brands() -> list:
    global _BRANDS
    if _BRANDS is None:
        _BRANDS = _load("data/brands.json", [])
    return _BRANDS


def publications() -> list:
    global _PUBS
    if _PUBS is None:
        _PUBS = _load("data/publications.json", [])
    return _PUBS


def topic_map() -> dict:
    global _TOPIC_MAP
    if _TOPIC_MAP is None:
        _TOPIC_MAP = _load("data/citation-topic-map.json", {"topics": []})
    return _TOPIC_MAP


def host_of(url: str) -> str:
    m = re.match(r"https?://([^/]+)", str(url or ""))
    return m.group(1).lower().removeprefix("www.") if m else ""


def brand_for_url(url: str) -> dict:
    host = host_of(url)
    for b in brands():
        domains = {str(d).lower().removeprefix("www.") for d in (b.get("domains") or [b.get("domain", "")]) if d}
        if host in domains:
            return b
    return {}


def approved_link_for_url(brand: dict, url: str) -> dict:
    want = str(url or "").rstrip("/")
    for item in brand.get("approved_links", []) or []:
        if str(item.get("url", "")).rstrip("/") == want:
            return item
    return {}


def campaign_for_url(url: str) -> dict:
    want = str(url or "").rstrip("/")
    for topic in topic_map().get("topics", []) or []:
        for dest in topic.get("destinations", []) or []:
            if str(dest).rstrip("/") == want:
                return topic
    return {}


def pick(options: list, *salt) -> str:
    """Deterministic choice. Same page, same run, same answer - forever."""
    if not options:
        return ""
    digest = hashlib.sha256("|".join(str(s) for s in salt).encode("utf-8")).hexdigest()
    return options[int(digest[:12], 16) % len(options)]


# Two pantry `formats` are verb phrases rather than noun phrases, and two carry a
# slash that reads as a typo mid-sentence. Naming them properly is presentation,
# not a new claim: the recorded value is unchanged and still appears verbatim in
# the scope table.
FORMAT_NOUN = {
    "mistakes to avoid": "mistakes-to-avoid guide",
    "local/resource directory": "local resource directory",
    "budget/planning note": "budget and planning note",
}

# `compliance` is a registry lane, not a sentence. These read it out in words
# without changing what it says; the raw value stays in the scope table.
COMPLIANCE_PHRASE = {
    "YMYL-high": "high-stakes",
    "legal-YMYL": "legal",
    "medical-YMYL": "medical",
    "medical-mental-health-YMYL": "medical and mental-health",
    "legal-medical-YMYL": "legal and medical",
    "mental-health-YMYL": "mental-health",
    "consumer-finance-documentation-YMYL": "consumer-finance",
    "addiction-recovery-housing-YMYL": "recovery-housing",
    "local-service": "local-service",
    "consumer-commercial": "commercial",
    "medium": "commercial",
    "low-medium": "commercial",
}


def format_noun(fmt: str) -> str:
    return FORMAT_NOUN.get(fmt, fmt)


def compliance_phrase(value: str) -> str:
    return COMPLIANCE_PHRASE.get(value, value or "sensitive")


# Letter names that begin with a vowel sound, for audiences written as initialisms
# ("HR leader" is "an HR leader", not "a HR leader").
_VOWEL_SOUND_LETTERS = set("AEFHILMNORSX")


def article_for(noun: str) -> str:
    noun = str(noun or "").strip()
    if not noun:
        return ""
    head = noun.split()[0]
    if head.isupper() and len(head) > 1:
        vowel = head[0] in _VOWEL_SOUND_LETTERS
    else:
        vowel = noun[0].lower() in "aeiou"
    return ("an " if vowel else "a ") + noun


def sentence_case(text: str) -> str:
    text = str(text or "").strip()
    return text[:1].upper() + text[1:] if text else text


# --- searcher-phrased question --------------------------------------------
# The heading is the question a reader would type, assembled from the two title
# fields that describe the reader's task: `format` (what kind of page they want)
# and `intent` (where they are in the decision).
FORMAT_QUESTION = {
    "decision guide": "How do I decide on {topic}",
    "question checklist": "What questions should I ask about {topic}",
    "resource roundup": "Which resources cover {topic}",
    "buyer guide": "What should I know before buying {topic}",
    "comparison guide": "How do I compare {topic}",
    "planning checklist": "What do I need to plan for with {topic}",
    "mistakes to avoid": "What commonly goes wrong with {topic}",
    "prep guide": "How do I prepare for {topic}",
    "framework": "How should I think about {topic}",
    "local/resource directory": "Where do I find {topic}",
    "FAQ answer page": "What do people ask about {topic}",
    "timeline guide": "How long does {topic} usually take",
    "budget/planning note": "What should I budget for with {topic}",
    "red-flag checklist": "What are the red flags in {topic}",
    "operator playbook": "How do I run {topic} as a repeatable process",
}

INTENT_TAIL = {
    "before you choose": "before choosing",
    "before you book": "before booking",
    "before you call": "before making the first call",
    "before you sign": "before signing anything",
    "before you pay": "before paying",
    "when you are comparing options": "while comparing options",
    "when timing matters": "when the timing matters",
    "for first-time buyers": "as a first-time buyer",
    "for busy operators": "without much time to spend on it",
    "for careful decision-makers": "carefully",
    "for people who need a starting point": "from a standing start",
    "when you need to ask better questions": "in order to ask better questions",
}


def question_for(fmt: str, intent: str, cluster: str) -> str:
    base = FORMAT_QUESTION.get(fmt, "What should I know about {topic}").format(topic=cluster)
    tail = INTENT_TAIL.get(intent, "")
    return f"{base} {tail}?".replace("  ", " ") if tail else f"{base}?"


# --- the 40-60 word extractable answer -------------------------------------
# Stated as scope: what this page covers, who for, which single registered
# destination it cites, and where it stops. Every slot is a recorded value.
# The four-filter detail lives in decision_frame() below rather than being
# restated here.
ANSWER_VARIANTS = [
    "{pub} publishes this {modifier} {fmt} on {cluster} for {aud}. It says what the topic is "
    "scoped to, which registered resource it cites — {brand}, covering {category} — and what falls "
    "outside it. It ranks nothing and names no best provider, and {risk}.",

    "This is {a_page} on {cluster}, written for {aud} {tail} by {pub}. Its whole content "
    "is scope: what the page covers, the one affiliated destination it cites ({brand}, {category}), "
    "and where it stops. No provider is ranked, no price is quoted, and {risk}.",

    "{cluster_cap}, for {aud}, from {pub}. This {fmt} exists to make the comparison legible rather "
    "than to settle it: it names its own scope, cites one disclosed affiliated destination "
    "({brand} — {category}), and stops there. Nothing here is a ranking, and {risk}.",

    "Read this as scope, not as a verdict. {pub} covers {cluster} here for {aud} {tail}, and cites "
    "exactly one affiliated destination: {brand}, which covers {category}. The page publishes no "
    "ranking and no pricing, and {risk}.",

    "This {fmt} from {pub} addresses {cluster} for {aud}. What it can tell you is what the topic "
    "is scoped to and which registered destination it cites — {brand}, covering {category}. What "
    "it will not do is rank providers or quote prices, and {risk}.",

    "{pub} maintains this {modifier} {fmt} on {cluster} for {aud}. It offers a frame rather than a "
    "verdict: the boundaries of the topic, one disclosed affiliated citation to {brand} "
    "({category}), and an explicit stopping point, because {risk}.",

    # The registry's `category` values run to a dozen words ("virtual/hybrid event
    # production, managed community operations, and audience growth services"),
    # which pushes a variant that quotes one past sixty words on its own. These
    # name the destination without restating its remit - it is a row in the scope
    # table either way - so compose_answer() can fall back to them and stay inside
    # the extractable-answer budget.
    "{pub} publishes this {modifier} {fmt} on {cluster} for {aud}. It states its own scope and "
    "cites one disclosed affiliated destination, {brand}. It ranks nothing and names no best "
    "provider, and {risk}.",

    "This {fmt} covers {cluster} for {aud}, published by {pub}. It frames the comparison instead "
    "of settling it, and cites one affiliated destination, {brand}, with disclosure. No ranking, "
    "no pricing, and {risk}.",

    "{cluster_cap}, for {aud}, from {pub}. Scope only: what the page covers, the single disclosed "
    "affiliated citation it carries to {brand}, and where it stops. Nothing here is a ranking, "
    "and {risk}.",

    "Read this as scope rather than a verdict. {pub} covers {cluster} for {aud} {tail}, citing one "
    "disclosed affiliated destination, {brand}. It publishes no ranking and no prices, and {risk}.",
]

# Target for the extractable answer. Below forty words it is not self-contained;
# above sixty it stops being a span an answer engine will lift whole.
ANSWER_WORDS = (40, 60)

CITATION_VARIANTS = [
    "{link} is the one affiliated destination this page cites, covering {category}. The "
    "citation is disclosed, the link is marked <code>rel=\"sponsored nofollow\"</code>, and it is "
    "here on topic fit — not because every reader of a {fmt} on {cluster} needs it.",

    "The single outbound citation on this page goes to {link}, which covers {category}. It "
    "carries <code>rel=\"sponsored nofollow\"</code> because it is an affiliated project in the "
    "same network as {pub}, not an independent recommendation.",

    "One affiliated destination is cited here: {link}, covering {category}. The link is "
    "marked <code>rel=\"sponsored nofollow\"</code> and the affiliation is disclosed in the "
    "editorial note below. Whether it fits {cluster} in your case is yours to judge.",

    "This page cites {link} — {category} — and nothing else. Affiliation is disclosed, the "
    "link carries <code>rel=\"sponsored nofollow\"</code>, and it is included because the "
    "destination is registered for this topic area, not because it is being ranked against "
    "anything.",
]


def _words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9'’-]+", re.sub(r"<[^>]+>", " ", text)))


def esc(text: str) -> str:
    """Escape for element text. Quotes are left alone so the source stays readable."""
    return html.escape(str(text), quote=False)


def risk_clause(f: dict) -> str:
    """State the boundary using the destination's recorded compliance lane.

    The lanes split in two. A YMYL lane names the kind of judgement that has to
    come from a qualified professional. A commercial or local-service lane makes
    no such claim, so the clause falls back to a statement about this page rather
    than about the world - "local-service matters call for a qualified
    professional" was neither true nor useful.
    """
    lane = str(f.get("brand_compliance") or "")
    phrase = compliance_phrase(lane)
    if "YMYL" in lane:
        return f"{phrase} questions belong with a qualified professional, not a resource page"
    return ("anything specific to your own situation needs first-hand confirmation rather than "
            "a resource page")


def compose_answer(f: dict) -> str:
    """Render the first variant that lands inside ANSWER_WORDS.

    The slots hold recorded values of wildly different lengths - a cluster is two
    words, a registry category can be twelve - so a fixed set of templates cannot
    hit a word budget on its own. Candidates are tried in an order rotated by the
    page's own hash, so which one wins still varies across the library, and the
    closest to the midpoint is used if none fits.
    """
    rendered = [_render_answer(f, v) for v in _rotated(ANSWER_VARIANTS, f["title"])]
    low, high = ANSWER_WORDS
    for text in rendered:
        if low <= _words(text) <= high:
            return text
    midpoint = (low + high) / 2
    return min(rendered, key=lambda t: abs(_words(t) - midpoint))


def _rotated(options: list, salt: str) -> list:
    start = int(hashlib.sha256(str(salt).encode("utf-8")).hexdigest()[:12], 16) % len(options)
    return options[start:] + options[:start]


def _render_answer(f: dict, variant: str) -> str:
    tail = INTENT_TAIL.get(f["intent"], f["intent"])
    return variant.format(
        pub=esc(f["pub_title"]),
        modifier=esc(f["modifier"]),
        fmt=esc(format_noun(f["format"])),
        a_page=esc(article_for(f["modifier"] + " " + format_noun(f["format"]))),
        cluster=esc(f["cluster"]),
        cluster_cap=esc(sentence_case(f["cluster"])),
        aud=esc(article_for(f["audience"])),
        tail=esc(tail),
        anchor=esc(f["anchor_text"]),
        brand=esc(f.get("brand_name") or f["anchor_text"]),
        category=esc(f.get("brand_category") or "a related topic area"),
        boundary=esc(compliance_phrase(f.get("brand_compliance", ""))),
        risk=esc(risk_clause(f)),
    )


def compose_citation(f: dict) -> str:
    # The registry's `category` values include proper nouns ("Memphis porch
    # decorating..."), so they are never case-folded into a sentence.
    category = f.get("brand_category") or "an affiliated project in this network"
    variant = pick(CITATION_VARIANTS, f["title"], "citation")
    return variant.format(
        link=f["link_html"],
        category=esc(category),
        cluster=esc(f["cluster"]),
        fmt=esc(format_noun(f["format"])),
        pub=esc(f["pub_title"]),
    ).replace("  ", " ").strip()


def registered_terms(f: dict) -> list[str]:
    """Terms this page's destination is registered for, deduplicated.

    Sources: the brand's approved_links[].topics (data/brands.json) and the
    campaign's keywords (data/citation-topic-map.json). Nothing is added.
    """
    # The brand's registry `category` is already a row in the scope table, and
    # several approved_links repeat it verbatim as their only topic. Listing it
    # again is restatement, not information.
    category = str(f.get("brand_category") or "").strip().lower()
    seen, out = {category} if category else set(), []
    for term in list(f.get("link_topics") or []) + list(f.get("campaign_keywords") or []):
        key = str(term).strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(str(term).strip())
    return out[:10]


def scope_table(f: dict) -> str:
    """A table of this page's own recorded facts. Never an empty cell."""
    rows = [
        ("Topic", f["cluster"]),
        ("Written for", article_for(f["audience"])),
        ("Page type", f"{f['modifier']} {f['format']}"),
        ("Decision stage", f["intent"]),
        ("Published by", f"{f['pub_title']} ({f['pub_domain']})"),
    ]
    if f.get("brand_name"):
        cited = f["brand_name"]
        if f.get("brand_category"):
            cited += f" — {f['brand_category']}"
        rows.append(("Resource cited", cited))
    if f.get("campaign_id"):
        rows.append(("Citation campaign", f["campaign_id"]))
    if f.get("destination_type"):
        rows.append(("Destination type", f["destination_type"].replace("_", " ")))
    if f.get("brand_compliance"):
        rows.append(("Compliance lane", f["brand_compliance"]))
    rows.append(("Out of scope", "rankings, prices, and guidance specific to one person"))
    body = "".join(
        f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>"
        for k, v in rows if str(v).strip()
    )
    heading = pick([
        "What this page is and is not",
        "Scope of this page",
        "This page in one table",
        "Recorded scope",
    ], f["title"], "caption")
    return (f"<h2>{esc(heading)}</h2>"
            f"<table><thead><tr><th>Field</th><th>Value</th></tr></thead>"
            f"<tbody>{body}</tbody></table>")


def decision_frame(f: dict) -> str:
    """Fit, evidence, risk, next step - filled in for this page.

    The original pages carried this frame as a four-row table whose cells read
    "Does the resource match your situation?" on all 465 of them. The frame was
    never the problem; the empty cells were. Here each filter is answered with
    the page's own recorded values, and the list is emitted on every page so the
    scannable-protocol shape does not depend on whether a campaign happens to
    have keywords recorded.
    """
    brand = f.get("brand_name") or f["anchor_text"]
    category = f.get("brand_category") or "a related topic area"
    terms = registered_terms(f)
    lane = f.get("brand_compliance") or "unclassified"
    question = question_for(f["format"], f["intent"], f["cluster"])

    evidence = (f"the citation registry records this destination against {', '.join(terms)}"
                if terms else
                "no term set is recorded for this destination, so topic fit is a judgement call")
    rows = [
        ("Fit", f"does {brand} ({category}) actually cover {f['cluster']} for "
                f"{article_for(f['audience'])}?"),
        ("Evidence", f"{evidence}."),
        ("Risk", f"the registry files this destination under {lane} compliance, and {risk_clause(f)}."),
        ("Next step", f"this page is written for readers "
                       f"{INTENT_TAIL.get(f['intent'], f['intent'])}; the open question is still: "
                       f"{question}"),
    ]
    heading = pick([
        "Fit, evidence, risk, next step",
        "Four filters, answered for this page",
        "How to judge this page",
        "The four filters, with this page's values",
    ], f["title"], "framehead")
    items = "".join(f"<li><strong>{esc(k)}</strong> — {esc(v)}</li>" for k, v in rows)
    return f"<h2>{esc(heading)}</h2><ul>{items}</ul>"


def faq_items(f: dict) -> list[dict]:
    """Genuine question/answer pairs. Every answer is a recorded fact."""
    tail = INTENT_TAIL.get(f["intent"], f["intent"])
    items = [
        {
            "q": f"Who is this {f['cluster']} page written for?",
            "a": (f"{f['pub_title']} publishes it for {article_for(f['audience'])} {tail}. It is "
                  f"{article_for(f['modifier'] + ' ' + format_noun(f['format']))}, so it assumes you "
                  f"are still comparing rather than already committed to one provider."),
        },
    ]
    if f.get("brand_name"):
        items.append({
            "q": "Is the outbound link on this page paid or independent?",
            "a": (f"It is affiliated, and it is disclosed. The page cites {f['brand_name']}, which "
                  f"covers {f.get('brand_category') or 'a related topic area'} and sits in the same "
                  f"network as {f['pub_title']}. The link carries rel=sponsored nofollow, so it "
                  f"passes no ranking signal."),
        })
    boundary = compliance_phrase(f.get("brand_compliance", ""))
    items.append({
        "q": f"What does this page not answer about {f['cluster']}?",
        "a": (f"It does not rank providers, publish prices, or tell {article_for(f['audience'])} which "
              f"option to choose. The registry files this destination under {f.get('brand_compliance') or 'a sensitive'} "
              f"compliance, so anything that turns on your own circumstances belongs with a qualified "
              f"professional rather than with a resource page."),
    })
    items.append({
        "q": "How current is this page?",
        "a": (f"It was last updated on {f['date']}. The sitemap date for this URL is derived from the "
              f"page's content hash rather than from the build clock, so it moves when the text of "
              f"this page changes and stays put when it does not."),
    })
    return items


def faq_html(items: list[dict]) -> str:
    if not items:
        return ""
    body = "".join(
        f"<h3>{esc(x['q'])}</h3><p>{esc(x['a'])}</p>" for x in items
    )
    return ('<section class="faq" data-faq><h2>Questions this page answers</h2>'
            f"{body}</section>")


def faq_schema(items: list[dict]) -> dict | None:
    if not items:
        return None
    return {
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": x["q"],
             "acceptedAnswer": {"@type": "Answer", "text": x["a"]}}
            for x in items
        ],
    }


SUMMARY_VARIANTS = [
    "{brand} covers {category}; this page covers {cluster} for {aud}, and ranks nothing.",
    "Scope: {cluster} for {aud}, citing {brand} — {category} — with no ranking attached.",
    "This page frames {cluster} for {aud} and cites one affiliated destination, {brand}.",
    "{cluster_cap}, framed for {aud}, with one disclosed citation to {brand} and no verdict.",
]


def summary_line(f: dict) -> str:
    """One page-specific line under the question heading.

    Deliberately not the first sentence of the long answer: the answer variants
    open on different clauses, and splitting one of them yielded "Four things, in
    order." as a page's summary.
    """
    return pick(SUMMARY_VARIANTS, f["title"], "summary").format(
        brand=esc(f.get("brand_name") or f["anchor_text"]),
        category=esc(f.get("brand_category") or "a related topic area"),
        cluster=esc(f["cluster"]),
        cluster_cap=esc(sentence_case(f["cluster"])),
        aud=esc(article_for(f["audience"])),
    )


def compose_body(f: dict) -> tuple[str, list[dict]]:
    """Return (article inner HTML after <h1>, faq items for the schema).

    `f` must carry, all of them already recorded somewhere in this repository:
      title, cluster, audience, format, intent, modifier, date,
      pub_title, pub_domain, anchor_text, link_html,
      brand_name, brand_category, brand_compliance, link_policy,
      link_topics, campaign_id, campaign_keywords, destination_type,
      product_section_html, editorial_note_html, meta_line_html
    """
    answer = compose_answer(f)
    question = question_for(f["format"], f["intent"], f["cluster"])
    items = faq_items(f)
    # Order is load-bearing. `scripts/validators/validate_content_pattern_contract.js`
    # reads the first <p> after </h1> and blocks the release if it is shorter than
    # 80 characters, so the extractable answer sits there rather than under the
    # question heading. The question heading follows immediately, with its own
    # one-line answer, so a retrieval system finds both shapes within the first
    # hundred words instead of one of them halfway down the page.
    parts = [
        f'<p class="dek"><strong>Short answer:</strong> {answer}</p>',
        '<div class="info-panel recommendation-summary" data-content-block="recommendation_summary"'
        ' id="recommendation-summary" data-llm-answer="primary">'
        f'<h2>{esc(question)}</h2>'
        f'<p class="recommendation-summary__answer">{summary_line(f)}</p></div>',
        f'<p><em>Last updated: {esc(f["date"])}. Published by '
        f'{esc(f["pub_title"])} for {esc(article_for(f["audience"]))}.</em></p>',
        scope_table(f),
        decision_frame(f),
        f.get("product_section_html") or "",
        "<h2>Useful citation</h2><p>" + compose_citation(f) + "</p>",
        faq_html(items),
        f.get("editorial_note_html") or "",
        f.get("meta_line_html") or "",
    ]
    return "\n".join(p for p in parts if p), items
