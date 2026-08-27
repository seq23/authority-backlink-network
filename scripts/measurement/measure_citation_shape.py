#!/usr/bin/env python3
"""
measure_citation_shape.py -- repeatable citation-shape measurement for the
authority network publications.

Two halves:

  A) EVIDENCE SIDE. Re-derives, from local-guides-citation-velocity's
     data/report_fixes/html_report_contract.generated.json, how often 46
     external agent runs asked for each page-shape feature. This is the
     target shape -- the shape that reviewers actually recommend on pages
     being evaluated for citation.

  B) SUBJECT SIDE. Measures the same features on every published HTML page
     in authority-backlink-network/sites/.

The point is the delta. Run it again after any content change to see whether
the gap moved. Deterministic, no network, no paid tools.

Usage:
  python3 measure_citation_shape.py \
      --sites  /path/to/authority-backlink-network/sites \
      --evidence /path/to/html_report_contract.generated.json \
      --out    /path/to/report.json
"""

from __future__ import annotations

import argparse
import collections
import html
import json
import os
import re
import sys

# --------------------------------------------------------------------------
# A) EVIDENCE SIDE
# --------------------------------------------------------------------------

# Each feature is a family of surface forms that reviewers use to ask for the
# same underlying page shape. Matched case-insensitively against recommendation
# prose. These are shape signals, never text to copy onto a page.
EVIDENCE_PATTERNS = {
    "comparison_table": r"comparison table|compare[a-z]* table|side[- ]by[- ]side|comparison (?:chart|grid|matrix|block|module|section)|vs\.? table|scorecard|comparison of",
    "checklist": r"checklist|step[- ]by[- ]step|numbered steps|bullet(?:ed)? list of|list of questions|questions to ask|actionable steps",
    "direct_answer": r"direct answer|answer (?:box|block|up front|first|immediately)|short answer|tl;?dr|upfront answer|answer the question|lead with the answer|summary (?:box|block) (?:at|near) the top|above the fold answer",
    "cost": r"\bcost\b|\bpricing\b|\bprice\b|\bfee[s]?\b|how much|\$[0-9]|dollar",
    "named_sources": r"cite|citation|source[s]?\b|authoritative|\.gov\b|\.edu\b|reference[s]?\b|attribut",
    "geo": r"\bgeo\b|local|city|state|near me|region|zip|location|metro",
}


def load_evidence_corpus(path):
    """Every distinct recommendation-bearing string in the contract file."""
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)

    texts = []
    for fix in doc.get("fixes", []):
        for field in ("fix_recommendation", "raw_text"):
            val = fix.get(field)
            if isinstance(val, str) and val.strip():
                texts.append(val.strip())
        rec = fix.get("recommendation_fields") or {}
        if isinstance(rec, dict):
            for val in rec.values():
                if isinstance(val, str) and val.strip():
                    texts.append(val.strip())

    for spec in doc.get("page_specs", []):
        for field in ("why_worth_building", "route_reason", "admission_basis"):
            val = spec.get(field)
            if isinstance(val, str) and val.strip():
                texts.append(val.strip())
        for line in spec.get("raw_lines") or []:
            if isinstance(line, str) and line.strip():
                texts.append(line.strip())

    # Distinct texts, order-stable.
    seen, uniq = set(), []
    for t in texts:
        if t not in seen:
            seen.add(t)
            uniq.append(t)

    incumbent = collections.Counter(
        f.get("fix_type") for f in doc.get("fixes", [])
    )
    return doc, uniq, incumbent


def measure_evidence(texts):
    counts = collections.Counter()
    for text in texts:
        low = text.lower()
        for feature, pattern in EVIDENCE_PATTERNS.items():
            if re.search(pattern, low):
                counts[feature] += 1
    total = len(texts) or 1
    return {
        feature: {
            "hits": counts[feature],
            "share_of_recommendations": round(counts[feature] / total, 4),
        }
        for feature in EVIDENCE_PATTERNS
    }


# --------------------------------------------------------------------------
# B) SUBJECT SIDE -- HTML shape detection
# --------------------------------------------------------------------------

TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
TABLE_RE = re.compile(r"<table\b.*?</table>", re.S | re.I)
TH_RE = re.compile(r"<th\b[^>]*>(.*?)</th>", re.S | re.I)
TR_RE = re.compile(r"<tr\b.*?</tr>", re.S | re.I)
LIST_RE = re.compile(r"<(ul|ol)\b[^>]*>(.*?)</\1>", re.S | re.I)
LI_RE = re.compile(r"<li\b[^>]*>(.*?)</li>", re.S | re.I)
H1_RE = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.S | re.I)
H2_RE = re.compile(r"<h2\b[^>]*>(.*?)</h2>", re.S | re.I)
MAIN_RE = re.compile(r"<main\b[^>]*>(.*?)</main>", re.S | re.I)
LDJSON_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I
)
ANCHOR_RE = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.S | re.I)
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
REL_RE = re.compile(r'rel=["\']([^"\']*)["\']', re.I)
CURRENCY_RE = re.compile(r"\$\s?[0-9][0-9,]*")
NUMBER_UNIT_RE = re.compile(
    r"\b[0-9][0-9,]*(?:\.[0-9]+)?\s?(?:dollars|usd|per hour|/hour|per month|/month|per year)\b",
    re.I,
)

# Structural chrome that is not article body: nav blocks, footer, disclosure
# asides, breadcrumb. Stripped before counting "substantive" text so that a
# page's unique contribution is not inflated by template furniture.
CHROME_RE = re.compile(
    r"<(nav|footer|header|aside)\b.*?</\1>", re.S | re.I
)


def strip_tags(fragment):
    fragment = SCRIPT_STYLE_RE.sub(" ", fragment)
    fragment = TAG_RE.sub(" ", fragment)
    return re.sub(r"\s+", " ", html.unescape(fragment)).strip()


def is_comparison_table(table_html):
    """
    A comparison table compares >=2 named options across >=2 attributes.

    A two-column Field/Value metadata table compares nothing and is excluded --
    this is the single most important discrimination in this script, because a
    naive '<table>' grep scores those as comparison tables.
    """
    headers = [strip_tags(h).lower() for h in TH_RE.findall(table_html)]
    headers = [h for h in headers if h]
    rows = len(TR_RE.findall(table_html))
    if rows < 3:  # header + >=2 data rows
        return False
    if len(headers) < 3:
        # Two columns can still compare, but not when the headers are the
        # generic metadata pair.
        if len(headers) == 2 and headers[0] in {"field", "attribute", "item", "key"}:
            return False
        return False
    return True


def detect_direct_answer(main_html):
    """
    A direct answer is a short, self-contained answer placed before the body,
    where an extractive answer engine will actually find it.
    """
    signals = []
    if 'data-content-block="recommendation_summary"' in main_html:
        signals.append("recommendation_summary_block")
    head = main_html[: main_html.find("</section>") + 10] if "</section>" in main_html else main_html[:4000]
    for h2 in H2_RE.findall(head):
        label = strip_tags(h2).lower()
        if re.search(r"short answer|the answer|quick answer|in short|tl;?dr", label):
            signals.append("short_answer_heading")
            break
    for blob in LDJSON_RE.findall(main_html):
        if re.search(r'"@type"\s*:\s*"(FAQPage|QAPage|Question)"', blob):
            signals.append("faq_schema")
            break
    return signals


def detect_geo(page_html, ld_blobs):
    signals = []
    for blob in ld_blobs:
        if re.search(r'"@type"\s*:\s*"(Place|LocalBusiness|PostalAddress|City|AdministrativeArea)"', blob):
            signals.append("place_schema")
            break
        if '"areaServed"' in blob or '"addressLocality"' in blob:
            signals.append("area_served")
            break
    h1s = " ".join(strip_tags(h) for h in H1_RE.findall(page_html)).lower()
    if re.search(r"\b(memphis|tennessee|near me|in [a-z]+ county|nashville|germantown|collierville|bartlett)\b", h1s):
        signals.append("geo_in_h1")
    return signals


