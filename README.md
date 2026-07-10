# Real Authority Network — BACKLINKS - Targeted SEO/AEO/GEO Engine

This repo is built only for the domains Sequoia Taylor listed. It is not a generic backlink scaffold.

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
