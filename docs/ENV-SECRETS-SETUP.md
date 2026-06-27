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

Only needed if a future patch enables auto-posting.

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

Current repo status: LinkedIn auto-posting is not enabled. Social items are draft-only.

## X Secrets for one account

Only needed if a future patch enables auto-posting.

Gather from the X Developer Portal for the one posting account/app:

- `X_API_KEY`
- `X_API_SECRET`
- `X_ACCESS_TOKEN`
- `X_ACCESS_TOKEN_SECRET`
- `X_BEARER_TOKEN` optional depending on posting method

Current repo status: X auto-posting is not enabled. X items are draft-only.

## Posting safety recommendation

Keep these false until the social publisher patch is intentionally installed:

- `ENABLE_LINKEDIN_POSTING=false`
- `ENABLE_X_POSTING=false`

The current baseline is designed to generate social drafts, not publish them.
