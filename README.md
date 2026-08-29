# Authority Network v4.5

Authority Network is a multi-publication content and backlink-governance system. It creates useful resource pages, routes only approved contextual links, prepares social posts, and records evidence for every generated or published action.

## Start here

- Editorial independence, contact setup and the contributor system: [`docs/EDITORIAL-INDEPENDENCE.md`](docs/EDITORIAL-INDEPENDENCE.md)
- Plan for earning citations from parties the owner does not control: [`docs/EXTERNAL-AUTHORITY-PLAN.md`](docs/EXTERNAL-AUTHORITY-PLAN.md)

- Plain-English system guide: [`docs/WHAT-THIS-SYSTEM-IS.md`](docs/WHAT-THIS-SYSTEM-IS.md)
- Day-0 VA/operator guide: [`docs/DAY-0-VA-OPERATOR-GUIDE.md`](docs/DAY-0-VA-OPERATOR-GUIDE.md)
- Validation/cache explanation: [`docs/VALIDATION-CACHE-PLAIN-ENGLISH.md`](docs/VALIDATION-CACHE-PLAIN-ENGLISH.md)
- Technical validation architecture: [`docs/VALIDATION-ARCHITECTURE-V4-5.md`](docs/VALIDATION-ARCHITECTURE-V4-5.md)
- Dream Wedding Builder and City Vendor architecture: [`docs/DREAM-WEDDING-BUILDER-AND-CITY-VENDOR.md`](docs/DREAM-WEDDING-BUILDER-AND-CITY-VENDOR.md)

## Core commands

```bash
npm run validate:changed
npm run validate:release
npm run validate:full
npm run validate:clean-rebuild
npm run validate:cache:self-test
```

Only real integrity, safety, routing, secret, deterministic-build, or required-journey failures block a release. Word counts and similar editorial targets are warnings. Generated daily pages may receive one safe mechanical repair pass.

---

# Real Authority Network — BACKLINKS - Targeted SEO/AEO/GEO Engine

This repo is built only for the domains the owner listed. It is not a generic backlink scaffold.

## New authority publication domains assumed

1. `founderoperatorlibrary.com` — supports A Player Mode, Billionaire High Performance Coach, Virtual Agency OS, West Peek Productions.
2. `memphisvendorlibrary.com` — supports Porch & Party.
3. `professionalresourcelibrary.com` — supports The Industry Guides + five canonical guide sites, Horse Legal Guide, and Hicks Consulting in separated sections.

You can rename these in `data/publications.json` before deployment.

## Target domains programmed

The targets are locked in `data/brands.json` and `data/link-registry.json`:

- theindustryguides.com
- theaccidentguides.com
- dentistryguides.com
- hormonesivhair.com
- neuroevalguides.com
- uscisexam.com
- billionairehighperformancecoach.com
- aplayermode.com
- virtualagency-os.com
- westpeekproductions.com
- horselegalguide.com
- hicksconsulting.org
- porchandparty901.com

No other backlink/citation target is configured.

## Critical link rules

- The Industry Guides may route to the five canonical domains.
- Canonical guide sites must not link back to The Industry Guides.
- The founder publication can only cite the founder/operator targets.
- The Memphis publication can only cite Porch & Party from this network.
- The professional publication can only cite regulated/professional targets.
- No fake rankings, fake reviews, fake independence, comment spam, PBNs, or doorway pages.

## How to use

Run local review:

```bash
npm run check
```

Generate social drafts:

```bash
npm run social:drafts
```

