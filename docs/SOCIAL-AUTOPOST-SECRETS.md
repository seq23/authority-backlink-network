# Social Auto-Posting Secrets and Variables

This repo now supports 100% hands-off page publishing and social auto-posting for one LinkedIn account and one X account.

## X is paused for posting — you post it by hand (2026-08-29)

**What happens every day:** nothing is sent to X and no request is made to it; `scripts/social_drafts.py` writes the day's eight highest-value X posts to `reports/social-drafts.md` instead.

**What you do:** open `reports/social-drafts.md`, post the eight posts on it by hand, then set `"marked_posted_through"` in `data/social-draft-ledger.json` to the batch id printed at the top of that sheet and commit. That is the whole loop.

**What is actually wrong.** Every write to X returns:

```txt
HTTP 402 {"detail":"credits depleted","status":402,"title":"Payment Required",
          "type":"https://api.x.com/2/problems/credits-depleted"}
```

That is X's pay-per-use billing, not a rate limit and not a bug here. X made pay-per-use the default on 2026-02-06 and retired the free tier for new developer signups; `credits-depleted` means the enrolled developer account has no credit balance to charge the request against. Two things establish that this is billing rather than a quota this account spent:

- the **first request of the first run** in this repository's history returned 402, and `posted_at` appears in no revision of `data/social-queue.json` — no post has ever succeeded, so there was never an allowance to use up;
- the problem type is `credits-depleted`. A credential that was wrong, expired or wrongly scoped returns 401 or 403 with a different problem type, so this is not a misconfigured secret being reported as 402.

**So no posting rate gets under it.** Not eight a day, not one a month. Nothing resets on a period boundary. The only fix is to add a credit balance in the X developer console. Note before doing so: on pay-per-use a post **containing a URL costs $0.20**, against $0.015 for one without, and every post this network sends carries a URL — eight a day is roughly **$48/month**.

**So the switch is off, and it is off in a way that keeps the content moving.** `platforms.x.enabled` is `false` — the publisher makes **zero** requests to X, so nothing is billable and nothing is probing a dead endpoint — but `platforms.x.pause_mode` is `"draft_by_hand"`, which is not the same pause as LinkedIn's. On every run `scripts/social_drafts.py` writes the day's eight highest-value posts to `reports/social-drafts.md` — the exact text the API would have sent, the link, nothing to assemble — and also prints them into the workflow run summary. The selection is the same one the publisher uses (`scripts/lib/social_selection.py`), so the sheet is the posts the API would have sent, in the order it would have sent them.

- **A batch stays put until you mark it done.** Runs re-render the same sheet rather than piling a second batch on top, so you never face a wall of 581 drafts.
- **Marking done is one edit,** exactly like the LinkedIn switch: set `marked_posted_through` to the batch id. Every draft in that batch and every earlier one is retired, and the next run cuts a fresh batch. Nothing is ever stamped row by row, so there is nothing to un-mark.
- **The posting queue is untouched.** Drafting reads `data/social-queue.json` and writes nothing to it. Fund the X account and automatic posting resumes on the next run with no undo pass — the drafts sheet simply stops being written.
- **LinkedIn is not drafted.** It is paused `"dormant"` (below): that switch says nothing is wanted from the platform at all, so drafting it would reverse a decision nobody made.
- **Turning X back on is one boolean.** `data/social-brand-policy.json` · **line 8** · change `"enabled": false` to `"enabled": true` under `platforms.x`, and commit. Nothing else — leave `pause_mode` alone, it is inert while the platform is enabled. Fund the developer account first, or every post answers 402 again.

`scripts/validators/validate_social_drafts_fallback.py` and `scripts/validators/validate_social_pause_modes.py` block the release if any of that stops being true — including if X ever makes a single API request while paused.

## LinkedIn is paused (2026-08-29) — one line turns it back on

**File:** `data/social-brand-policy.json` · **line 17** · change `"enabled": false` to `"enabled": true` under `platforms.linkedin`, and commit. That is the whole switch.

- The 581 LinkedIn posts already in `data/social-queue.json` start going out again on their own. They were never deleted or re-labelled; being parked is derived from the switch, not stamped on the rows, so nothing has to be un-marked or re-created.
- Two repository secrets also have to exist before a post can actually send: `LINKEDIN_ACCESS_TOKEN` and `LINKEDIN_AUTHOR_URN`. Flipping the switch on before adding them breaks nothing — each run records `linkedin_on_but_uncredentialled` in `reports/social-publisher-report.json` and nothing else changes. (X is not posting either — it is paused for posting, above.)
- `ENABLE_LINKEDIN_POSTING` / `ENABLE_X_POSTING` are now per-run overrides only. Leave them unset and the file above is the answer. They are listed below for completeness, not as something to set.

Four states are deliberately distinguishable in every run report, under `platform_states`: `paused_by_switch` (a decision that nothing is wanted — LinkedIn, `pause_mode: "dormant"`), `paused_for_posting_drafts_by_hand` (the API is off but distribution continues by hand — X, `pause_mode: "draft_by_hand"`), `on_but_uncredentialled` (a to-do), and `on_and_posting` (working). A platform switched off without a `paused_on` / `paused_by` / `paused_reason` record fails the build (`scripts/validators/validate_social_rate_limits.py`), and one switched off without a recognised `pause_mode` fails it too (`scripts/validators/validate_social_pause_modes.py`) — an unrecognised mode reads as dormant at runtime, so a typo would silently end that platform's distribution while the run stayed green.

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