# A title is a retrieval surface. An answer engine matches a question to a page;
# a title assembled from internal taxonomy slots matches no question.
QUERY_SHAPE_RE = re.compile(
    r"^(how|what|when|where|why|which|who|can|should|do|does|is|are|will|\d+\s)", re.I
)
SLOT_MODIFIER_RE = re.compile(
    r"\b(beginner-safe|aeo-ready|geo-ready|no-fluff|human-first|operator-grade|"
    r"citation-friendly|plain-english|decision-focused|editorial|low-risk|"
    r"2026-ready|comparison-friendly|practical|checklist-driven)\b",
    re.I,
)
SLOT_STAGE_RE = re.compile(
    r"\b(before you (?:book|choose|sign|pay|buy)|for first-time buyers|"
    r"when timing matters|when you are comparing options|"
    r"for careful decision-makers|for people who need a starting point|"
    r"when you need to ask better questions|when money is on the line)\b",
    re.I,
)

STOPWORDS = set(
    "a an the to of for in on at is are do does how what when where which with "
    "and or vs my me you your i it that this be can should need best much many "
    "long far get got new old".split()
)


def query_tokens(text):
    return {
        w
        for w in re.findall(r"[a-z0-9]+", (text or "").lower())
        if w not in STOPWORDS and len(w) > 2
    }


def analyse_page(path, root):
    raw = open(path, encoding="utf-8", errors="replace").read()
    main_match = MAIN_RE.search(raw)
    main_html = main_match.group(1) if main_match else raw
    body_html = CHROME_RE.sub(" ", main_html)
    body_text = strip_tags(body_html)
    ld_blobs = LDJSON_RE.findall(raw)

    tables = TABLE_RE.findall(raw)
    comparison_tables = [t for t in tables if is_comparison_table(t)]

    # Lists: keep only those with >=3 items, and record item text so the
    # corpus pass can decide which are boilerplate.
    lists = []
    for _tag, inner in LIST_RE.findall(body_html):
        items = [strip_tags(i) for i in LI_RE.findall(inner)]
        items = [i for i in items if i]
        if len(items) >= 3:
            lists.append(items)

    direct_answer = detect_direct_answer(main_html)
    geo = detect_geo(raw, ld_blobs)

    currency_hits = CURRENCY_RE.findall(body_text) + NUMBER_UNIT_RE.findall(body_text)
    cost_heading = any(
        re.search(r"\bcost|\bprice|\bpricing|\bfee\b|how much|budget", strip_tags(h).lower())
        for h in H2_RE.findall(body_html)
    )

    authoritative, affiliated, bad_rel = [], [], []
    for attrs, _label in ANCHOR_RE.findall(raw):
        href_m = HREF_RE.search(attrs)
        if not href_m:
            continue
        href = href_m.group(1)
        rel = (REL_RE.search(attrs).group(1).lower() if REL_RE.search(attrs) else "")
        if 'data-source="external-authority"' in attrs:
            authoritative.append(href)
        if "sponsored" in rel:
            affiliated.append(href)
            if "nofollow" not in rel:
                bad_rel.append(href)

    h1 = strip_tags(H1_RE.search(raw).group(1)) if H1_RE.search(raw) else ""
    rel = os.path.relpath(path, root)
    title_m = re.search(r"<title\b[^>]*>(.*?)</title>", raw, re.S | re.I)
    dek_m = re.search(r'<p class="dek">(.*?)</p>', raw, re.S | re.I)
    retrieval_label = " ".join(
        [
            h1,
            strip_tags(title_m.group(1)) if title_m else "",
            strip_tags(dek_m.group(1)) if dek_m else "",
            rel.replace(os.sep, " ").replace("-", " "),
        ]
    )

    return {
        "path": rel,
        "bytes": len(raw),
        "body_words": len(body_text.split()),
        "body_text": body_text,
        "h1": h1,
        "retrieval_tokens": sorted(query_tokens(retrieval_label)),
        "title_query_shaped": bool(QUERY_SHAPE_RE.match(h1)),
        "title_taxonomy_slot": bool(
            SLOT_MODIFIER_RE.search(h1) or SLOT_STAGE_RE.search(h1)
        ),
        "tables_total": len(tables),
        "comparison_tables": len(comparison_tables),
        "lists": lists,
        "direct_answer_signals": direct_answer,
        "cost_currency_hits": len(currency_hits),
        "cost_heading": cost_heading,
        "authoritative_links": len(authoritative),
        "affiliated_links": len(affiliated),
        "affiliated_links_missing_nofollow": len(bad_rel),
        "geo_signals": geo,
    }