Deploy through GitHub Actions after adding Cloudflare secrets:

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`

Each site is static and can be deployed to Cloudflare Pages for $0.

## Folder map

- `sites/founder-operator` — Founder/Operator publication
- `sites/memphis-local` — Memphis local vendor publication
- `sites/professional-resources` — Professional resource publication
- `data/brands.json` — locked target domain registry
- `data/link-registry.json` — approved target URL + anchor registry
- `data/network-rules.json` — hostile review and publishing policy
- `scripts/hostile_review.py` — blocks bad links/claims/wrong publication routing
- `.github/workflows/*` — review, draft generation, deploy workflows

## Current status

This zip includes real starter pages, schemas, sitemaps, llms.txt files, registries, review scripts, and deployment workflows. It is still intentionally conservative: automated generation creates drafts and PRs; risky content and social posting require review.

## Final hostile review status

This reviewed zip includes `docs/FINAL-HOSTILE-REVIEW-MANIFEST.md` plus current reports in `reports/`.

Run:

```bash
npm run check
```

Current expected status: PASS with zero link violations and zero hostile-review warnings.

## V4.2 Social Auto-Posting

This baseline includes hands-off social auto-posting for one LinkedIn account and one X account. See:

- `docs/SOCIAL-AUTOPOST-SECRETS.md`
- `docs/AUTOPOST-END-TO-END-TRACE.md`
- `docs/V4-2-END-TO-END-HOSTILE-REVIEW.md`

Cloudflare deploy remains handled by Cloudflare Git integration. GitHub Actions generates pages, validates them, queues social posts, auto-posts eligible items, commits ledgers/reports, and lets Cloudflare deploy site changes.


## Approval Prep target

Approval Prep (`approvalprep.com`) is a high-priority Professional Resource Library target. The autopilot aims for roughly 5–8 Approval Prep pages per day from launch, with normal daily variation and tolerant editorial review. The 90-day north star is 100,000 honest citation surfaces and impressions—not 100,000 claimed independent backlinks.

## Approval Prep product-routing rule

Approval Prep is a document-creation business, not primarily a checklist site. Authority pages must identify the reader's real document problem and route to the matching paid kit, free Letter Writing Studio, educational guide, or boundary page. The core positioning is: **Create the letter. Build the packet. Get ready before you apply.**


## Dream Wedding Builder + City Vendor
The network supports one multi-domain Dream Wedding Builder brand and a reusable City Vendor publication family. Memphis Vendor Library and Porch & Party remain intact. See `docs/DREAM-WEDDING-BUILDER-AND-CITY-VENDOR.md`.


## Portfolio citation control plane (v4.6)

This repository coordinates verified authority backlinks across the full brand portfolio while each product repository may continue producing its own owned content surfaces. The six-month objective is 100,000 combined citation/impression opportunities—not 100,000 fabricated backlinks.

Use `npm run citation:dashboard` for the portfolio report, `npm run citation:verify-repo` to verify repository-rendered backlink evidence, and `npm run citation:import-manifests` to import configured product-repo surface manifests. Growth targets guide scheduling but do not create petty release blockers.

## Portfolio Backlink Autopilot (v5.0)

Authority Network now governs 15 portfolio backlink campaigns across all modernized product repos. It preserves the three existing publication properties and adds:

- SHA-traceable product destination snapshots;
- Community-as-a-Service authority and WPP commercial campaign separation;
- SEO/AEO/GEO seed-page quality contracts;
- contextual gap and yield scheduling;
- safe local self-healing;
- successful-publish-gated IndexNow and Google Search Console distribution;
- priority URL Inspection;
- live deployed backlink verification;
- durable provider and observation receipts;
- truthful rendered/deployed/live/indexed/cited lifecycle states.

Start with [`docs/runbooks/AUTHORITY_NETWORK_BACKLINK_AUTOPILOT.md`](docs/runbooks/AUTHORITY_NETWORK_BACKLINK_AUTOPILOT.md).

Core commands:

```bash
npm run backlinks:seed
npm run backlinks:repair
npm run backlinks:verify
npm run backlinks:health
npm run distribution:prepare-indexnow
npm run distribution:run
npm run validate:release
```

Cloudflare deployment remains handled by Cloudflare Git integration. The post-publish distribution workflow runs only after successful Authority Network publication, plus manual and scheduled retry paths.

## Measurement tools, and why they are not validators

Three tools measure whether these publications can earn citations, and none of
them blocks anything:

```bash
npm run measure:internal-reachability   # rebuild the link graph from rendered HTML
npm run measure:crawler-access          # live probe: can GPTBot et al. fetch these pages
npm run measure:citation-shape          # shape gap against 46 external agent runs
npm run measure:citation-all            # all three, in that order
```

They produce numbers a person reads, in `reports/citation-measurement/`. That is
the whole job. This repository has a standing rule that a measurement is not a
mandate: `scripts/measure_content_duplication.py` was added with the note "this
commit measures it rather than fixing it", because the remedy there is editorial
and "rewriting the prose of thousands of live pages automatically would risk
manufacturing substance that is not there". The same reasoning holds for these
three, and 00a657e kept them on exactly that ground after they refuted the
"377 orphans" claim the portfolio was reasoning from.

Not blocking is not the same as not reachable. Each one now has a named entry
point, and `scripts/validators/validate_script_callers.py` fails the release if
any tracked script under `scripts/` loses its last caller — so a measurement
tool cannot quietly become an orphan again, and cannot rot unnoticed while it
sits there. `measure_internal_reachability.py` had already done both: it read
`sites/` from an absolute path outside the checkout and wrote its result into a
scratch directory belonging to a session that no longer existed.

Repair tools, likewise reachable and likewise manual:

```bash
npm run links:backfill-rel                       # add a missing rel="sponsored nofollow"
npm run pages:debloat                            # dry run; :write to apply
npm run pages:retrofit-recommendation-summary -- --apply
npm run pages:backfill-missed-days               # operator recovery for skipped publish days
npm run analytics:install-clarity
npm run cadence:reseed-lastmod
```
