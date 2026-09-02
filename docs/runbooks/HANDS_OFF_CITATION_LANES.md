# Hands-off citation lanes: the USCIS changelog and the journalist-query scan

Status: ACTIVE
Runtime model: fully autonomous (changelog) and automated-to-one-tap (queries)
Scope: Ranks 4 and 1 of `docs/EXTERNAL-AUTHORITY-PLAN.md`

Both lanes exist because the plan priced them in owner hours, and owner hours are
the scarce resource. Rank 4 was costed at "~1 h/week" with the warning "if that
hour will not happen reliably, do not start this play". Rank 1 was costed at "20
minutes each morning to scan". Neither of those is a commitment worth making, so
neither was made: the work happens in CI and the owner's involvement is reduced
to the one decision a machine must not take.

---

## 1. What the owner has to do

Two things, both one-off, and one of them is optional.

### Required for the journalist-query lane: an inbox it can read

The lane cannot start until there is mail to read. This is a genuine external
dependency and it is the only one.

1. Subscribe to **Source of Sources** at `sourceofsources.com`. It is free, the
   form asks for a name and an email address, and the site says so in as many
   words: *"This list doesn't cost a dime."* Up to three query emails a day.
2. Point it at a mailbox, or filter it into a folder in an existing one.
3. Set these **repository secrets** (Settings → Secrets and variables → Actions):

   | Secret | What it is |
   |---|---|
   | `SOS_IMAP_HOST` | IMAP host of that mailbox, e.g. `imap.gmail.com` |
   | `SOS_IMAP_USER` | the mailbox address |
   | `SOS_IMAP_PASSWORD` | an **app password**, never the account password |

   Optional repository *variables*: `SOS_IMAP_PORT` (default `993`) and
   `SOS_IMAP_FOLDER` (default `INBOX`).

Until those exist the daily run reaches a named stop, opens **one** issue saying
what it needs, and then stays quiet. It does not open that issue again every
morning; a standing instruction nobody follows is a defect this repository has
already paid for once.

The mailbox is read **read-only**. Nothing is marked, moved, deleted or sent.

### Already set, nothing to do: `OPENROUTER_API_KEY`

Both lanes draft through OpenRouter and the secret is already on this repository
(set 2026-08-29 for the citation probe). If it is ever rotated, both lanes reach
a named stop rather than publishing anything unverified. The changelog holds the
change for the next run instead of losing it.

### Nothing else

There is no other credential, no paid tier, and no service to sign up for. In
particular there is **no Featured.com API key**, because there is no Featured
API — see section 4.

---

## 2. The USCIS form and fee changelog (Rank 4)

**Workflow:** `.github/workflows/uscis-changelog.yml`, Tuesdays 13:11 UTC.
**Publishes:** `sites/professional-resources/uscis-form-and-fee-changelog.html`,
served as the changelog page on Professional Resource Library.
**Owner time:** none.

### What it watches, and why only that

Three USCIS pages, declared in `data/uscis-changelog/tracked-sources.json`:
filing fees, forms updates, and the all-forms list. Nothing else, and the file
argues at length for why widening it would make the asset worse. The short
version: what a journalist cites is an *unbroken* record, and every extra agency
adds another URL that can move and another week where the log is partially blind
while still publishing.

### The chain

```text
fetch each tracked page
  unreachable        -> NAMED STOP; snapshot untouched; never "no change"
                        two consecutive misses -> workflow red + issue
  no material change -> say so, stop
  changed            -> diff -> model describes the diff -> VERIFY -> publish
                        -> only then advance the snapshot
```

The snapshot advances **only after** an entry exists. An OpenRouter outage
therefore costs a week of latency and never a lost change: next week's run sees
the same difference again.

### The guard that matters

Every entry must quote text that is actually present in the fetched page, and
every quote must be a line in the stored diff. Applied twice, deliberately:

- the `verify()` function in `scripts/uscis_changelog.py`, at write time, which
  stops a hallucination;
- `scripts/validators/validate_uscis_changelog.py`, offline against the evidence
  stored in each entry, which stops a **hand edit** — the case nothing at write
  time can see, because no run happened.

The validator also drives that guard through a clean fixture entry and five
broken ones on every run, so a week with no entries still proves the guard is
alive rather than reporting a green empty loop.

### If it goes red

