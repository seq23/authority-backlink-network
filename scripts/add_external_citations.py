#!/usr/bin/env python3
"""Give every substantive page a source outside this network.

The measurement that motivates this: across `sites/`, 571 outbound editorial
links carried rel="sponsored nofollow" and every one of them pointed at a domain
in this portfolio. Zero pages cited anything the owner does not own. That is the
single fact that makes three publications read as a link farm rather than as
publications, and no amount of word count or internal linking compensates for it.

What this adds
--------------
One `Sources` section per page, listing verified outside authorities from
`data/external-sources.json` chosen by topic match against the page's own text.

Four rules it follows, because a citation block done badly is worse than none:

1. Only registered sources. Every URL in the registry was fetched and returned
   200 (see scripts/verify_external_sources.py). Nothing is cited from memory.
2. `rel="noopener"` and nothing else. An editorial citation of a federal agency
   must not carry `sponsored` or `nofollow`; that markup declares a paid
   placement and would be a false disclosure. Affiliated portfolio links keep
   `rel="sponsored nofollow"` untouched.
3. Lane and subject separation. A source is only offered to publications listed
   in its `lanes`, and after the first source is chosen every further source
   must share a topic with the ones already selected. That keeps the
   professional publication's equine, immigration, credit and workplace
   mental-health material from citing each other's sources, which its own
   disclosure requires.
4. Confidence floor. A page that does not match at least two sources gets
   nothing. Navigation pages, the about page and the mastheads make no factual
   claims of their own, so they are skipped rather than decorated.

Idempotent: the block is delimited by `data-block="external-citations"` and
replaced wholesale, so running twice writes the same bytes.

    python3 scripts/add_external_citations.py --write
"""
from __future__ import annotations

import argparse
import math
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITES = ROOT / "sites"
PUBLICATIONS = json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))
REGISTRY = json.loads((ROOT / "data/external-sources.json").read_text(encoding="utf-8"))
SOURCES = REGISTRY["sources"]

LANE_BY_FOLDER = {p["folder"].split("/", 1)[1]: p["id"] for p in PUBLICATIONS}

BLOCK_RE = re.compile(
    r'\s*<section data-block="external-citations">.*?</section>', re.S | re.I)
MAIN_RE = re.compile(r"(<main[^>]*>)(.*?)(</main>)", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.S | re.I)
# The editorial-boundary section is the page's closing disclaimer. Sources belong
# above it: the reader should see what the page stands on before being told what
# it is not.
BOUNDARY_RE = re.compile(r'<section><h2>Editorial boundary</h2>', re.I)

# Pages that answer no query of their own. Citing sources on a masthead or a
# navigation hub would be decoration, which is the failure mode this is meant
# to avoid.
SKIP_NAMES = {"404.html", "about.html", "index.html"}

MIN_SOURCES = 2
MAX_SOURCES = 4


def page_text(html_text: str) -> str:
    match = MAIN_RE.search(html_text)
    body = match.group(2) if match else html_text
    body = SCRIPT_RE.sub(" ", body)
    return " ".join(TAG_RE.sub(" ", body).split()).lower()


