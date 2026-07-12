# Authority Network v4.5 Validation Architecture

## Architecture law

The repository has one validation orchestrator: `scripts/validate.py`.

It delegates to evidence-producing components. No validator creates a second registry hierarchy, and no validator validates another validator recursively.

## Components

| Component | Responsibility |
|---|---|
| `scripts/validate.py` | profile order, receipts, release verdict |
| `validation/page_audit.py` | parse each HTML page into one normalized page model |
| `validation/repair.py` | one safe mechanical repair pass for generated daily pages |
| `validation/cache.py` | content-addressed successful proof cache |
| `scripts/page_validation.py` | cache planning, repair, final page receipt |
| `scripts/deterministic_build.py` | two-build parity for sitemaps and `llms.txt` |
| `scripts/cache_self_test.py` | hostile cache fixtures |
| existing hostile/link/social checks | policy-specific global invariants and journey proof |

## Profiles

- `changed`: fast, cache-aware, no repairs
- `release`: cache-aware, one repair pass, deterministic proof
- `full`: all pages, no reusable page proof, cache fixtures
- `cache-self-test`: isolated hostile fixtures only
- `clean-rebuild`: deterministic derived-artifact parity

## Release verdict

```text
release blocked = hard failures > 0
```

Warnings never become hidden hard failures.

## Page audit fields

Each page receipt contains:

- path and route;
- publication;
- source hash;
- title and H1;
- word count;
- canonical and meta description;
- HTML language;
- internal and external links;
- schema count;
- duplicate-content fingerprint;
- findings;
- repairs;
- cache status.

## Packaging law

`.validation-cache`, Python bytecode, temporary files, and runtime secrets must not enter the ZIP.
