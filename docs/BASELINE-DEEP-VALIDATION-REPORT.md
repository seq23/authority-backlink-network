# Authority Network Baseline Deep Validation Report

Validation date: 2026-06-27

## Scope

This baseline combines the targeted Authority Network repo with the V4.1 one-year pantry/autopilot patch.

It is locked to these owned target domains only:

- theindustryguides.com
- theaccidentguides.com
- dentistryguides.com
- hormonesivhair.com
- neuroevalguides.com
- uscisexam.com
- billionairehighperformancecoach.com
- aplayermode.com
- virtualagency-os.com
- westpeekproductions.com
- horselegalguide.com
- hicksconsulting.org
- porchandparty901.com

Publication lanes:

- founderoperatorlibrary.com → Founder / Operator / AI / virtual production lane
- memphisvendorlibrary.com → Memphis local vendor / Porch & Party lane
- professionalresourcelibrary.com → Industry Guides / equine / Hicks professional-resource lane

## Workflow Inventory

Included workflows:

1. `.github/workflows/authority-v4-autopilot.yml`
   - Scheduled daily at 14:22 UTC.
   - Manual `workflow_dispatch` supported.
   - Generates deterministic content from the pantry.
   - Optionally attempts Gemini rewrite when enabled.
   - Publishes passing static HTML pages by committing generated files.
   - Updates sitemaps, llms.txt, link registry, social queue, and reports.
   - Cloudflare deploy is handled by Cloudflare Git integration after commit.

2. `.github/workflows/hostile-review.yml`
   - Runs on pull request and push to main.
   - Runs hostile review and link audit.
   - Uploads reports as a GitHub Actions artifact.

Removed/omitted workflows:

- Direct Cloudflare deploy workflows were removed because Cloudflare is already connected to GitHub.
- The old standalone social-drafts workflow was removed because V4 autopilot now updates the unified social queue.

## Isolated Validation Results

### Static validation

- Python compile check: PASS
- `npm run check`: PASS
- Hostile review before generation: PASS
- Link audit before generation: PASS

### Autopilot isolated volume tests

Each volume was run in a separate copy of the repo.

| Test | DAILY_PAGE_LIMIT | Published | Hostile Review | Link Audit | Duplicate Warnings | Hard Fails |
|---|---:|---:|---|---|---:|---:|
| conservative | 3 | 3 | PASS | PASS | 0 | 0 |
| normal | 6 | 6 | PASS | PASS | 0 | 0 |
| max allowed | 9 | 9 | PASS | PASS | 0 | 0 |

### Consecutive-run self-heal test

A max-volume run was executed twice against the same test copy.

| Run | DAILY_PAGE_LIMIT | Published | Hostile Review | Link Audit | Duplicate Warnings | Hard Fails |
|---|---:|---:|---|---|---:|---:|
| first | 9 | 9 | PASS | PASS | 0 | 0 |
| second | 9 | 9 | PASS | PASS | 0 | 0 |

Result: PASS. The engine selected new deterministic signatures and did not duplicate previously published signatures.

## Known Operating Model

- Baseline generation requires no paid AI key.
- Gemini is optional, not required.
- If Gemini is disabled, missing, rate-limited, or returns a bad response, the deterministic page version is used if it passes the score gate.
- Social output is draft-only by default and remains `draft_requires_human_approval`.
- LinkedIn/X API posting is not enabled by default.

## Final Baseline Status

PASS.

This repo is safe to upload as a full baseline snapshot and then run GitHub Actions manually once before relying on the schedule.
