# Environment Secrets and Variables Setup

## Minimum required for baseline autopilot

No secrets are required for deterministic programmatic content generation.

## Recommended GitHub Variables

Set these under:

`GitHub repo → Settings → Secrets and variables → Actions → Variables`

- `DAILY_PAGE_LIMIT` = `3` to start; later `6`; max `9`
- `MIN_BASE_PUBLISH_SCORE` = `72`
- `MIN_AUTO_PUBLISH_SCORE` = `85`
- `MAX_DUPLICATE_SIMILARITY` = `0.15`
- `ENABLE_GEMINI_REWRITE` = `false`
- `GEMINI_MODEL` = `gemini-2.5-flash-lite`
- `LINKEDIN_DAILY_LIMIT` = `1`
- `X_DAILY_LIMIT` = `5`
- `FOUNDER_PUBLICATION_DOMAIN` = your actual founder/operator publication domain
- `MEMPHIS_PUBLICATION_DOMAIN` = your actual Memphis publication domain
- `PROFESSIONAL_PUBLICATION_DOMAIN` = your actual professional resource publication domain

## Optional Gemini Secret

Set under:

`GitHub repo → Settings → Secrets and variables → Actions → Secrets`

- `GEMINI_API_KEY`

Then set variable:

- `ENABLE_GEMINI_REWRITE` = `true`

If Gemini fails, is missing, or rate-limits, the base deterministic page is still published if it passes review.

## LinkedIn Secrets for one account

Only needed when LinkedIn auto-posting should actually send posts. Content generation and backlink publication never depend on these credentials.

Gather:

1. LinkedIn developer app access.
2. OAuth access token with posting permissions.
3. The author URN for the single account or organization that will post.

Potential secrets:

- `LINKEDIN_ACCESS_TOKEN`
- `LINKEDIN_AUTHOR_URN`

Possible author URN formats:

- Personal profile: `urn:li:person:<id>`
- Organization page: `urn:li:organization:<id>`

How to retrieve:

1. Create or open a LinkedIn Developer app.
2. Add the appropriate LinkedIn product/API access for posting.
3. Complete OAuth flow for the account/page that will post.
4. Save the returned access token as `LINKEDIN_ACCESS_TOKEN`.
5. Save the person or organization URN as `LINKEDIN_AUTHOR_URN`.

Current behavior: when LinkedIn posting is enabled but credentials are absent, LinkedIn is skipped and the social report records a nonblocking warning. Core content/backlink publication continues.

## X Secrets for one account

Only needed when X auto-posting should actually send posts. Content generation and backlink publication never depend on these credentials.

Gather from the X Developer Portal for the one posting account/app:

- `X_API_KEY`
- `X_API_SECRET`
- `X_ACCESS_TOKEN`
- `X_ACCESS_TOKEN_SECRET`
- `X_BEARER_TOKEN` optional depending on posting method

Current behavior: when X posting is enabled but credentials are absent, X is skipped and the social report records a nonblocking warning. Core content/backlink publication continues.

## Posting failure policy

Social distribution is subordinate to content publication. The shipped workflows may attempt social posting when the enable flags are true, but missing credentials or provider posting failures do not block generated pages, backlinks, validation, or the commit step.

- `ENABLE_LINKEDIN_POSTING=true|false` controls LinkedIn attempts.
- `ENABLE_X_POSTING=true|false` controls X attempts.
- `REQUIRE_SOCIAL_SECRETS=true` records missing credentials explicitly.
- `FAIL_ON_SOCIAL_POST_FAILURE=false` is the normal production setting and keeps social failures nonblocking.
- Set `FAIL_ON_SOCIAL_POST_FAILURE=true` only when the owner intentionally wants social failure to become a hard workflow failure.

The social-only workflow follows the same nonblocking policy and still writes its ledger/report for diagnosis.
