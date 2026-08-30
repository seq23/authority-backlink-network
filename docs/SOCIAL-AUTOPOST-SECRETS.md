# Social Auto-Posting Secrets and Variables

This repo now supports 100% hands-off page publishing and social auto-posting for one LinkedIn account and one X account.

## X posts through Buffer now, and there is nothing left for you to do (2026-08-29)

**The short version.** X's own API stays off and is contacted zero times — it is pay-per-use
and you decided not to fund it. Buffer publishes to the same X profile from its free plan at
no per-post cost, and your X channel `sequoia_ta12767` is connected. **The scheduled runs hand
the day's posts to Buffer by themselves. Nothing is asked of you.**

### The copy-paste sheet is gone

There used to be a `reports/social-drafts.md` — the day's posts written out for you to paste
into X, and a field to set when you had. You said: *"this means i manually have to do it? i
will never do it honestly."* That is the right answer, and it means the sheet was producing
work nobody would ever do while every run reported a growing pile of posts as if it were
pending. So the sheet, the module that wrote it and the validator that guarded it were
**deleted**, not switched off.

One thing survives, read-only: `data/social-draft-ledger.json` still records what you posted
to X **by hand** before this change, under `marked_posted_through`. Those posts are live on
your profile and must never go out again, so every run reads that field. **Nothing updates it
and nothing will ever ask you to.** Everything after that marker was drafted and never posted,
and Buffer has since carried it.

### What happens each day

The scheduled run picks the day's highest-value X posts in the usual priority order, tops up
Buffer's queue to just under what the free plan allows, and stops. Buffer publishes each post
at the channel's next posting slot. Anything there was no room for stays `queued_for_auto_post`
and goes out on a later run as Buffer drains — nothing is dropped and nothing is held anywhere
else.

### The free plan is the ceiling, and it is read fresh every run

You pay Buffer nothing, which is the whole reason this route exists instead of X's paid API.
So the plan's allowances are treated as hard limits, discovered from Buffer's own API on every
single run — never typed into the code, where a number would stay wrong the moment Buffer or
your plan changed. Three different limits apply at once and **the strictest one binds**:

| Limit | What it is | Value on your account |
| --- | --- | --- |
| `dailyPostingLimits.limit` | posts per channel per **day** | 50 for the X channel |
| `limits.scheduledPosts` | posts allowed **queued at once** | **10** |
| `X_DAILY_LIMIT` | this network's own daily decision | 8 |

The middle one is the real constraint and it is not a rate — it is a **depth**. Ten posts may
sit waiting at any moment, so pushing eight a day into it would fill it on day two and stay
full. The route therefore tops the queue up to **one below** the cap and adds more only as
Buffer sends what is already there. The last slot is left free on purpose: Buffer's count and
ours are read moments apart, and filling the final slot is what turns a race into a
`LimitReachedError`. On a day Buffer has published little, few posts leave. That is correct,
not a fault, and the run says which ceiling bound it.

**Nothing here spends money or asks to.** No upgrade, no trial, and no posting past a refusal
to see what happens: a limit or plan refusal **halts the route for that run**, is recorded by
name, and is never retried. The budget is charged on **attempts**, before the request — the
2026-08-29 run that made 581 requests in 76 seconds did so because its caps counted successes.

### The three things that cannot happen

- **No post goes out twice.** Anything at or before `marked_posted_through` — what you posted
  by hand — is refused on **every** path out, Buffer's and X's own API alike.
- **No post reaches the wrong channel.** Your Buffer account also carries `iamcindymercer`, a
  TikTok channel for a different project. The route selects a channel by service (`twitter`)
  and re-checks it before every single post. It will refuse to run rather than fall back to
  "the first channel".
- **No request ever reaches X's own API.** Not a probe, not one attempt to see whether credits
  appeared. Every one would be billable.

`scripts/validators/validate_buffer_route.py` (19 properties) and
`scripts/validators/validate_no_manual_lane.py` (11) block the release if any of that stops
being true, including if `BUFFER_ACCESS_TOKEN` ever reaches a log, a report or a commit.

### Turning the route off

`data/social-brand-policy.json` → `platforms.x.delivery_route.enabled` → `false`, and commit.
X then distributes nothing and its entries simply wait in the queue, counted in the run report
under `deferred_waiting_for_delivery_route`. There is no fallback lane to come back and
nothing will ask you to post anything. Turning X's own paid API back on is still the separate
single boolean below.

## If you ever fund X's own API instead (2026-08-29)

### Why the API is off