def boilerplate_pass(pages, threshold=0.20):
    """
    A list, or a body sentence, that recurs on >=threshold of pages is template
    furniture, not this page's answer. Identifying it separates 'the page has a
    checklist' from 'the page has a checklist about this question'.
    """
    n = len(pages) or 1

    list_freq = collections.Counter()
    for page in pages:
        for items in page["lists"]:
            list_freq["".join(items)] += 1
    boilerplate_lists = {k for k, v in list_freq.items() if v / n >= threshold}

    sent_freq = collections.Counter()
    page_sents = []
    for page in pages:
        sents = {
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", page["body_text"])
            if len(s.strip()) > 40
        }
        page_sents.append(sents)
        for s in sents:
            sent_freq[s] += 1
    boilerplate_sents = {k for k, v in sent_freq.items() if v / n >= threshold}

    for page, sents in zip(pages, page_sents):
        own = [items for items in page["lists"] if "".join(items) not in boilerplate_lists]
        page["unique_lists"] = len(own)
        page["boilerplate_lists"] = len(page["lists"]) - len(own)
        # A page-specific checklist: >=3 items, not template furniture, and
        # phrased as steps or questions rather than a link menu.
        page["page_specific_checklist"] = any(
            len(items) >= 3
            and sum(1 for i in items if len(i.split()) >= 4) >= 3
            for items in own
        )
        unique_sents = [s for s in sents if s not in boilerplate_sents]
        page["unique_sentences"] = len(unique_sents)
        page["boilerplate_sentences"] = len(sents) - len(unique_sents)
        page["unique_words"] = sum(len(s.split()) for s in unique_sents)
        page["boilerplate_share"] = (
            round(1 - page["unique_words"] / page["body_words"], 4)
            if page["body_words"]
            else None
        )
        del page["body_text"]
        del page["lists"]

    return {
        "boilerplate_list_variants": len(boilerplate_lists),
        "boilerplate_sentence_variants": len(boilerplate_sents),
        "threshold": threshold,
    }


def measure_query_coverage(doc, pages):
    """
    The evidence names the queries where the incumbent is weak or absent. Open
    ground is only worth anything if the network actually publishes a page on
    it, so this measures the overlap rather than assuming it.
    """
    by_strength = collections.defaultdict(set)
    for fix in doc.get("fixes", []):
        q = (fix.get("query") or "").strip()
        if not q:
            continue
        ft = (fix.get("fix_type") or "").lower()
        if "incumbent" in ft:
            by_strength[ft].add(q)

    page_tokens = [(p["path"], set(p["retrieval_tokens"])) for p in pages]

    def best(q):
        qt = query_tokens(q)
        if not qt:
            return 0.0, None
        top, where = 0.0, None
        for rel, pt in page_tokens:
            ov = len(qt & pt) / len(qt)
            if ov > top:
                top, where = ov, rel
        return top, where

    def bucket(queries):
        strong = partial = missing = 0
        uncovered = []
        for q in sorted(queries):
            score, _where = best(q)
            if score >= 0.75:
                strong += 1
            elif score >= 0.50:
                partial += 1
            else:
                missing += 1
                uncovered.append(q)
        n = len(queries) or 1
        return {
            "queries": len(queries),
            "strong_match": strong,
            "partial_match": partial,
            "no_page": missing,
            "no_page_share": round(missing / n, 4),
            "uncovered_examples": uncovered[:25],
        }

    open_ground = by_strength["no incumbent"] | by_strength["weak incumbent"]
    held_ground = by_strength["medium incumbent"] | by_strength["strong incumbent"]
    return {
        "definition": "query-token coverage of the best-matching page's h1+title+dek+slug",
        "open_ground_no_or_weak_incumbent": bucket(open_ground),
        "held_ground_medium_or_strong_incumbent": bucket(held_ground),
    }