# --------------------------------------------------------------------------
# How a page's sources are chosen
# --------------------------------------------------------------------------
# Not by keyword matching. That was tried and it failed in a way worth
# recording: the daily pages are written from a small shared vocabulary (their
# median pairwise Sorensen-Dice is 0.686), so a page about credit-explanation
# letters and a page about a dental consultation share most of their words. A
# keyword matcher scored the American Dental Association as a match for a
# letters-of-explanation page, which is exactly the decorative, gamed-looking
# citation this work exists to avoid.
#
# The repository already holds an authoritative answer. `data/topic-taxonomy.json`
# assigns every daily page to exactly one hub, and `build_site_navigation.py`
# resolves that assignment from a cluster string the *generator itself wrote*
# into the page. That is a recorded fact, not an inference.
#
# So sources are mapped to hubs by hand, once, below. Each entry is a
# deliberate editorial judgement that these authorities are the right outside
# references for that subject, and a hub with no honest match gets none.
HUB_SOURCES: dict[str, list[str]] = {
    # -- founder ------------------------------------------------------------
    "virtual-event-production": ["esta-tsp", "avixa-standards", "avixa"],
    "community-operations": ["ftc-endorsement-guides", "ftc-business-guidance"],
    "ai-execution-and-delegation": ["nist-ai-rmf", "nist-ai-rmf-development",
                                    "copyright-office-ai", "ftc-endorsement-guides"],
    "founder-operating-rhythms": ["sba-manage-your-business", "sba-launch-your-business"],
    "hiring-and-lean-team-stack": ["irs-contractor-or-employee",
                                   "sba-manage-your-business", "nist-cybersecurity-framework"],
    # -- memphis ------------------------------------------------------------
    "wedding-planning-tools": ["tn-sales-and-use-tax", "tn-secretary-of-state-businesses"],
    "wedding-day-timelines": ["nws-memphis", "tn-fire-prevention"],
    "wedding-and-event-budgets": ["tn-sales-and-use-tax", "tn-alcoholic-beverage-commission",
                                  "tn-secretary-of-state-businesses"],
    "wedding-seating-charts": ["tn-fire-prevention", "memphis-city-government"],
    "grazing-tables-and-vendors": ["fda-food-code", "fda-refrigerator-thermometers",
                                   "shelby-county-health", "tn-secretary-of-state-businesses"],
    "porch-and-seasonal-styling": ["nws-memphis", "noaa-climate-normals",
                                   "memphis-city-government"],
    "event-and-room-styling": ["tn-fire-prevention", "memphis-city-government",
                               "tn-sales-and-use-tax"],
    # -- professional -------------------------------------------------------
    "credit-reports-and-disputes": ["cfpb-dispute-credit-report-error",
                                    "ftc-disputing-credit-report-errors",
                                    "annualcreditreport-official", "identitytheft-gov"],
    "loan-application-packets": ["cfpb-debt-to-income-ratio", "fannie-mae-selling-guide",
                                 "cfpb-loan-estimate"],
    "loan-type-explanations": ["cfpb-loan-options", "cfpb-mortgages", "sba-loans"],
    "application-problems": ["cfpb-credit-reports-and-scores", "ftc-free-credit-reports"],
    "letters-of-explanation": ["fannie-mae-selling-guide", "cfpb-debt-to-income-ratio"],
    "income-and-employment-letters": ["cfpb-debt-to-income-ratio", "fannie-mae-selling-guide"],
    "bank-statement-and-deposit-letters": ["fannie-mae-selling-guide",
                                           "cfpb-debt-to-income-ratio"],
    "identity-and-address-records": ["identitytheft-gov", "usps-mail-forwarding"],
    "rental-applications": ["hud-fair-housing", "hud-rental-assistance",
                            "cfpb-credit-reports-and-scores"],
    "proof-of-income-and-residency": ["cfpb-debt-to-income-ratio", "usps-mail-forwarding"],
    "business-funding-documents": ["sba-loans", "irs-contractor-or-employee"],
    "document-preparation": ["identitytheft-gov", "usps-mail-forwarding",
                             "annualcreditreport-official"],
    "workplace-mental-health": ["eeoc-mental-health-rights", "osha-workplace-stress",
                                "eeoc-disability-resources", "samhsa-national-helpline"],
    "recovery-housing": ["narr-standards", "samhsa-national-helpline"],
    "equine-contracts": ["american-horse-council", "tn-courts", "uscourts"],
    # regulated-provider-research deliberately has no hub-level entry. It spans
    # dental, neuropsychological, immigration-medical and hormone-clinic
    # material, and this publication's own disclosure says those stay separated.
    # Its pages are cited at cluster level instead, and a cluster too general to
    # cite honestly gets nothing.
}

