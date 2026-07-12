# v4.6.1 Python Portability Fix

## Failure repaired

Local updater validation failed on an older local Python runtime because `pathlib.Path.write_text()` was called with the `newline` keyword, which that runtime does not support.

## Change

All generated-text writes that require LF normalization now use `Path.open(..., newline="\n")` followed by `write()`. This preserves deterministic LF output while remaining compatible with the local Python runtime.

## Scope

- `scripts/deterministic_build.py`
- `scripts/authority_v4_autopilot.py`
- package version updated to 4.6.1

## Preservation

The three-publication architecture and all brand-to-publication mappings remain unchanged except for the previously approved Dream Wedding Builder addition to Memphis Vendor Library.

## Validation

`npm run validate:release` passes with zero hard failures, zero strong warnings, and zero soft warnings.
