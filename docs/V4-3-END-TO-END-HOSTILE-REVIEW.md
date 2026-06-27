# V4.3 End-to-End Hostile Review + Fix Loop

Review date: 2026-06-27

## Verdict

PASS after fix loop.

## Scope Reviewed

- `.github/workflows/authority-v4-autopilot.yml`
- `.github/workflows/hostile-review.yml`
- `.github/workflows/social-autopost.yml`
- `scripts/authority_v4_autopilot.py`
- `scripts/hostile_review.py`
- `scripts/link_audit.py`
- `scripts/social_publisher.py`
- `data/brands.json`
- `data/publications.json`
- `data/network-rules.json`
- `data/social-queue.json`
- `content-bank/yearly-pantry.json`
- `content-bank/scaling-policy.json`
- all three publication folders under `sites/`

## Hostile Findings

### Finding 1 — Daily social cap could be exceeded across two workflows

Severity: HIGH

Issue: `authority-v4-autopilot.yml` and `social-autopost.yml` can both run on the same day. The social publisher originally enforced limits only per run, not per day across the queue ledger. That meant the repo could post 1 LinkedIn + 5 X during autopilot, then another 1 LinkedIn + 5 X during the separate social workflow.

Fix applied: `scripts/social_publisher.py` now initializes `posted_today` from existing `posted_at` values in `data/social-queue.json`. If the daily cap has already been reached, later workflow runs post nothing.

Validation: `test-07-social-daily-cap-second-run.txt` shows second same-day social run made zero attempts and preserved `posted_today` as LinkedIn 1 / X 5.

### Finding 2 — Missing social secrets must stop live posting

Severity: HIGH

Status: PASS

The live social publisher fails closed when posting is enabled, dry run is false, and required secrets are missing.

Validation: `test-08-social-secret-guard.txt` intentionally failed with missing LinkedIn secrets. This is expected and correct behavior.

### Finding 3 — Cloudflare deploy workflow duplication risk

Severity: MEDIUM

Status: PASS

No direct Cloudflare deploy workflows are present. Cloudflare deploy remains handled by Cloudflare Git integration after GitHub Actions commits to `main`.

### Finding 4 — Link lane / target-domain contamination risk

Severity: HIGH

Status: PASS

`hostile_review.py` and `link_audit.py` validate that outbound target domains are in the locked brand registry and assigned to the correct publication lane.

Validation: `link-audit.json` shows zero violations.

### Finding 5 — YMYL unsafe content risk

Severity: HIGH

Status: PASS

Professional-resource pages and sensitive topic pages require disclaimers and fail on banned claims such as guaranteed outcomes, fake rankings, fake reviews, or advice-style claims.

Validation: `hostile-review-report.json` shows zero errors.

## Isolated Tests Run

| Test | Purpose | Expected | Result |
|---|---|---:|---:|
| 01 pycompile | Python syntax validation | 0 | PASS |
| 02 workflow static | Workflow token/path validation | 0 | PASS |
| 03 autopilot generation | Generate 9 pages with deterministic engine | 0 | PASS |
| 04 hostile review | Review generated + existing site content | 0 | PASS |
| 05 link audit | Validate all outbound links | 0 | PASS |
| 06 social dry run first pass | Simulate 1 LinkedIn + 5 X posts | 0 | PASS |
| 07 social daily cap second run | Confirm second same-day run posts nothing | 0 | PASS |
| 08 social secret guard | Confirm live mode fails without secrets | 1 expected | PASS |
| 09 JSON integrity | Validate JSON files parse | 0 | PASS |

## Final Recommendation

Install this V4.3 package, add required GitHub variables/secrets, then run workflows in this order:

1. `Hostile Review`
2. `Authority Network V4.2 Autopilot + Social Auto-Post` with `SOCIAL_DRY_RUN=true`
3. Set `SOCIAL_DRY_RUN=false`
4. Run `Social Auto-Post Only` manually once
5. Let schedules run