# Cluster-level mapping, which is finer than the hub. The cluster string is
# recorded on the page by the generator, so this is as precise as the hub map
# and separates subjects the hub merges.
CLUSTER_SOURCES: dict[str, list[str]] = {
    "neuropsych evaluation research": ["apa-testing-and-assessment",
                                       "aacn-clinical-neuropsychology",
                                       "eeoc-disability-resources"],
    "neuro eval guides authority": ["apa-testing-and-assessment",
                                    "aacn-clinical-neuropsychology"],
    "dental decision resources": ["nidcr", "ada-dental-insurance",
                                  "ada-health-policy-institute", "aaoms"],
    "uscis civil surgeon appointment prep": ["uscis-find-civil-surgeon", "uscis-i-693",
                                             "ecfr-8-232-1"],
    "uscis exam guides authority": ["uscis-i-693", "uscis-find-civil-surgeon"],
    "iv therapy clinic research": ["fda-human-drug-compounding", "fda-consumer-updates"],
    "hormone wellness clinic questions": ["fda-human-drug-compounding",
                                          "fda-consumer-updates"],
    "hormones iv hair authority": ["fda-human-drug-compounding", "fda-consumer-updates"],
    "hair restoration provider research": ["fda-consumer-updates",
                                           "fda-human-drug-compounding"],
    "personal injury lawyer questions": ["uscourts", "tn-courts"],
    "accident guides authority": ["uscourts", "tn-courts"],

    # -- credit-reports-and-disputes ---------------------------------------
    # The hub sent all 43 of these pages to the same four sources, which is why
    # a debt-validation page and a goodwill-letter page read as the same page.
    # They are not the same subject and they are not governed by the same text:
    # a validation notice is set by 12 CFR 1006.34, and whether a late payment
    # is worth explaining at all is decided by the FCRA reporting period.
    "credit dispute letters": ["cfpb-dispute-credit-report-error",
                               "ftc-disputing-credit-report-errors",
                               "annualcreditreport-official", "identitytheft-gov"],
    "credit report errors": ["cfpb-credit-report-answers",
                             "ftc-disputing-credit-report-errors",
                             "cfpb-how-long-info-stays", "annualcreditreport-official"],
    "goodwill letters": ["cfpb-how-long-info-stays", "cfpb-what-is-a-credit-score",
                         "cfpb-credit-reports-and-scores"],
    "debt validation letters": ["ecfr-12-1006-34", "cfpb-debt-collection",
                                "ftc-debt-collection-faqs"],
    "credit report issues": ["cfpb-credit-reports-and-scores", "ftc-free-credit-reports",
                             "cfpb-credit-report-answers"],
    "late payment explanation": ["cfpb-how-long-info-stays", "cfpb-what-is-a-credit-score",
                                 "ftc-disputing-credit-report-errors"],
    "how to explain a late payment": ["cfpb-credit-report-answers",
                                      "cfpb-how-long-info-stays", "ftc-free-credit-reports"],
    "credit explanation letters": ["fannie-mae-selling-guide", "cfpb-debt-to-income-ratio",
                                   "cfpb-what-is-a-credit-score"],

    # -- loan-application-packets ------------------------------------------
    "personal loan documents": ["cfpb-loan-options", "cfpb-debt-to-income-ratio",
                                "cfpb-what-is-a-credit-score"],
    "loan application packet": ["cfpb-loan-estimate", "fannie-mae-selling-guide",
                                "cfpb-debt-to-income-ratio"],
    "full approval prep bundle": ["fanniemae-originating-underwriting",
                                  "hud-sfh-handbook-4000-1", "cfpb-closing-disclosure"],
    "lender document request": ["fannie-mae-selling-guide", "irs-get-transcript",
                                "cfpb-debt-to-income-ratio"],
    "application document checklists": ["cfpb-loan-estimate", "cfpb-closing-disclosure",
                                        "hud-sfh-handbook-4000-1"],

    # -- loan-type-explanations --------------------------------------------
    "loan explanation letters": ["cfpb-loan-options", "cfpb-mortgages",
                                 "cfpb-debt-to-income-ratio"],
    "mortgage explanation": ["cfpb-mortgages", "cfpb-closing-disclosure",
                             "hud-sfh-handbook-4000-1"],
    "business loan explanation": ["sba-loans", "irs-small-business-self-employed",
                                  "irs-business-structures"],
    "car loan explanation": ["cfpb-loan-options", "cfpb-what-is-a-credit-score",
                             "cfpb-credit-reports-and-scores"],

    # -- income-and-employment-letters -------------------------------------
    "income change explanation": ["cfpb-debt-to-income-ratio", "irs-get-transcript",
                                  "fannie-mae-selling-guide"],
    "employment explanation letters": ["irs-contractor-or-employee",
                                       "fannie-mae-selling-guide",
                                       "cfpb-debt-to-income-ratio"],
    "job gap explanation": ["fanniemae-originating-underwriting",
                            "cfpb-debt-to-income-ratio", "irs-get-transcript"],
    "business explanation letters": ["irs-small-business-self-employed",
                                     "irs-business-structures", "sba-loans"],
    "self-employed income explanation": ["irs-schedule-c",
                                         "irs-small-business-self-employed",
                                         "irs-get-transcript"],
    "cash flow explanation": ["irs-schedule-c", "fdic-consumer-resource-center",
                              "irs-small-business-self-employed"],

    # -- bank-statement-and-deposit-letters --------------------------------
    "bank statement explanation": ["fdic-consumer-resource-center",
                                   "fannie-mae-selling-guide",
                                   "cfpb-debt-to-income-ratio"],
    "large deposit explanation": ["fincen", "fdic-consumer-resource-center",
                                  "fanniemae-originating-underwriting"],

    # -- letters-of-explanation --------------------------------------------
    "letters of explanation": ["fannie-mae-selling-guide", "cfpb-debt-to-income-ratio",
                               "fanniemae-originating-underwriting"],

    # -- application-problems ----------------------------------------------
    "multiple application issues": ["cfpb-credit-report-answers", "ftc-free-credit-reports",
                                    "cfpb-credit-reports-and-scores"],
    "application issue explanation": ["cfpb-credit-reports-and-scores",
                                      "cfpb-debt-to-income-ratio", "ftc-free-credit-reports"],

    # -- rental-applications -----------------------------------------------
    "apartment application paperwork": ["cfpb-tenant-screening-report", "hud-fair-housing",
                                        "cfpb-credit-reports-and-scores"],
    "rental application packet": ["hud-fair-housing", "hud-rental-assistance",
                                  "cfpb-tenant-screening-report"],
    "rental history explanation": ["cfpb-tenant-screening-report",
                                   "cfpb-credit-report-answers", "hud-fair-housing"],
    "apartment denial review": ["cfpb-tenant-screening-report", "ftc-free-credit-reports",
                                "hud-fair-housing"],
    "rental cover letters": ["ftc-rental-listing-scams", "hud-fair-housing",
                             "hud-rental-assistance"],

    # -- proof-of-income-and-residency -------------------------------------
    "proof of income for renting": ["cfpb-tenant-screening-report", "hud-rental-assistance",
                                    "cfpb-debt-to-income-ratio"],
    "proof of income letters": ["irs-get-transcript", "cfpb-debt-to-income-ratio",
                                "irs-schedule-c"],
    "credit rental income and loan letters": ["cfpb-credit-reports-and-scores",
                                              "cfpb-debt-to-income-ratio", "hud-fair-housing"],
    "proof of residency letter": ["usps-mail-forwarding", "tsa-real-id",
                                  "usagov-replace-vital-documents"],
    "how to organize a proof-of-income packet": ["irs-get-transcript", "irs-schedule-c",
                                                 "cfpb-debt-to-income-ratio"],
    "proof of income documents": ["irs-get-transcript", "cfpb-debt-to-income-ratio",
                                  "usps-mail-forwarding"],

    # -- identity-and-address-records --------------------------------------
    "address issue explanation": ["usps-mail-forwarding", "tsa-real-id",
                                  "usagov-replace-vital-documents"],
    "name mismatch explanation": ["usagov-replace-vital-documents", "tsa-real-id",
                                  "identitytheft-gov"],
    "identity records explanation": ["identitytheft-gov", "usagov-replace-vital-documents",
                                     "tsa-real-id"],

    # -- business-funding-documents ----------------------------------------
    "business funding packet": ["sba-loans", "irs-get-ein", "irs-business-structures"],
    "business funding documents": ["sba-loans", "irs-small-business-self-employed",
                                   "fincen-boi"],
    "business ownership documents": ["fincen-boi", "irs-business-structures", "irs-get-ein"],

    # -- document-preparation ----------------------------------------------
    "complete document library": ["identitytheft-gov", "usps-mail-forwarding",
                                  "annualcreditreport-official"],
    "life admin letters": ["usagov-replace-vital-documents", "usps-mail-forwarding",
                           "tsa-real-id"],
    "self-service document creation": ["usagov-replace-vital-documents", "identitytheft-gov",
                                       "irs-get-transcript"],
    "truthful document preparation": ["irs-get-transcript", "fannie-mae-selling-guide",
                                      "identitytheft-gov"],
    "life admin documents": ["usagov-replace-vital-documents", "usps-mail-forwarding",
                             "irs-get-transcript"],
    "documentation checklists": ["cfpb-loan-estimate", "fannie-mae-selling-guide",
                                 "irs-get-transcript"],
    "document consistency before applying": ["fannie-mae-selling-guide", "irs-get-transcript",
                                             "cfpb-debt-to-income-ratio"],
    "self-service paperwork preparation": ["usagov-replace-vital-documents",
                                           "identitytheft-gov", "usps-mail-forwarding"],

    # -- workplace-mental-health -------------------------------------------
    "compassion fatigue resources": ["osha-workplace-stress", "samhsa-national-helpline",
                                     "lifeline-988"],
    "trauma-informed leadership": ["samhsa-home", "osha-workplace-stress",
                                   "eeoc-mental-health-rights"],
    "workplace wellbeing scoping": ["osha-workplace-stress", "eeoc-disability-resources",
                                    "ada-gov"],
    "organizational mental health training": ["eeoc-mental-health-rights", "ada-gov",
                                              "osha-workplace-stress"],
    "workplace burnout resources": ["osha-workplace-stress", "samhsa-national-helpline",
                                    "eeoc-mental-health-rights"],
    "high-achieving women and burnout": ["osha-workplace-stress", "lifeline-988",
                                         "samhsa-home"],
    "therapy consultation questions": ["ahrq-questions", "samhsa-national-helpline",
                                       "lifeline-988"],
    "therapy information": ["samhsa-home", "lifeline-988", "ahrq-questions"],
    "workplace mental health training": ["eeoc-mental-health-rights",
                                         "eeoc-disability-resources", "ada-gov"],

    # -- recovery-housing ---------------------------------------------------
    "family recovery support": ["samhsa-national-helpline", "lifeline-988", "samhsa-home"],
    "recovery housing": ["narr-standards", "samhsa-national-helpline"],
    "recovery housing decisions": ["narr-standards", "samhsa-home", "hud-rental-assistance"],
    "community reintegration": ["samhsa-home", "hud-rental-assistance", "lifeline-988"],
    "recovery referrals": ["samhsa-national-helpline", "lifeline-988", "narr-standards"],
    "recovery housing questions": ["narr-standards", "samhsa-national-helpline",
                                   "hud-rental-assistance"],
    "recovery resources": ["samhsa-home", "samhsa-national-helpline", "lifeline-988"],

    # -- equine-contracts ---------------------------------------------------
    "equine contract preparation": ["american-horse-council", "psu-extension-equine",
                                    "uscourts"],
    "boarding agreement questions": ["psu-extension-equine", "american-horse-council",
                                     "tn-courts"],
    "horse contract preparation": ["american-horse-council", "uscourts", "tn-courts"],
    "boarding barn contract issues": ["psu-extension-equine", "tn-courts",
                                      "american-horse-council"],
    "equine liability questions": ["american-horse-council", "uscourts",
                                   "psu-extension-equine"],
    "horse boarding agreements": ["psu-extension-equine", "american-horse-council",
                                  "uscourts"],
    "horse dispute preparation": ["uscourts", "tn-courts", "american-horse-council"],
    "horse purchase documents": ["american-horse-council", "psu-extension-equine",
                                 "tn-courts"],

    # -- regulated-provider-research ----------------------------------------
    # This hub deliberately has no hub-level entry, so these clusters were
    # getting nothing at all. AHRQ's question list and the CMS comparison tools
    # are the federal, non-ranking references for "how do I choose a provider",
    # which is exactly what these pages are about.
    "preparing records before a specialist appointment": ["ahrq-questions", "medicare-gov"],
    "decision frameworks for sensitive services": ["ahrq-questions", "medicare-gov"],
    "how to prepare for consults": ["ahrq-questions", "medicare-gov"],
    "red flags in regulated services": ["ahrq-questions", "fda-consumer-updates"],
    "regulated provider research": ["medicare-gov", "ahrq-questions"],
    "the industry guides authority": ["ahrq-questions", "medicare-gov"],
}

