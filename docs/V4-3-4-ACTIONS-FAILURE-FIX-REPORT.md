# V4.3.4 Actions Failure Fix Report

## Failure 1: Missing LinkedIn/X secrets caused social workflow failure

### Prior behavior
`python3 scripts/social_publisher.py` exited with code 1 when live posting was enabled but LinkedIn or X secrets were missing.

### Fixed behavior
Missing social secrets now cause a platform-level skip, not a workflow failure.

- Missing LinkedIn secrets disable LinkedIn for that run and record `secret_skips.linkedin`.
- Missing X secrets disable X for that run and record `secret_skips.x`.
- Exit code remains 0 unless an actual attempted post fails and `FAIL_ON_SOCIAL_POST_FAILURE=true`.

## Failure 2: Autopilot generated malformed publication URLs

### Prior behavior
If a GitHub Variable existed but was blank, `os.getenv(NAME, default)` returned an empty string and generated `https:///daily/...` URLs.

### Fixed behavior
Publication domains now resolve using `os.getenv(NAME) or default_domain`, so blank variables fall back to canonical default publication domains.

## Validation performed

- `npm run release:prepush:local` passed.
- Live social publisher with missing LinkedIn/X secrets exited successfully and reported platform skips.
- Autopilot was tested with blank publication domain env vars; hostile review passed with no `https:///` URL errors.
