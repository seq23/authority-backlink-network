# Earning citations from people Sequoia does not own

**Status:** plan, not yet executed. Nothing in here has been done.
**Budget assumed:** $0 for tooling. Owner time is the scarce resource.
**Measured:** 2026-08-27, on `work/editorial-independence` at `main`.

---

## 1. The diagnosis, measured

I counted every absolute anchor in `sites/`:

| | count |
|---|---|
| Absolute `http(s)` anchors across 608 pages | 21,055 |
| → to affiliated brand domains | 571 |
| → of those, carrying `rel="sponsored nofollow"` | **571 (all of them)** |
| → to the publications' own domains (internal) | 20,484 |
| → **to any domain outside the portfolio** | **0** |

Two facts follow, and they point in opposite directions.

**The disclosure is correct.** All 571 affiliated links are labelled and carry
`sponsored nofollow`. That is the honest configuration and it must stay. It also
means those 571 links pass no ranking equity — by design. The network's
enormous internal link graph (20,484 anchors) does nothing for external
authority either, because internal links cannot manufacture it.

**The citation graph is a closed loop.** The network cites 0 domains it does not
own. Every outbound editorial gesture points either at itself or at its owner's
other properties. That is the single strongest signal that this is a link
surface rather than a publication — stronger than the affiliation, stronger than
the templating, and stronger than the missing bylines. A real publication cites
outsiders constantly, because reality contains outsiders.

**So the only lever that can move external authority is inbound citations from
parties the owner does not control.** Everything below is about that.

> **Do not confuse this with outbound sourcing.** A concurrent workstream is
> adding verified external sources to pages (`data/external-sources.json`). That
> is correct and improves accuracy — but citing outward earns nothing inbound.
> The two efforts are complements, not substitutes. This document is only about
> the inbound direction.

### One expectation to set now

Realistic outcome of executing this plan well for twelve months is roughly
**10–30 genuine external citations**, not hundreds. Anything promising hundreds
is selling something. Ten citations from real publications are worth more than a
thousand from anywhere they can be bought, and — unlike the purchasable kind —
they do not become a liability later.

---

## 2. How these are ranked

Ranked by **citations earned ÷ (owner hours + dollars)**, with a confidence
mark, because a high ratio on a play that probably will not work is worth less
than a solid ratio on one that will.

Cost figures are the owner's own time at the effort actually required, not a
best case. Dollar figures are $0 unless stated. Where a price could not be
verified it says so rather than guessing.

---

## 3. The ranked plays

### Rank 1 — Journalist source platforms
**Effort:** ~5 h/month, ongoing · **Cost:** $0 · **Confidence:** high
**Expected:** 1–3 placements/month once the rhythm is established

The best ratio available, by a wide margin, and the only play that produces
citations from established publications at zero cost. A reporter needs a source;
you are a source; the resulting article names and links you.

**This only works because Sequoia is genuinely an expert.** She runs virtual and
hybrid event production, operations for small teams, and a Memphis event
business. Those are real, answerable beats. Pitches must go out **in her own
name**, not from a publication persona — a fabricated expert is the one thing
that turns this from an asset into a catastrophe.

Verified free-to-source platforms (checked 2026-08-27; status quoted, not assumed):

| Platform | URL | Free tier for a source | Note |
|---|---|---|---|
| **Source of Sources (SOS)** | sourceofsources.com | Yes — *"This list doesn't cost a dime."* | Peter Shankman's post-HARO project. Up to 3 query emails/day. Asks for charity donations, not fees. **Start here.** |
| **HARO** (now run by Featured) | helpareporter.com | Believed yes — could not verify | See the correction below. Featured's own tiers are Free $0 / Lite $29 / Pro $79. Confirm in a browser before relying on it. |
| **Featured.com** | featured.com | Yes — *"$0 Free forever"* | Now owns and operates HARO. |
| **SourceBottle** | sourcebottle.com | Yes — *"Put your wallets away! You can now create your Expert Profile for free!"* | Optional paid pitch upsell. |
| **Qwoted** | qwoted.com | Yes — Basic, free | 2 pitches/month, and responses are held on a **2-hour delay** vs. paid. The delay is the real cost. |
| **#JournoRequest** | Bluesky | Free | Verified active with posts dated 2026-08-27. **Skews heavily UK** — weak for a Memphis vendor beat, useful for the operations beat. |