**What happens every day:** nothing is sent to X and no request is made to it. The day's posts go into Buffer's free queue instead, as described above.

**What is actually wrong.** Every write to X returns:

```txt
HTTP 402 {"detail":"credits depleted","status":402,"title":"Payment Required",
          "type":"https://api.x.com/2/problems/credits-depleted"}
```

That is X's pay-per-use billing, not a rate limit and not a bug here. X made pay-per-use the default on 2026-02-06 and retired the free tier for new developer signups; `credits-depleted` means the enrolled developer account has no credit balance to charge the request against. Two things establish that this is billing rather than a quota this account spent:

- the **first request of the first run** in this repository's history returned 402, and `posted_at` appears in no revision of `data/social-queue.json` — no post has ever succeeded, so there was never an allowance to use up;
- the problem type is `credits-depleted`. A credential that was wrong, expired or wrongly scoped returns 401 or 403 with a different problem type, so this is not a misconfigured secret being reported as 402.

**So no posting rate gets under it.** Not eight a day, not one a month. Nothing resets on a period boundary. The only fix is to add a credit balance in the X developer console. Note before doing so: on pay-per-use a post **containing a URL costs $0.20**, against $0.015 for one without, and every post this network sends carries a URL — eight a day is roughly **$48/month**.

**So the switch is off, and it is off in a way that keeps the content moving.** `platforms.x.enabled` is `false` — the publisher makes **zero** requests to X, so nothing is billable and nothing is probing a dead endpoint — but `platforms.x.pause_mode` is `"delivery_route"`, which is not the same pause as LinkedIn's. It says the platform's own API lane is off while a declared route carries the same posts. Buffer is that route.

- **The posting queue is untouched.** The route reads `data/social-queue.json` and stamps only what Buffer actually accepted. Fund the X account and automatic posting resumes on the next run with no undo pass.
- **Nothing is ever asked of a person.** A post the route had no room for keeps `queued_for_auto_post` and is counted in the run report under `deferred_waiting_for_delivery_route`. That is a named state, not a task.
- **LinkedIn is not affected.** It is paused `"dormant"` (below): that switch says nothing is wanted from the platform at all.
- **Turning X back on is one boolean.** `data/social-brand-policy.json` → `"enabled": true` under `platforms.x`, and commit. Nothing else — leave `pause_mode` alone, it is inert while the platform is enabled. Fund the developer account first, or every post answers 402 again. Posts you already made by hand stay refused on that path too.

`scripts/validators/validate_no_manual_lane.py` and `scripts/validators/validate_social_pause_modes.py` block the release if any of that stops being true — including if X ever makes a single API request while paused.

## LinkedIn is paused (2026-08-29) — one line turns it back on

**File:** `data/social-brand-policy.json` · **line 17** · change `"enabled": false` to `"enabled": true` under `platforms.linkedin`, and commit. That is the whole switch.

- The 581 LinkedIn posts already in `data/social-queue.json` start going out again on their own. They were never deleted or re-labelled; being parked is derived from the switch, not stamped on the rows, so nothing has to be un-marked or re-created.
- Two repository secrets also have to exist before a post can actually send: `LINKEDIN_ACCESS_TOKEN` and `LINKEDIN_AUTHOR_URN`. Flipping the switch on before adding them breaks nothing — each run records `linkedin_on_but_uncredentialled` in `reports/social-publisher-report.json` and nothing else changes. (X's own API is not posting either — it is paused with a delivery route, above, and Buffer carries its posts.)
- `ENABLE_LINKEDIN_POSTING` / `ENABLE_X_POSTING` are now per-run overrides only. Leave them unset and the file above is the answer. They are listed below for completeness, not as something to set.

Four states are deliberately distinguishable in every run report, under `platform_states`: `paused_by_switch` (a decision that nothing is wanted — LinkedIn, `pause_mode: "dormant"`), `paused_api_awaiting_delivery_route` (the platform's own API is off and a declared route carries its posts — X, `pause_mode: "delivery_route"` — reported only when the route could not carry anything that run, in which case the entries simply wait), `on_but_uncredentialled` (a to-do), and `on_and_posting` (working). A platform switched off without a `paused_on` / `paused_by` / `paused_reason` record fails the build (`scripts/validators/validate_social_rate_limits.py`), and one switched off without a recognised `pause_mode` fails it too (`scripts/validators/validate_social_pause_modes.py`) — an unrecognised mode reads as dormant at runtime, so a typo would silently end that platform's distribution while the run stayed green.

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
