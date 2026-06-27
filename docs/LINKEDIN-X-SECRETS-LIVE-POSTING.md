# LinkedIn + X Secrets for Live Auto-Posting

This repo supports one LinkedIn account and one X account.

## GitHub Variables

Set these under:

`GitHub repo → Settings → Secrets and variables → Actions → Variables`

Recommended starting values:

```txt
DAILY_PAGE_LIMIT=3
ABSOLUTE_MAX_PAGES_PER_DAY=9
MIN_BASE_PUBLISH_SCORE=72
ENABLE_GEMINI_REWRITE=false
GEMINI_MODEL=gemini-2.5-flash-lite
PUBLISH_IF_GEMINI_FAILS=true
LINKEDIN_DAILY_LIMIT=1
X_DAILY_LIMIT=5
ENABLE_LINKEDIN_POSTING=true
ENABLE_X_POSTING=true
REQUIRE_SOCIAL_SECRETS=true
FAIL_ON_SOCIAL_POST_FAILURE=false
SOCIAL_DRY_RUN=true
MAX_SOCIAL_SIMILARITY=0.86
LINKEDIN_VERSION=202606
FOUNDER_PUBLICATION_DOMAIN=founderoperatorlibrary.com
MEMPHIS_PUBLICATION_DOMAIN=memphisvendorlibrary.com
PROFESSIONAL_PUBLICATION_DOMAIN=professionalresourcelibrary.com
```

After dry-run succeeds, change:

```txt
SOCIAL_DRY_RUN=false
```

## GitHub Secrets

Set these under:

`GitHub repo → Settings → Secrets and variables → Actions → Secrets`

### Optional Gemini rewrite

```txt
GEMINI_API_KEY
```

### LinkedIn live posting

```txt
LINKEDIN_ACCESS_TOKEN
LINKEDIN_AUTHOR_URN
```

`LINKEDIN_AUTHOR_URN` should be the URN for the single LinkedIn author you want posting.

Common forms:

```txt
urn:li:person:YOUR_PERSON_ID
urn:li:organization:YOUR_ORGANIZATION_ID
```

Use a person URN for posting from Sequoia's personal profile. Use an organization URN for posting from a company page where you have admin/API permissions.

### X live posting

```txt
X_API_KEY
X_API_SECRET
X_ACCESS_TOKEN
X_ACCESS_TOKEN_SECRET
```

These must belong to the one X account that should post.

## Recommended setup order

1. Add all variables with `SOCIAL_DRY_RUN=true`.
2. Add LinkedIn and X secrets.
3. Run `Social Auto-Post Only` manually.
4. Confirm report shows dry-run successes.
5. Set `SOCIAL_DRY_RUN=false`.
6. Run `Social Auto-Post Only` manually once.
7. Let schedules run.

## Failure behavior

- Missing secrets in live mode cause the workflow to fail closed.
- Failed social API calls are logged in `reports/social-publisher-report.json`.
- `FAIL_ON_SOCIAL_POST_FAILURE=false` lets the workflow continue while recording failed posts.
- Set `FAIL_ON_SOCIAL_POST_FAILURE=true` if you want failed social posting to fail the whole workflow.
