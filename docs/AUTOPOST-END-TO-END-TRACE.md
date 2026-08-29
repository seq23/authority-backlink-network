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
- `not_for_posting`: retired by an explicit decision, with the reason recorded on
  the entry in `retired_reason`. Written by `scripts/prioritize_social_queue.py`,
  never posted, never deleted.

## Limits

- LinkedIn: `LINKEDIN_DAILY_LIMIT`, default `3`
- X: `X_DAILY_LIMIT`, default `8`
- Per-run slice: `SOCIAL_RUN_LIMIT`, default `3`
- Spacing inside a run: `SOCIAL_POST_MIN_INTERVAL_SECONDS`, default `90`, jittered
  0.7x-1.6x
- Same-day duplicate guard: `MAX_SOCIAL_SIMILARITY`, default `0.86`

### Why these numbers

Two ceilings apply, and the lower one governs.

- **API-legal.** X free-tier write access is about 500 posts per month for the
  authenticated user, roughly 16/day averaged and shared across every workflow
  that posts. Nothing in this repository evidences a paid tier, so free tier is
  assumed until a credential or an invoice says otherwise.
- **Platform-safe.** A solo practitioner account posting dozens of link-bearing
  notes a day reads as automation to spam scoring regardless of what the API
  accepts. This account has no successful posting history at all, which makes a
  sudden high-volume start the worst possible profile.

8/day is about 240 posts a month: real throughput, roughly half the free-tier
allowance, and a volume a working practitioner could plausibly produce.

Volume is only half of it. Shape is the other half: the publisher used to emit
the whole day's allowance inside one loop, landing every post on effectively one
timestamp. `SOCIAL_RUN_LIMIT` plus four irregular crons plus jittered in-run
spacing turn the same daily total into scattered activity.

`scripts/validators/validate_social_rate_limits.py` holds these values to a band
in both directions, so a later edit can neither push them somewhere that risks
the account nor quietly restore a cap too low to drain.

## Failure behavior

- A platform missing its credentials is retired on its own. The other platform
  still posts. Only a run with no usable platform at all reports
  `blocked_missing_secrets`.
- Missing secrets fail the workflow when `REQUIRE_SOCIAL_SECRETS=true`.
- API failures mark individual posts `post_failed`.
- If `FAIL_ON_SOCIAL_POST_FAILURE=false`, page publishing can still commit and Cloudflare deploys.
- If `FAIL_ON_SOCIAL_POST_FAILURE=true`, any social API failure fails the workflow.