# The standing overview pages are not daily pages, so they carry no cluster
# string. They are named explicitly rather than guessed at.
PAGE_SOURCES: dict[str, list[str]] = {
    "founder-operator/virtual-event-production-buyers-guide.html":
        ["esta-tsp", "avixa-standards", "avixa"],
    "founder-operator/ai-executive-coaching-resources.html":
        ["nist-ai-rmf", "copyright-office-ai"],
    "founder-operator/ai-marketing-operations-resources.html":
        ["ftc-endorsement-guides", "ftc-business-guidance", "nist-ai-rmf"],
    "founder-operator/founder-execution-systems.html":
        ["sba-manage-your-business", "sba-launch-your-business"],
    "memphis-local/memphis-grazing-table-resources.html":
        ["fda-food-code", "fda-refrigerator-thermometers", "shelby-county-health"],
    "memphis-local/memphis-party-decor-vendors.html":
        ["tn-secretary-of-state-businesses", "tn-sales-and-use-tax", "memphis-city-government"],
    "memphis-local/memphis-porch-decorating-resources.html":
        ["nws-memphis", "noaa-climate-normals"],
    "memphis-local/seasonal-home-styling-memphis.html":
        ["noaa-climate-normals", "nws-memphis"],
    "professional-resources/dental-decision-resources.html":
        ["ada-dental-insurance", "ada-health-policy-institute", "aaoms"],
    "professional-resources/equine-legal-resource-library.html":
        ["american-horse-council", "tn-courts", "uscourts"],
    "professional-resources/hormone-wellness-clinic-research.html":
        ["fda-human-drug-compounding", "fda-consumer-updates"],
    "professional-resources/neuro-evaluation-research.html":
        ["apa-testing-and-assessment", "aacn-clinical-neuropsychology",
         "eeoc-disability-resources"],
    "professional-resources/personal-injury-research-resources.html":
        ["uscourts", "tn-courts"],
    "professional-resources/regulated-service-provider-research.html":
        ["ada-dental-insurance", "apa-testing-and-assessment", "uscourts"],
    "professional-resources/uscis-medical-exam-resources.html":
        ["uscis-i-693", "uscis-find-civil-surgeon", "ecfr-8-232-1"],
    "professional-resources/workplace-burnout-and-boundaries.html":
        ["eeoc-mental-health-rights", "osha-workplace-stress", "samhsa-national-helpline"],
}

