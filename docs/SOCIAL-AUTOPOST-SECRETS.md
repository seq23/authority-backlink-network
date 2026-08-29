# Social Auto-Posting Secrets and Variables

This repo now supports 100% hands-off page publishing and social auto-posting for one LinkedIn account and one X account.

## How it works

1. `authority-v4-autopilot.yml` generates pages, validates them, queues social posts, posts the social queue, commits ledgers/reports, and lets Cloudflare Git integration deploy the pages.
2. `social-autopost.yml` is a second posting-only workflow that can clear queued posts even when no new pages are generated.
3. Social posting uses official APIs only. No browser automation, cookie automation, scraping, auto-DMs, or fake engagement.

## Required GitHub variables

Go to GitHub repo → Settings → Secrets and variables → Actions → Variables.

Set:

```txt
DAILY_PAGE_LIMIT=3
ABSOLUTE_MAX_PAGES_PER_DAY=9
MIN_BASE_PUBLISH_SCORE=72
ENABLE_GEMINI_REWRITE=false
GEMINI_MODEL=gemini-2.5-flash-lite
ENABLE_LINKEDIN_POSTING=true
ENABLE_X_POSTING=true
REQUIRE_SOCIAL_SECRETS=true
FAIL_ON_SOCIAL_POST_FAILURE=false
SOCIAL_DRY_RUN=false
LINKEDIN_DAILY_LIMIT=3
X_DAILY_LIMIT=8
MAX_SOCIAL_SIMILARITY=0.86
LINKEDIN_VERSION=202606
FOUNDER_PUBLICATION_DOMAIN=founderoperatorlibrary.com
MEMPHIS_PUBLICATION_DOMAIN=memphisvendorlibrary.com
PROFESSIONAL_PUBLICATION_DOMAIN=professionalresourcelibrary.com
```

Use your actual domains if different.

## Optional Gemini secret

Only needed if you want free-tier AI polish/rewrite. Baseline generation does not require it.

```txt
GEMINI_API_KEY
```

## LinkedIn secrets

Go to GitHub repo → Settings → Secrets and variables → Actions → Secrets.

Add:

```txt
LINKEDIN_ACCESS_TOKEN
LINKEDIN_AUTHOR_URN
```

`LINKEDIN_AUTHOR_URN` must be one of:

```txt
urn:li:person:YOUR_PERSON_ID
urn:li:organization:YOUR_ORGANIZATION_ID
```

Use a person URN if posting from your personal profile. Use an organization URN if posting from a company page. The access token must have the matching LinkedIn posting permission for that author.

## X secrets

Add:

```txt
X_API_KEY
X_API_SECRET
X_ACCESS_TOKEN
X_ACCESS_TOKEN_SECRET
```

The X token must have write/post permission for the account. App-only bearer tokens are not enough for posting as a user.

## Validation mode before live posting

To test without posting publicly, set:

```txt
SOCIAL_DRY_RUN=true
```

Run both workflows manually. Confirm `reports/social-publisher-report.json` shows dry-run successes. Then set:

```txt
SOCIAL_DRY_RUN=false
```

## Kill switches

```txt
ENABLE_LINKEDIN_POSTING=false
ENABLE_X_POSTING=false
```

Use these to immediately stop posting while leaving page generation active.