**Correction to a common assumption:** HARO is *not* dead. Cision discontinued
Connectively (formerly HARO) on 9 Dec 2024, then sold HARO to Featured.com in
April 2025, which relaunched it on 22 Apr 2025. Any plan that describes HARO as
shut down is out of date.

**Do not list these** — verified as unusable:
- **Help a B2B Writer** — gone. Redirects to MentionMatch, which is pre-launch.
- **Muck Rack** — free tier is for *journalists only*. No free path in as a source.
- **ResponseSource** — £625 per category per year. No free source tier, UK-focused.

**How to actually do it:** subscribe to SOS and Featured. Budget 20 minutes each
morning to scan. Answer only queries where you have first-hand knowledge — a
2-in-10 hit rate on 5 good answers beats a 0-in-50 rate on generic ones. Lead
with the specific claim, keep it under 200 words, and say plainly who you are
and what you own. Disclosure here is an advantage: reporters are wary of
undisclosed commercial sources.

---

### Rank 2 — Original Memphis vendor cost data
**Effort:** 25–35 h for the first edition, then ~10 h/year · **Cost:** $0
**Confidence:** high · **Expected:** 5–15 citations per edition, compounding

The single highest-value asset any of these three publications could publish,
and the reason is structural: **"what does X cost in city Y" is the shape of
question journalists must answer and cannot answer without a source.** Nobody
publishes rigorous Memphis-specific event pricing. The national wedding sites
publish national averages and city multipliers, which are not the same thing and
are visibly not the same thing.

**Phase 1 — desk-researched, no respondents needed (20 h).** Collect *published*
pricing from Memphis-area vendors: photographers, caterers, florists, venues,
rentals, DJs. Many publish price sheets or starting rates. Record vendor,
category, what the price includes, and the date observed. This requires no one
to answer an email, which is why it works.

**Phase 2 — a real survey (adds 15–20 h, lower confidence).** Ask vendors for
ranges directly. Harder: it needs a list and goodwill. Do this only after Phase 1
has published and the publication has something to show. Vendors respond to a
publication that already exists.

**Publish it properly, or it earns nothing:**
- State the sample size, the collection window, and the method, at the top.
- Say what the data does *not* cover.
- Publish the underlying table on the page, and offer a CSV.
- Give it a stable URL and a year in the title, so the next edition is a new
  citable artifact rather than an overwrite.
- Name a real person as the author. The byline infrastructure is now built.
- Update it annually. A dataset in its third edition is cited far more than a
  first edition, because it becomes the series people reference.

**Who cites it:** local TV and press, Memphis Business Journal, national wedding
media doing city roundups, other vendors, and — increasingly — AI answer engines,
which the repo is already configured to welcome.

**The honest risk:** it is real work, and a thin version is worse than nothing.
Twelve vendors with a stated method beats sixty with a hand-wave, but six is not
a dataset.

---

### Rank 3 — Recruit Memphis vendors as named contributors
**Effort:** ~3 h per contributor · **Cost:** $0 · **Confidence:** medium-high
**Expected:** 1–2 inbound links each, plus durable credibility

The byline system shipped empty and ready (`data/contributors.json`,
`/contributors`, author pages, `Person` schema with `sameAs`). Memphis event
vendors are the natural first pool: a photographer, a planner, a caterer. Each
gets a byline, an author page, and a link to a profile they control. They link
back from their own site and social because it is a credential.

This is a fair trade and it is not a link scheme: the contributor writes real
material under their real name, and the link exists because they wrote it.

