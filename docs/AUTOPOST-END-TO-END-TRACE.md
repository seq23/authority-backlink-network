# Auto-Post End-to-End Data Trace

## Workflow: Authority Network V4.2 Autopilot + Social Auto-Post

Trigger:
- Daily schedule: `22 14 * * *`
- Manual `workflow_dispatch`

Data path:

1. `.github/workflows/authority-v4-autopilot.yml`
2. `scripts/authority_v4_autopilot.py`
3. Reads:
   - `content-bank/yearly-pantry.json`
   - `content-bank/scaling-policy.json`
   - `content-recipes/*.json`
   - `data/autopilot-state.json` if present
4. Writes:
   - `sites/*/daily/*.html`
   - `sites/*/sitemap.xml`
   - `sites/*/llms.txt`
   - `data/link-registry.json`
   - `data/social-queue.json`
   - `data/autopilot-state.json`
   - `reports/v4-autopilot-report.json`
5. Runs hostile review:
   - `scripts/hostile_review.py`
   - writes `reports/hostile-review-report.json`
6. Runs link audit:
   - `scripts/link_audit.py`
   - writes `reports/link-audit.json`
7. Runs social publisher:
   - `scripts/social_publisher.py`
   - reads `data/social-queue.json`
   - posts items with status `queued_for_auto_post` or `approved_for_auto_post`
   - writes `data/social-queue.json`
   - writes `reports/social-publisher-report.json`
8. Commits:
   - `sites/**`
   - `data/**`
   - `reports/**`
9. Cloudflare Pages Git integration deploys the changed site folders.

## Workflow: Social Auto-Post Only

Trigger:
- Daily schedule: `17 16 * * *`
- Manual `workflow_dispatch`

Data path:

1. `.github/workflows/social-autopost.yml`
2. `scripts/social_publisher.py`
3. Reads `data/social-queue.json`
4. Posts queued items within daily limits
5. Writes `data/social-queue.json` and `reports/social-publisher-report.json`
6. Commits social ledger/report.

## Posting statuses

- `queued_for_auto_post`: eligible for automatic posting
- `approved_for_auto_post`: eligible for automatic posting
- `posted`: successfully posted
- `post_failed`: attempted but failed
- `skipped_duplicate`: blocked by similarity guard

## Limits

- LinkedIn: `LINKEDIN_DAILY_LIMIT`, default `1`
- X: `X_DAILY_LIMIT`, default `5`
- Same-day duplicate guard: `MAX_SOCIAL_SIMILARITY`, default `0.86`

## Failure behavior

- Missing secrets fail the workflow when `REQUIRE_SOCIAL_SECRETS=true`.
- API failures mark individual posts `post_failed`.
- If `FAIL_ON_SOCIAL_POST_FAILURE=false`, page publishing can still commit and Cloudflare deploys.
- If `FAIL_ON_SOCIAL_POST_FAILURE=true`, any social API failure fails the workflow.
