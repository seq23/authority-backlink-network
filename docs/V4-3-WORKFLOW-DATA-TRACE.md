# V4.3 GitHub Actions Data Trace

## Workflow 1: Hostile Review

File: `.github/workflows/hostile-review.yml`

Triggers:

- `push` to `main`
- `pull_request`

Inputs:

- Repository files
- `data/brands.json`
- `data/publications.json`
- `data/network-rules.json`
- `data/social-queue.json`
- HTML files under `sites/`

Steps:

1. Checkout repo
2. Setup Python 3.11
3. Run `python3 scripts/hostile_review.py`
4. Run `python3 scripts/link_audit.py`
5. Upload `reports/` artifact

Outputs:

- `reports/hostile-review-report.json`
- `reports/link-audit.json`
- GitHub Actions artifact: `authority-network-review-reports`

Failure conditions:

- unknown brand/publication ids
- unauthorized outbound domains
- target domain linked from wrong publication lane
- missing affiliation disclosure
- missing professional/YMYL disclaimer
- banned phrase or unsafe claim
- duplicate social body
- unsupported social status

## Workflow 2: Authority Network V4.2 Autopilot + Social Auto-Post

File: `.github/workflows/authority-v4-autopilot.yml`

Triggers:

- manual `workflow_dispatch`
- daily schedule at `22 14 * * *` UTC

Inputs:

Variables:

- `DAILY_PAGE_LIMIT`
- `ABSOLUTE_MAX_PAGES_PER_DAY`
- `MIN_BASE_PUBLISH_SCORE`
- `ENABLE_GEMINI_REWRITE`
- `GEMINI_MODEL`
- `LINKEDIN_DAILY_LIMIT`
- `X_DAILY_LIMIT`
- `FOUNDER_PUBLICATION_DOMAIN`
- `MEMPHIS_PUBLICATION_DOMAIN`
- `PROFESSIONAL_PUBLICATION_DOMAIN`
- `ENABLE_LINKEDIN_POSTING`
- `ENABLE_X_POSTING`
- `REQUIRE_SOCIAL_SECRETS`
- `FAIL_ON_SOCIAL_POST_FAILURE`
- `SOCIAL_DRY_RUN`
- `MAX_SOCIAL_SIMILARITY`
- `LINKEDIN_VERSION`

Secrets:

- `GEMINI_API_KEY` optional
- `LINKEDIN_ACCESS_TOKEN` required for live LinkedIn posting
- `LINKEDIN_AUTHOR_URN` required for live LinkedIn posting
- `X_API_KEY` required for live X posting
- `X_API_SECRET` required for live X posting
- `X_ACCESS_TOKEN` required for live X posting
- `X_ACCESS_TOKEN_SECRET` required for live X posting

Step data trace:

1. `authority_v4_autopilot.py`
   - Reads: `content-bank/yearly-pantry.json`, `content-bank/scaling-policy.json`, `data/autopilot-state.json`, prompts, site folders
   - Writes: new HTML pages under `sites/*/daily/`, `sitemap.xml`, `llms.txt`, `data/autopilot-state.json`, `data/link-registry.json`, `data/social-queue.json`, `reports/v4-autopilot-report.json`

2. `hostile_review.py`
   - Reads generated site files and registries
   - Writes `reports/hostile-review-report.json`
   - Fails if content/link/compliance gates fail

3. `link_audit.py`
   - Reads site HTML and registries
   - Writes `reports/link-audit.json`
   - Fails if outbound links violate allowed lanes

4. `social_publisher.py`
   - Reads `data/social-queue.json`
   - Posts up to daily caps if enabled and not dry-run
   - Writes updated `data/social-queue.json` and `reports/social-publisher-report.json`
   - Counts prior `posted_at` entries from the same day before posting, preventing double-posting across workflows

5. Auto-commit
   - Commits `sites/**`, `data/**`, and `reports/**`
   - Cloudflare Git integration deploys after commit

6. Failure issue
   - Opens GitHub issue if workflow fails

## Workflow 3: Social Auto-Post Only

File: `.github/workflows/social-autopost.yml`

Triggers:

- manual `workflow_dispatch`
- daily schedule at `17 16 * * *` UTC

Inputs:

Same social variables/secrets as the social step in autopilot.

Step data trace:

1. Checkout repo
2. Setup Python 3.11
3. Run `social_publisher.py`
   - Reads `data/social-queue.json`
   - Counts already-posted same-day items
   - Posts only if daily caps are not already reached
   - Writes updated queue and report
4. Auto-commit social ledger
5. Open issue on failure

## Anti-Double-Posting Rule

The social publisher enforces daily caps globally by counting `posted_at` entries already present in `data/social-queue.json` for the current date. This means autopilot and social-only workflows can both exist without exceeding daily caps.

## Cloudflare Trace

There are no Cloudflare deploy workflows in this repo. Cloudflare deploys independently through Git integration after GitHub commits new files to `main`.
