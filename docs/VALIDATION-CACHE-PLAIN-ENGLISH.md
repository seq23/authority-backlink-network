# Validation and Page Cache — Plain English

## Why this exists

The repository has many generated pages. Reading every page several times in several scripts wastes time and encourages brittle validation chains.

v4.5 uses one shared page reader. It extracts the page title, H1, words, links, schema, descriptions, and publication identity once. The result becomes reusable proof.

## What the cache stores

The cache stores successful page-audit receipts tied to exact fingerprints. A fingerprint includes:

- the page bytes;
- brand, publication, city, pantry, and network-rule files;
- the page-audit code;
- the repair code;
- the cache code;
- the validation profile and epoch.

When any relevant input changes, the old receipt no longer matches and the page is checked again.

## What the cache does not store

The cache never reuses:

- failures;
- interrupted runs;
- malformed receipts;
- mismatched proof;
- results from another validation epoch.

## Hard failures versus warnings

Hard failures are reserved for real release risk. Word count is a soft warning. Missing optional metadata is a warning. A wrong domain, malformed JSON-LD, missing title, duplicate domain ownership, or unsafe claim is a hard failure.

## Clean rebuild

The deterministic-build command generates governed derived files twice in separate temporary directories. The hashes must match exactly. This proves that identical inputs produce identical sitemaps and LLM discovery files.

## Cold and warm validation

- A cold run has no reusable cache.
- A warm run reuses matching successful receipts.
- Both runs must produce the same release decision.

The only acceptable difference is speed and the hit/miss count.