def summarise(pages, label):
    n = len(pages) or 1

    def share(pred):
        hits = sum(1 for p in pages if pred(p))
        return {"pages": hits, "share": round(hits / n, 4)}

    auth_counts = [p["authoritative_links"] for p in pages]
    return {
        "publication": label,
        "pages": len(pages),
        "shape": {
            "comparison_table": share(lambda p: p["comparison_tables"] > 0),
            "checklist_any_list": share(lambda p: p["unique_lists"] + p["boilerplate_lists"] > 0),
            "checklist_page_specific": share(lambda p: p["page_specific_checklist"]),
            "direct_answer": share(lambda p: bool(p["direct_answer_signals"])),
            "cost": share(lambda p: p["cost_currency_hits"] > 0),
            "cost_heading_only": share(lambda p: p["cost_heading"] and p["cost_currency_hits"] == 0),
            "named_sources": share(lambda p: p["authoritative_links"] > 0),
            "geo": share(lambda p: bool(p["geo_signals"])),
        },
        "retrieval_surface": {
            "title_query_shaped": share(lambda p: p["title_query_shaped"]),
            "title_taxonomy_slot": share(lambda p: p["title_taxonomy_slot"]),
            "note": "a taxonomy-slot title matches no question a person asks",
        },
        "false_positive_check": {
            "pages_with_any_table": share(lambda p: p["tables_total"] > 0),
            "pages_with_comparison_table": share(lambda p: p["comparison_tables"] > 0),
            "note": "gap between these two is metadata (Field/Value) tables a naive <table> grep would miscount as comparison tables",
        },
        "outbound": {
            "authoritative_links_per_page": round(sum(auth_counts) / n, 3),
            "affiliated_links_per_page": round(
                sum(p["affiliated_links"] for p in pages) / n, 3
            ),
            "affiliated_links_missing_nofollow": sum(
                p["affiliated_links_missing_nofollow"] for p in pages
            ),
        },
        "body": {
            "median_body_words": sorted(p["body_words"] for p in pages)[len(pages) // 2]
            if pages
            else 0,
            "median_unique_words": sorted(p["unique_words"] for p in pages)[len(pages) // 2]
            if pages
            else 0,
            "median_boilerplate_share": sorted(
                p["boilerplate_share"] for p in pages if p["boilerplate_share"] is not None
            )[len(pages) // 2]
            if pages
            else None,
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", required=True)
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--boilerplate-threshold", type=float, default=0.20)
    args = ap.parse_args()

    doc, texts, incumbent = load_evidence_corpus(args.evidence)
    evidence = {
        "source": os.path.basename(args.evidence),
        "generated_at": doc.get("generated_at"),
        "manifests_seen": doc.get("manifests_seen"),
        "fixes_discovered": doc.get("fixes_discovered"),
        "distinct_recommendation_texts": len(texts),
        "feature_frequency": measure_evidence(texts),
        "incumbent_strength": {
            "no_incumbent": incumbent.get("no incumbent", 0),
            "weak_incumbent": incumbent.get("weak incumbent", 0),
            "medium_incumbent": incumbent.get("medium incumbent", 0),
            "strong_incumbent": incumbent.get("strong incumbent", 0),
        },
    }

    pages = []
    for dirpath, _dirs, files in os.walk(args.sites):
        for fn in sorted(files):
            if fn.endswith(".html"):
                pages.append(analyse_page(os.path.join(dirpath, fn), args.sites))
    pages.sort(key=lambda p: p["path"])

    corpus = boilerplate_pass(pages, args.boilerplate_threshold)
    query_coverage = measure_query_coverage(doc, pages)

    by_pub = collections.defaultdict(list)
    by_cohort = collections.defaultdict(list)
    for page in pages:
        by_pub[page["path"].split(os.sep)[0]].append(page)
        m = re.search(r"daily[/\\](\d{4})-(\d{2})-\d{2}-", page["path"])
        by_cohort[f"{m.group(1)}-{m.group(2)}" if m else "standing"].append(page)
        del page["retrieval_tokens"]

    report = {
        "schema_version": 1,
        "measurement": "citation_shape_gap",
        "evidence_side": evidence,
        "corpus_boilerplate": corpus,
        "query_coverage": query_coverage,
        "subject_side": {
            "all_publications": summarise(pages, "ALL"),
            "per_publication": [summarise(v, k) for k, v in sorted(by_pub.items())],
            "by_publish_cohort": [
                summarise(v, k) for k, v in sorted(by_cohort.items())
            ],
        },
        "pages": pages,
    }

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=False)

    print(json.dumps({k: v for k, v in report.items() if k != "pages"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
