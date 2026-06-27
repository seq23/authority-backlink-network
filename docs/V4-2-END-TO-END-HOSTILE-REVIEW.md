# V4.2 End-to-End Hostile Review

Status: PASS with live API caveat.

## What was validated

1. Python compile check for every script.
2. Authority page generation.
3. Hostile review after page generation.
4. Link audit after page generation.
5. Social publisher dry-run path.
6. Missing-secret guard for live social posting.

## Results

| Test | Expected | Result |
|---|---:|---:|
| Python compile | 0 | 0 |
| Autopilot generation | 0 | 0 |
| Hostile review | 0 | 0 |
| Link audit | 0 | 0 |
| Social dry run | 0 | 0 |
| Missing-secret guard | 1 | 1 |

The missing-secret guard intentionally fails if live social posting is enabled without required LinkedIn/X credentials. That is correct behavior.

## Data trace

### Pages

`authority-v4-autopilot.yml` → `scripts/authority_v4_autopilot.py` → `content-bank/yearly-pantry.json` + `content-bank/scaling-policy.json` → `sites/*/daily/*.html` + `sitemap.xml` + `llms.txt` → `data/link-registry.json` → Cloudflare Git deploy.

### Social

`authority-v4-autopilot.yml` → `scripts/authority_v4_autopilot.py` → `data/social-queue.json` status `queued_for_auto_post` → `scripts/social_publisher.py` → LinkedIn/X APIs → `data/social-queue.json` status `posted` or `post_failed` → `reports/social-publisher-report.json`.

### Posting order

The social publisher prioritizes newest page-generated posts first. Older queued drafts are not allowed to block new page-related social posts.

## Live API caveat

The workflow cannot be live-post tested without real LinkedIn and X secrets. Dry-run logic and missing-secret protection were tested. Live posting will execute once secrets and variables are set in GitHub Actions.
