# V4.3.4 GitHub Actions Failure Fix

## Fixed failures

1. `social_publisher.py` no longer hard-fails when LinkedIn or X secrets are missing. Missing platform secrets now skip that platform and report `secret_skips`.
2. `authority_v4_autopilot.py` no longer emits `https:///...` social URLs when GitHub Variables exist but are blank. Publication domains now use `os.getenv(NAME) or default_domain`.

## Expected behavior

- If `LINKEDIN_ACCESS_TOKEN` / `LINKEDIN_AUTHOR_URN` are missing, LinkedIn posting is skipped.
- If X secrets are missing, X posting is skipped.
- Hostile review fails if any generated social URL has a malformed domain.
- GitHub Actions can pass before live social credentials are added.
