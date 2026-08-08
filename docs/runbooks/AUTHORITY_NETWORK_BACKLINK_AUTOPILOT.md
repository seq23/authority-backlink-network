# Authority Network Backlink Autopilot Runbook

Status: ACTIVE
Runtime model: FULL SAFE AUTONOMY for routine safe work
Scope: Authority Network publications only; product repositories remain read-only destinations

## 1. Operating chain

```text
successful Authority Network publish
-> refresh sitemap and llms.txt
-> validate SEO/AEO/GEO and backlink context
-> self-repair safe local defects
-> Cloudflare Git deployment
-> bounded deployment-settle window
-> IndexNow notification
-> GSC sitemap submission
-> priority URL Inspection
-> fetch deployed source page
-> verify target URL, anchor, canonical/indexability
-> durable receipt
-> observation and campaign-yield feedback
```

The system never treats a rendered link as live, a submitted URL as indexed, an indexed page as ranking, an affiliated link as independent, or any of those states as a verified citation.

## 2. Portfolio coverage

The canonical campaign registry is `data/portfolio-backlink-campaigns.json`.
The SHA-traceable destination inventory is `data/product-repo-manifests.json`.
The current rendered coverage report is `data/portfolio-campaign-health.json`.

Governed campaigns cover:

- The Industry Guides and all five Listings guide brands
- Virtual Agency OS as a separate education brand
- West Peek Productions Community as a Service and commercial services
- Billionaire High Performance Coach
- ApprovalPrep
- Dream Wedding Builder
- Porch & Party
- Hicks Consulting
- Horse Legal Guide
- Dianne's Place Recovery Services

Community as a Service backlink routing is locked:

- every West Peek Productions Community as a Service backlink targets `www.westpeekproductions.com`;
- Virtual Agency OS remains a separate education brand and may not receive links assigned to a West Peek Productions campaign.

## 3. GitHub configuration

### Repository variable: `INDEXNOW_KEY`

Use an 8-128 character public IndexNow verification key. This is a public verification token, not a private credential. The autopilot writes `<key>.txt` into each publication root before commit so the deployed property can verify the submission.

### Repository secret: `GSC_SERVICE_ACCOUNT_JSON`

Use the full Google service-account JSON. Grant the service account access to all three Search Console properties.

### Repository variable: `GSC_SITE_URLS_JSON`

Example:

```json
{
  "founder": "sc-domain:founderoperatorlibrary.com",
  "memphis": "sc-domain:memphisvendorlibrary.com",
  "professional": "sc-domain:professionalresourcelibrary.com"
}
```

### Optional variables

- `AUTHORITY_PUBLICATION_BASE_URLS_JSON`: override deployed origins when they differ from `data/publications.json`.
- `INDEXNOW_KEY_LOCATION_TEMPLATE`: default `https://{domain}/{key}.txt`.
- `GSC_INSPECTION_LIMIT`: default `20` per publication/run.
- `LIVE_BACKLINK_VERIFY`: default `true`.
- `DEPLOYMENT_SETTLE_SECONDS`: default `90`, maximum `900`.
- `FAIL_ON_PROVIDER_ERROR`: default `false`; failures remain visible and retry automatically without falsely promoting evidence.

## 4. Workflows

### Authority Network V4.2 Autopilot + Social Auto-Post

Daily generation, campaign selection, safe local backlink repair, release validation, social automation, and commit.

### Authority Network Post-Publish Distribution

Runs automatically only when the Authority autopilot completes successfully. It also supports manual dispatch and a daily retry. It checks out the latest `main`, validates the release, runs provider distribution, verifies live links, persists receipts, and commits observation evidence.

Cloudflare deployment remains owned by Cloudflare Git integration. GitHub Actions does not perform direct Cloudflare deployment.


## 4.1 Social failure isolation

Social distribution is subordinate to content and backlink publication. Missing LinkedIn/X credentials and provider posting failures are recorded in the social report but do not block generated content, backlink validation, the commit step, or post-publish distribution when `FAIL_ON_SOCIAL_POST_FAILURE=false` (the normal production setting). The autopilot workflow also marks the social step `continue-on-error` so an unexpected social-process exit cannot strand otherwise-valid generated content.

Strict social failure is opt-in only: set `FAIL_ON_SOCIAL_POST_FAILURE=true` when the owner intentionally wants social delivery to become release-blocking.

The owner backlink/operator view is regenerated at `founderoperatorlibrary.com/agency/` after autopilot and after post-publish distribution so evidence status stays aligned with the canonical link ledger.

## 5. Safe self-healing

Automatic repairs are limited to deterministic safe defects:

- missing approved target link;
- missing approved anchor;
- missing affiliation disclosure;
- regenerated canonical/meta/schema for seed pages;
- sitemap and `llms.txt` omissions;
- campaign coverage undercount caused by stale ledgers;
- provider retry after transient failure;
- live verification retry after deployment delay.

The system skips and records rather than inventing:

- unsupported facts or claims;
- unrelated source topics;
- fake reviews, awards, rankings, or independent coverage;
- new publication domains;
- fake provider success, indexing, citations, or LLM surfacing.

## 6. Evidence states

```text
approved_destination
-> published_in_repository
-> deployed
-> live_verified
-> source_discovered
-> source_indexed
-> search_visibility_observed
-> external_surfacing_observed
```

Evidence is stored in:

- `data/link-registry.json`
- `data/distribution/provider-receipt.json`
- `data/distribution/receipts/`
- `data/distribution/observation-feedback.json`
- `data/portfolio-campaign-health.json`
- `reports/citation-portfolio-dashboard.json`

## 7. Normal operation

No routine human action is required after variables/secrets and Cloudflare Git deployments are configured.

Owner involvement is required only for:

- provider credential authorization;
- DNS or publication deployment failure;
- legal/commercial policy changes;
- new domains or new portfolio brands;
- destructive architecture changes;
- unrecoverable provider/repository corruption.

## 8. Validation

```bash
python3 scripts/portfolio_backlink_engine.py seed
python3 scripts/portfolio_backlink_engine.py repair
python3 scripts/portfolio_backlink_engine.py verify-local
python3 scripts/portfolio_backlink_engine.py health
npm run validate:release
```

Provider/live proof is only complete after deployed domains and production credentials are configured. Local and mocked provider validation proves the implementation path, not production provider state.