A ready-to-send recruitment brief is in
[`EDITORIAL-INDEPENDENCE.md`](EDITORIAL-INDEPENDENCE.md#contributor-recruitment-brief).

**Hard rule:** never add anyone to `data/contributors.json` who has not actually
agreed and actually written something. The file's own header says this at
length. A fabricated contributor destroys every other item in this document.

---

### Rank 4 — A regulated-change changelog on Professional Resource Library
**Effort:** 12–15 h setup, then ~1 h/week · **Cost:** $0 · **Confidence:** medium
**Expected:** slow start, strong compounding

USCIS, state boards and courts publish requirements; none of them publish a
readable, dated record of *what changed and when*. That changelog is genuinely
original work built entirely on primary sources, and it is exactly what a
journalist or a practitioner cites when they need to say "this changed in March".

Pick one narrow lane and hold it — immigration form and fee changes is the
strongest candidate. Each entry: date observed, what changed, the primary source,
and what it means for someone mid-process.

**Handle with care.** This is YMYL material. Every entry must cite the issuing
agency directly, carry the date it was checked, and keep the advice boundary the
publication already enforces. A stale page here is a harmful page, which is why
the weekly hour is not optional. If that hour will not happen reliably, do not
start this play.

---

### Rank 5 — A published-pricing index for Founder Operator Library
**Effort:** ~20 h · **Cost:** $0 · **Confidence:** medium
**Expected:** 2–5 citations

Same mechanism as Rank 2, weaker market. Virtual event production and community
platform pricing is poorly documented and buyers search for it constantly.
Collect *published* pricing across vendors in one category and publish the
comparison with method and date.

Ranked below Memphis because the audience is national and therefore competitive,
and because FOL has no list to survey. It is a desk-research play only.

---

### Rank 6 — Association memberships and local directories
**Effort:** low hours · **Cost:** $500 – $25,000+ · **Confidence:** medium
**Expected:** a handful of directory listings, mostly `nofollow`

Verified as currently operating (2026-08-27):

| Organisation | URL | Public member directory | Cost |
|---|---|---|---|
| Greater Memphis Chamber | memphischamber.com | Yes | **$500** (ACCESS) → $1,000 → $2,500 → $5,000 → $10,000 → $25,000+ |
| ILEA | ileahub.com | Yes — "FIND A MEMBER" | Not published |
| NACE | nace.net | Yes | Not published |
| Association of Bridal Consultants | abcweddingplanners.com | Yes | Not published |
| WIPA | wipa.org | Could not confirm public | Not published |

Note ABC moved: `bridalassn.com` now redirects to `abcweddingplanners.com`.

**Ranked last deliberately.** These cost dollars rather than hours, and a
directory listing is a weak citation — usually `nofollow`, rarely editorial.
**Join these if they are worth it for the business** (referrals, relationships,
the Memphis room). Do not join them for links; the ratio is poor.

**Could not verify:** whether Memphis Business Journal accepts contributed
columns. Their site blocks automated fetching. Worth ten minutes in a browser —
but note that *Business Journals Leadership Trust* is a **paid membership**, not
earned editorial, and would not count as an independent citation.

---

## 4. What not to do, and why each one fails

**Link exchanges.** "I'll link you if you link me." Reciprocal patterns are
trivially detectable and are explicitly named in Google's link spam policy. In
this portfolio's case it is worse than usual: everything already traces to one
owner, so a reciprocal arrangement adds a second detectable pattern on top of a
first.

**Paid links.** Direct violation of search engine guidelines, and the repo's own
`README.md` forbids it in as many words. A paid link that is disclosed passes no
equity; one that is not is a policy violation. There is no version that works.

**PBNs.** This is the one that matters, because it is the failure mode this
network is closest to. A private blog network is a set of sites, commonly owned,
existing to link to the owner's money sites. The three publications are commonly
owned and do link to the owner's commercial properties. **The things that make
them not a PBN are: the affiliation is disclosed, the links are
`sponsored nofollow`, and the pages are genuinely useful.** All three must hold.
The moment any is dropped — an undisclosed owner, a followed affiliated link, a
page that exists only to carry one — the network becomes the thing the README
forbids.

**Guest posting at scale.** Google's site reputation abuse policy now targets
this directly. A guest post on a site that publishes anything is worth nothing.
One genuine contributed piece to a publication that actually edits is worth a
great deal — but that is Rank 1, done properly, not this.

**Syndication and spun content.** Republishing the same article across sites
creates duplicate content and earns no citation, because nobody cites a copy.

**Comment and forum links.** Forbidden by the README, universally `nofollow`,
and reputationally negative.

**Buying "DA 50+ backlink packages."** These are fabricated metrics sold against
a third-party score that no search engine uses. It is fraud with a dashboard.

**Publishing more pages faster.** Worth naming because it is the tempting one and
the infrastructure makes it easy. The network has 608 pages and 0 external
citations. Page 609 does not change that. Volume is not the constraint.

---

## 5. Sequencing — the first 90 days

The ordering matters more than the list, because Rank 2 is much easier to land
once Rank 1 has produced something and the governance pages exist.

**Days 1–7 — clear the prerequisites (about 4 h).**
Everything here is already built and needs the owner's hands only:
1. Set up email routing so `editor@` and `corrections@` actually receive mail —
   steps in [`EDITORIAL-INDEPENDENCE.md`](EDITORIAL-INDEPENDENCE.md#2-the-contact-surface).
   **A corrections address that bounces is worse than none.** Nothing else in
   this plan should start until this is done.
2. Confirm the three analytics projects are recording (they are separate
   already — see the same doc).

**Days 8–30 — start Rank 1 (about 5 h).**
Subscribe to Source of Sources and Featured. Scan daily. Answer only what you
genuinely know. Expect nothing in month one; the rhythm is the point.

**Days 15–60 — build Rank 2 (about 25 h).**
Phase 1 of the Memphis pricing data. Desk research only. Publish with method,
sample size, date and a real byline.

**Days 60–90 — Rank 3, and pitch Rank 2 (about 10 h).**
Approach three Memphis vendors as contributors using the brief. Send the pricing
data to local press and to the wedding publications that run city cost pieces —
a dataset with a stated method is a story, and it is the thing they cannot get
elsewhere.

**Deliberately not in the first 90 days:** Ranks 4, 5 and 6. Rank 4 needs a
weekly commitment that should not be made until the others are habitual; Rank 5
duplicates Rank 2's method with a weaker return; Rank 6 costs money and should be
a business decision, not a link decision.

---

## 6. How to know whether it worked

Track the one number that matters and ignore the vanity ones.

**The number:** count of distinct domains, not owned by Sequoia, that link to any
of the three publications. It is 0 today. Check it quarterly.

A useful second measure, since this network is explicitly built for AI answer
engines: whether the original data gets quoted in AI answers to questions like
"what does a wedding photographer cost in Memphis". The repo already has an
`llm_citation_probe.mjs` and a signals ledger for this.

**Ignore:** domain authority scores, total backlink counts (which will include
the network citing itself), and page counts.

**The honest failure condition:** if after twelve months of Rank 1 and Rank 2 the
count of unowned linking domains is still 0, the problem is not the tactics — it
is that the publications are not yet producing anything a stranger would want to
cite. The answer then is more original data, not more pages and not more links.

---

## Appendix — verification notes

Every service named in this document was checked on **2026-08-27** by fetching
its live pages. Status quotes are verbatim. Specifically:

- **Verified operating with a free source tier:** Source of Sources, Featured.com,
  SourceBottle, Qwoted (Basic).
- **Verified operating, no free source tier:** ResponseSource (£625/category/yr),
  Muck Rack (free tier is journalists-only).
- **Verified gone — must not be recommended:** Help a B2B Writer (redirects to
  MentionMatch, pre-launch).
- **Verified active:** `#JournoRequest` on Bluesky, posts dated 2026-08-27.
- **Verified operating:** Greater Memphis Chamber (tiers as listed), ILEA, NACE,
  ABC (new domain), WIPA.
- **Could not verify — do not assert:** HARO's current source-side free tier
  (helpareporter.com and connectively.us both return HTTP 429 to automated
  requests); whether Memphis Business Journal accepts contributed columns
  (bizjournals.com blocks fetching); membership pricing for ILEA, NACE, ABC and
  WIPA (none publish it).

Public data sources for original research, verified live the same day:
[data.gov](https://data.gov) (554,493 datasets), the
[BLS public API](https://api.bls.gov/publicAPI/v2/) (returned live data through
July 2026 — note October 2025 is missing due to an appropriations lapse, so a
gap in a time series is real, not an error), and the Census ACS API, which **now
requires a free API key** — request one before building anything on it.
