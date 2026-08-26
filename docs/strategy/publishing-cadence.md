# Publishing cadence policy

## Why this document exists

The cadence was set from research and then never revisited against outcomes.
Search Console now works, so the temptation is to retune it from telemetry. That
would be wrong right now, for two reasons worth stating before any numbers.

**The 90-day window is contaminated.** Until 2026-08-26, every unknown URL on
thirteen domains returned HTTP 200 with a copy of the homepage, sitemaps were
never submitted to Search Console, three sitemaps were addressed to a host
literally named `None`, and tens of thousands of internal links resolved through
redirects. Surfacing measured under those conditions says the site was hard to
crawl. It says nothing about whether the publishing rate is right.

**Age was mistaken for failure.** A first pass found "94% of pages earn nothing"
and would have cut cadence on it. Segmenting by age corrected that: pages older
than 90 days surface at 20.2%, pages newer than 90 days at 0.1%. Most of the
corpus was simply young.

So the cadence numbers are not being changed on telemetry. What follows is
changed on research, which does not depend on a clean crawl.

## What the research says

1. **Past ~50 published pages, improving existing pages beats adding new ones.**
   Every property here is 10-50x past that threshold: sprylabs 2,812 pages,
   local-guides 2,326, WPP-llm 3,192.

2. **Volume carries site-wide risk, not just wasted effort.** Google's helpful
   content system evaluates a site holistically, so a large body of thin or
   duplicative pages can suppress the ranking of the whole domain. Publishing
   500 pages of which 200 are thin can cost visibility on the other 300.

3. **For AI answers, depth beats breadth.** A focused site that dominates a
   narrow topic cluster earns citations against larger competitors, and smaller
   sites have the advantage because depth in one niche is easier to build than
   coverage across many.

4. **The citation lift is measurable and it is not volume.** Adding quotations
   from credible sources raises a source's share of an AI answer by about 41%,
   statistics by about 31%, citations by about 28%. Tables are extracted more
   reliably than prose. 55% of AI Overview citations come from the first 30% of
   the cited page.

5. **Zero is also wrong.** Sites that stop publishing keep climbing for a while
   on compounding, then plateau and decline. Freshness still matters for crawl
   scheduling.

## Policy

**Keep publishing, change the mix.** The lane's daily budget stays; what it
spends the budget on changes.

- **Enrichment is the default work.** Each cycle improves existing pages against
  the four elements with measured citation lift - named sources, concrete
  numbers, comparison tables, FAQ blocks - prioritising pages that already
  surface in Search Console, because lifting a page that ranks 11th is worth
  more than a new page that ranks nowhere.
- **New pages continue, but must clear demand evidence.** A new page requires a
  measured (T1) query. That gate already exists; it was starved because nothing
  wrote T1 evidence until Search Console was connected.
- **Volume holds only on clean evidence.** `scripts/cadence/publish_headroom.mjs`
  refuses to hold publishing using data from before 2026-08-26 and requires 60
  days of post-fix data before it will gate anything. Until then the declared
  cadence stands.

## What would change this

Two clean 30-day windows after 2026-08-26. If pages surfacing per month rises
while volume is flat, the enrichment shift is working. If surfacing is flat
while the corpus grows, the headroom gate holds new volume automatically and
this document should be revisited with the numbers.

Reviewed: 2026-08-26.