A tracked source has been unreachable for two consecutive checks. Read
`reports/uscis-changelog-latest.json`, and if USCIS moved the page, update the
URL in `data/uscis-changelog/tracked-sources.json` and register the new URL in
`data/external-sources.json` (`npm run sources:verify-network`). Nothing was
published as "unchanged" for that source in the meantime.

---

## 3. The journalist-query scan (Rank 1)

**Workflow:** `.github/workflows/journalist-query-scan.yml`, weekdays 12:30 UTC.
**Surfaces:** one GitHub issue, only on days with something worth answering.
**Owner time:** about two minutes, on the days there is anything.

### The send is human, permanently

There is no send path in `scripts/journalist_query_scan.py`, no mail transport is
imported, and `scripts/validators/validate_journalist_query_lane.py` fails the
build the day one appears — including the day someone adds it for a good reason,
because a good reason is exactly how it would arrive.

The reasoning is not caution. Pitches go out in Sequoia's name as a genuine
expert. An auto-sent pitch carrying one wrong fact gets printed under her name:
a correction in a real publication, and a source relationship burned permanently
and silently. The upside of auto-sending is about thirty seconds.

### What a run does

Ingests the day's digests, drops anything matching a hard exclusion before any
model is asked anything, prefilters to the declared beats, then asks for a draft
grounded **only** in `data/journalist-queries/expertise-ledger.json`. Nothing
relevant means nothing is sent at all. One to three relevant means one issue
carrying the query, the outlet, the deadline, the address to reply to, and a
draft under 200 words.

### The ledger is the thing to maintain

If a draft says something she would not say, **edit the ledger, not the draft**.
The ledger is what the next draft is built from; a fixed draft fixes one day.

Every fact in it must point at evidence a stranger can open, and the validator
hard-fails if that evidence path does not exist. Every number in a draft must
appear in a fact the draft cited — numbers are the highest-risk fabrication and
the only claim class that can be checked mechanically, so they are.

### Quiet day versus broken lane

These must never look the same, and the failure mode of a lane like this is that
they do. A digest the parser cannot read produces a named `UNPARSEABLE_DIGEST`
stop naming the provider and quoting what it could not read — never "no relevant
queries today". The validator proves this by feeding the real scanner an
unreadable digest and failing if the run calls it quiet.

If a provider changes its email layout, the fix is field labels in
`data/journalist-queries/query-formats.json`. No code change.

---

## 4. What was verified about ingestion, on 2026-09-01

Checked live before anything was built, because the plan named a Featured API
endpoint and it does not exist.

| Claim | Result |
|---|---|
| Source of Sources delivers queries by email | **Confirmed.** *"Up to three times a day, you'll get an email filled with queries from journalists"*; signup is name + email; *"This list doesn't cost a dime."* |
| Source of Sources has a query feed | **False.** `sourceofsources.com/feed` returns 200 but is the WordPress *blog* feed — channel title "Source of Sources", `lastBuildDate` Jan 2026, articles like "How to Create an Online Press Kit". It is not the queries and must not be used as if it were. |
| `featured.com/api-integration/sign-up` | **HTTP 404.** So is `featured.com/api`. `featured.com/robots.txt` disallows the api path. `featured.com/questions` answers **429** to automated requests. No public API; nothing was built against Featured. |
| The owner already receives these emails | **No.** Her mailbox has zero messages from `sourceofsources.com`, `featured.com`, `helpareporter.com`, `qwoted.com` or `sourcebottle.com` in the previous 60 days. |

That last row is why section 1 exists: the lane is complete and the only missing
piece is a free subscription and one app password.

---

## 5. Rule 0 in both lanes

Neither may exit 0 having done nothing without saying so. The legitimate named
outcomes are:

| Lane | Named outcome | Meaning |
|---|---|---|
| changelog | `NO CHANGE` | every tracked page was fetched, compared, and none moved |
| changelog | `BASELINE_CAPTURED` | first copy taken; the absence of an entry is **not** a claim that nothing changed |
| changelog | `NAMED_STOP_UNREACHABLE` | a page could not be fetched; never recorded as unchanged |
| changelog | `HELD` | a change was found but could not be described; retried, not lost |
| queries | `NO RELEVANT QUERIES` | queries were read and every one was dropped, with counts by reason |
| queries | `NAMED STOP NO_MAILBOX_CREDENTIAL` | nothing was looked at, which is not the same as nothing being there |
| queries | `NAMED STOP UNPARSEABLE_DIGEST` | a digest arrived and could not be read |

Each is printed into the workflow log by a step that runs `if: always()`, so a
green run is never mistaken for a run that did not happen.