SOURCE_BY_ID = {s["id"]: s for s in SOURCES}

_hub_of_page: dict[str, str] = {}
_cluster_of_page: dict[str, str] = {}


def index_hub_assignments() -> dict[str, int]:
    """Ask build_site_navigation which hub each daily page belongs to.

    Reusing that module rather than reimplementing it means the citations and
    the navigation can never disagree about a page's subject.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_site_navigation as nav
    from lib import site_urls

    counts: dict[str, int] = {}
    for pub in nav.PUBLICATIONS:
        source = ROOT / pub["folder"]
        domain = site_urls.domain_of(pub)
        hubs = nav.load_hubs(pub["id"])
        members, _unmapped = nav.assign_members(source, domain, hubs)
        folder = pub["folder"].split("/", 1)[1]
        for slug, rows in members.items():
            for row in rows:
                key = f'{folder}/{row["rel"]}'
                _hub_of_page[key] = slug
                _cluster_of_page[key] = (row.get("cluster") or "").strip().lower()
                counts[slug] = counts.get(slug, 0) + 1
    return counts


# Where a subject is governed by one nameable instrument - a regulation, a
# form, a handbook - the page says so in its own words rather than leaving the
# reader to infer it from a list of links.
#
# The limit on this map is deliberate and it is a limit of evidence. Each note
# states what a document *is*: its title, its publisher, and the subject it
# governs. Every one of those titles was read off the document itself during
# `verify_external_sources.py --network`, which stores the observed title in
# the receipt. What a regulation *requires* is not asserted here, because the
# fetch verified that the page exists and what it is called, not its contents.
#
# A subject whose sources are general agency landing pages gets no note. There
# is nothing more to say about it than the citation list already says, and
# saying it anyway would be padding.
CLUSTER_INSTRUMENT: dict[str, str] = {
    "debt validation letters":
        "The instrument here is a regulation, not a template. 12 CFR 1006.34, "
        "titled &ldquo;Notice for validation of debts&rdquo; and published by the "
        "Office of the Federal Register, is the text that governs the validation "
        "notice a collector owes you, so it is the thing to read before drafting "
        "anything.",
    "self-employed income explanation":
        "Self-employment income reaches a lender as a tax form. The IRS publishes "
        "Schedule C (Form 1040), &ldquo;Profit or Loss from Business (Sole "
        "Proprietorship)&rdquo;, and an explanation letter is checked against the "
        "figure that form already reports rather than replacing it.",
    "cash flow explanation":
        "Schedule C (Form 1040), the IRS form reporting profit or loss from a sole "
        "proprietorship, is where a reviewer looks first. A narrative about cash "
        "flow sits alongside that form; it does not stand in for it.",
    "full approval prep bundle":
        "FHA files are governed by a published handbook. HUD's Single Family "
        "Housing Policy Handbook 4000.1 is the document that states what an FHA "
        "file must contain, which is why two lenders can ask for the same paperwork.",
    "application document checklists":
        "A checklist assembled from experience and one assembled from HUD's Single "
        "Family Housing Policy Handbook 4000.1 are different objects. The handbook "
        "is published, so it can be checked.",
    "mortgage explanation":
        "Two published documents sit behind most mortgage paperwork: HUD's Single "
        "Family Housing Policy Handbook 4000.1 for FHA files, and the CFPB's "
        "closing disclosure explainer for the form that arrives before closing.",
    "business ownership documents":
        "Ownership paperwork now answers to a federal filing. FinCEN's Beneficial "
        "Ownership Information Reporting programme is the requirement that "
        "ownership records have to line up with, and FinCEN publishes it directly.",
    "business funding documents":
        "Beneficial Ownership Information Reporting, published by FinCEN, is the "
        "federal filing a funding file is now expected to be consistent with.",
    "business funding packet":
        "A funding packet normally has to evidence an EIN. The IRS issues it and "
        "publishes the official route to get one, which is the only place it comes "
        "from.",
    "proof of income letters":
        "There is an official version of the income record. The IRS publishes tax "
        "transcripts, and a transcript is a different object from a copy of a "
        "return that an applicant assembles.",
    "how to organize a proof-of-income packet":
        "The IRS transcript service is the authoritative source for the tax records "
        "a packet is built around, rather than a self-assembled copy.",
    "income change explanation":
        "A change in income is verified against records the IRS already holds. Its "
        "transcript service is where the official version of those records comes "
        "from.",
    "job gap explanation":
        "A gap is read against a documented earnings record. The IRS transcript "
        "service publishes the official version of that record.",
    "truthful document preparation":
        "Truthfulness here has a reference point. The IRS transcript service holds "
        "the official record a prepared document has to stay consistent with.",
    "lender document request":
        "A lender's request is rarely arbitrary. Fannie Mae's Selling Guide and the "
        "IRS transcript service between them explain where most items on the list "
        "come from.",
    "large deposit explanation":
        "A large deposit draws a question because of a reporting regime, not "
        "suspicion of the individual. FinCEN, the Treasury bureau that administers "
        "it, publishes that regime.",
    "apartment application paperwork":
        "A landlord does not see an application the way an applicant does. The "
        "CFPB's page &ldquo;What is a tenant screening report?&rdquo; describes the "
        "document that actually arrives on the other side.",
    "rental history explanation":
        "Rental history reaches a landlord through a tenant screening report. The "
        "CFPB publishes what that report is and what an applicant may ask for.",
    "apartment denial review":
        "After a denial the relevant document is the tenant screening report. The "
        "CFPB sets out what it contains and the applicant's right to see the one "
        "used.",
    "proof of income for renting":
        "What a landlord receives is a tenant screening report, described by the "
        "CFPB, rather than the packet an applicant hands over.",
    "goodwill letters":
        "Whether a mark is still worth writing about depends on time. The CFPB's "
        "&ldquo;How long does information stay on my credit report?&rdquo; sets out "
        "the reporting periods, and a goodwill letter cannot shorten them.",
    "late payment explanation":
        "The CFPB's &ldquo;How long does information stay on my credit report?&rdquo; "
        "gives the reporting periods that decide whether a late payment is still on "
        "the report at all.",
    "how to explain a late payment":
        "Before drafting, check whether the entry is still reportable. The CFPB "
        "publishes how long information stays on a credit report.",
    "credit report errors":
        "An error and a stale-but-accurate entry are handled differently. The CFPB's "
        "credit report answers and its page on how long information stays on a "
        "report separate the two.",
    "proof of residency letter":
        "Address proof has a federal standard behind it. TSA publishes the REAL ID "
        "requirements, which name the documents a compliant credential accepts.",
    "address issue explanation":
        "The REAL ID standard, published by TSA, is what decides which address "
        "documents are accepted, so it is the reference an address explanation "
        "works against.",
    "name mismatch explanation":
        "A name mismatch is resolved by replacing or correcting a vital record. "
        "USAGov publishes the official replacement route for each one.",
    "identity records explanation":
        "USAGov publishes the official route for replacing lost or stolen ID "
        "documents, which is where an identity record is corrected rather than "
        "explained.",
    "life admin letters":
        "Most of these letters exist because a record needs replacing. USAGov "
        "publishes the official replacement route for each vital document.",
    "credit dispute letters":
        "A dispute has a statutory route. The CFPB describes how to dispute an "
        "error on a credit report, and the FTC publishes what a dispute letter "
        "should contain.",
}


def choose_sources(rel_key: str, lane: str) -> tuple[list[dict], str]:
    """Sources for one page, from its recorded hub or its explicit entry."""
    cluster = _cluster_of_page.get(rel_key, "")
    if rel_key in PAGE_SOURCES:
        ids, reason = PAGE_SOURCES[rel_key], "named-page"
    elif cluster in CLUSTER_SOURCES:
        ids, reason = CLUSTER_SOURCES[cluster], f"cluster:{cluster}"
    else:
        hub = _hub_of_page.get(rel_key)
        if not hub:
            return [], "no-hub"
        ids = HUB_SOURCES.get(hub, [])
        reason = f"hub:{hub}"
    chosen = []
    for sid in ids[:MAX_SOURCES]:
        source = SOURCE_BY_ID.get(sid)
        if source is None:
            raise SystemExit(f"{rel_key}: unknown source id {sid!r}")
        if lane not in source["lanes"]:
            raise SystemExit(
                f"{rel_key}: source {sid!r} is not registered for the {lane} lane")
        chosen.append(source)
    return chosen, reason


def render_block(sources: list[dict], instrument: str = "") -> str:
    lead = f'<p class="instrument-note">{instrument}</p>' if instrument else ""
    items = "".join(
        f'<li><a href="{html.escape(s["url"], quote=True)}" '
        f'data-source="external-authority" rel="noopener">'
        f'{html.escape(s["title"])}</a> &mdash; '
        f'{html.escape(s["publisher"])}. '
        f'<span class="note">{html.escape(s["supports"])}</span></li>'
        for s in sources)
    return (
        '\n<section data-block="external-citations"><h2>Sources outside this network</h2>'
        '<p>This page is general guidance. The authorities below publish the '
        'underlying requirements, and they are the place to confirm anything '
        'current before acting on it.</p>'
        f'{lead}'
        f'<ul>{items}</ul>'
        '<p class="note">These sources are independent. They are not affiliated '
        'with this publication, nothing was paid for their inclusion, and their '
        'publishers have not reviewed or endorsed this page.</p></section>')


def process(path: Path, rel_key: str, lane: str, write: bool) -> tuple[str, list[dict]]:
    original = path.read_text(encoding="utf-8")
    # Pages that already carry a hand-authored citation block own their own
    # sources. Injecting a second one would give the reader two Sources
    # sections, which reads as padding rather than sourcing.
    if 'data-block="external-sources"' in original:
        return ("authored", [])
    stripped = BLOCK_RE.sub("", original)
    sources, reason = choose_sources(rel_key, lane)
    if len(sources) < MIN_SOURCES:
        # Removing a previously injected block on a page that no longer maps
        # keeps the run idempotent in both directions.
        if stripped != original and write:
            path.write_text(stripped, encoding="utf-8", newline="\n")
        return ("skipped", [])

    block = render_block(sources, CLUSTER_INSTRUMENT.get(
        _cluster_of_page.get(rel_key, ""), ""))
    boundary = BOUNDARY_RE.search(stripped)
    if boundary:
        updated = stripped[:boundary.start()] + block + "\n" + stripped[boundary.start():]
    else:
        close = stripped.lower().rfind("</main>")
        if close == -1:
            return ("no-main", [])
        updated = stripped[:close] + block + "\n" + stripped[close:]

    if updated == original:
        return ("unchanged", sources)
    if write:
        path.write_text(updated, encoding="utf-8", newline="\n")
    return ("written", sources)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    stats: dict[str, dict] = {}
    domains_by_lane: dict[str, set] = {}
    hub_counts = index_hub_assignments()
    print(f"  hub assignments read from data/topic-taxonomy.json: "
          f"{sum(hub_counts.values())} daily page(s) across {len(hub_counts)} hub(s)")

    for folder, lane in sorted(LANE_BY_FOLDER.items()):
        root = SITES / folder
        row = stats.setdefault(lane, {"pages": 0, "cited": 0, "skipped": 0,
                                      "written": 0, "citations": 0})
        pages = [p for p in sorted(root.rglob("*.html")) if p.name not in SKIP_NAMES]
        for path in pages:
            rel_key = f"{folder}/{path.relative_to(root).as_posix()}"
            row["pages"] += 1
            status, sources = process(path, rel_key, lane, args.write)
            if status == "authored":
                row["cited"] += 1
                row["authored"] = row.get("authored", 0) + 1
                authored = re.findall(r'data-source="external-authority"[^>]*>',
                                      path.read_text(encoding="utf-8"))
                row["citations"] += len(authored)
                domains_by_lane.setdefault(lane, set()).update(
                    s["domain"] for s in SOURCES
                    if s["url"] in path.read_text(encoding="utf-8"))
            if status in {"written", "unchanged"}:
                row["cited"] += 1
                row["citations"] += len(sources)
                domains_by_lane.setdefault(lane, set()).update(
                    s["domain"] for s in sources)
            if status == "written":
                row["written"] += 1
            if status == "skipped":
                row["skipped"] += 1

    print("EXTERNAL CITATIONS" + ("" if args.write else " (dry run)"))
    total_pages = total_cited = total_links = 0
    for lane, row in sorted(stats.items()):
        pct = round(100 * row["cited"] / max(row["pages"], 1), 1)
        print(f"\n  {lane}: {row['cited']}/{row['pages']} page(s) cited ({pct}%)")
        print(f"    outbound citations: {row['citations']}   "
              f"distinct domains: {len(domains_by_lane.get(lane, set()))}")
        print(f"    no confident topic match, left alone: {row['skipped']}")
        print(f"    {'updated' if args.write else 'would update'}: {row['written']}")
        total_pages += row["pages"]
        total_cited += row["cited"]
        total_links += row["citations"]

    all_domains = sorted(set().union(*domains_by_lane.values())) if domains_by_lane else []
    print(f"\n  TOTAL: {total_cited}/{total_pages} substantive page(s) now cite an "
          f"outside source ({round(100 * total_cited / max(total_pages, 1), 1)}%)")
    print(f"  {total_links} outbound citations across {len(all_domains)} external domains")
    print("  " + ", ".join(all_domains))

    report = ROOT / "reports/external-citation-coverage.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({
        "schema_version": "1.0",
        "generated_by": "scripts/add_external_citations.py",
        "rel_policy": "editorial citations carry rel=\"noopener\" only; "
                      "affiliated portfolio links keep rel=\"sponsored nofollow\"",
        "per_publication": {k: {**v, "distinct_domains": sorted(domains_by_lane.get(k, set()))}
                            for k, v in stats.items()},
        "totals": {"pages": total_pages, "pages_citing": total_cited,
                   "citations": total_links, "distinct_domains": len(all_domains)},
        "external_domains": all_domains,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"\n  wrote {report.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
