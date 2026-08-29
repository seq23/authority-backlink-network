# V4.3.3 GitHub Actions Data Trace

Status: STRUCTURAL PASS

## Scope

This trace validates the workflow wiring shipped in the baseline artifact. It does not call live GitHub APIs from the artifact container.

## Workflows traced

1. `.github/workflows/authority-v4-autopilot.yml`
2. `.github/workflows/social-autopost.yml`
3. `.github/workflows/hostile-review.yml`

## Fixes included

- Added shared social concurrency group to autopilot and social-only workflows.
- Verified autopilot runs generation, hostile review, link audit, social publisher, commit, and failure issue creation.
- Verified social-only workflow runs social publisher, commits ledger, and creates failure issue.
- Verified hostile-review workflow runs hostile review and link audit.
- Verified no workflow performs direct Cloudflare deployment.
- Verified all required LinkedIn/X secret references are present.

## Remaining live setup

Add GitHub Actions secrets and variables, then run workflows manually once.

Required live secrets:

- `LINKEDIN_ACCESS_TOKEN`
- `LINKEDIN_AUTHOR_URN`
- `X_API_KEY`
- `X_API_SECRET`
- `X_ACCESS_TOKEN`
- `X_ACCESS_TOKEN_SECRET`

Recommended variables:

- `ENABLE_LINKEDIN_POSTING=true`
- `ENABLE_X_POSTING=true`
- `REQUIRE_SOCIAL_SECRETS=true`
- `FAIL_ON_SOCIAL_POST_FAILURE=false`
- `SOCIAL_DRY_RUN=false`
- `LINKEDIN_DAILY_LIMIT=3`
- `X_DAILY_LIMIT=8`
- `MAX_SOCIAL_SIMILARITY=0.86`
- `DAILY_PAGE_LIMIT=3`
- `ABSOLUTE_MAX_PAGES_PER_DAY=9`

## Live verification command after push

```bash
gh run list --repo seq23/authority-network --limit 10
```

Expected live result after secrets are installed:

- Hostile Review: success
- Authority Network V4.2 Autopilot + Social Auto-Post: success
- Social Auto-Post Only: success or queued behind shared concurrency if overlapping

