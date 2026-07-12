# Authority Network v4.5 Validation, Deterministic Build, and Page Cache Upgrade Plan

## Governing decisions

- Validation tier: V2 generated/content-heavy site, with V4 provider-boundary checks for social publishing only.
- One orchestration authority: `scripts/validate.py` + one profile plan. Package scripts and workflows are aliases only.
- Hard failures only for corruption, unsafe publication, false evidence, wrong-domain routing, secret exposure, broken required journeys, stale/mismatched cache proof, or executable/internal errors.
- Word counts, page-count targets, cadence, link-count preferences, optional metadata, and repairable quality drift are warnings.
- Generated pages get one deterministic self-repair pass and one recheck. No recursive validator loops.
- Cache is performance-only and can never change the verdict.

## Phase 1 — Canonical page model and deterministic generator

1. Separate canonical page inputs from runtime receipts.
2. Replace wall-clock values inside canonical generated HTML with a controlled build date supplied through `BUILD_DATE` or source state.
3. Sort every input collection before selection, serialization, sitemap generation, and ledger writing.
4. Add stable IDs for pages, links, social items, and generation jobs.
5. Make all JSON/state writes atomic.
6. Add clean-build mode that starts from authoritative data and an empty generated-output directory.

## Phase 2 — Shared final-state page audit engine

Create one parser/auditor that reads each HTML page once and returns:

- route and canonical identity;
- publication and city ownership;
- title, description, headings, schema, FAQ, disclosures;
- internal and external links;
- target-brand/product route metadata;
- word count and quality diagnostics;
- sensitive-topic classification;
- duplicate-content fingerprint;
- self-repairable defects;
- hard-failure defects.

Hostile review and link audit become policy views over this shared audit result instead of independently reparsing every page.

## Phase 3 — Severity and self-healing

### Hard fail

- malformed or unreadable canonical data;
- duplicate route/domain ownership;
- unregistered external target;
- wrong publication lane;
- product-route mismatch;
- missing required disclosure on sensitive content;
- fabricated evidence or prohibited claim;
- ledger/HTML contradiction;
- secret exposure;
- nondeterministic release output;
- stale or foreign cache proof reused.

### Strong warning with repair attempt

- missing FAQ or schema on generated page;
- thin generated section;
- excessive links;
- missing optional metadata;
- repeated anchor pattern;
- near-duplicate content;
- word count outside preferred range.

### Repair model

`audit -> repair once -> audit once -> publish if no hard failures`

Repairs may add required generated schema, FAQ shells grounded in existing content, normalize metadata, correct deterministic ordering, or remove an accidental duplicate link. Repairs may not invent claims, sources, local facts, testimonials, or provider details.

## Phase 4 — Content-addressed page cache

Use one cache root:

`.validation-cache/`

Each page receipt fingerprint includes:

- repository/validation epoch;
- source page hash;
- publication/city registry hash;
- brand/product registry hash;
- shared template/generator hash;
- page-audit engine hash;
- policy/config hash;
- dependency lock hash;
- validation profile.

Cache only PASS and approved warning-pass receipts. Never cache FAIL, internal error, interrupted, incomplete, or foreign receipts.

## Phase 5 — Dependency-aware invalidation

- page changed -> re-audit page;
- publication/city record changed -> re-audit affected publication;
- brand/product registry changed -> re-audit pages linking to affected brands;
- shared generator/template changed -> re-audit all generated pages;
- audit engine/policy/epoch changed -> full uncached audit;
- unknown impact -> full uncached audit with strong warning, not guessed zero work.

Global invariants always run: duplicate routes, domain ownership, registry parsing, active-city checks, sitemap membership, ledger consistency, secret scans, and packaging exclusions.

## Phase 6 — Profiles

- `validate:changed`: affected pages + global invariants.
- `validate:release`: deterministic build, one repair pass, final-state cached audit, global invariants, portability receipt.
- `validate:full`: empty cache, every page, rebuild trusted baseline.
- `validate:cache:self-test`: hostile cache fixtures only.
- `validate:clean-rebuild`: two isolated builds and parity comparison.

## Phase 7 — Clean-rebuild parity

Class 1 strict byte parity:

- HTML pages;
- sitemap.xml;
- llms.txt;
- canonical registries;
- generated route/link manifests.

Class 2 semantic parity only where a narrowly declared runtime field is unavoidable.

Class 3 runtime evidence excluded from canonical parity:

- reports;
- post IDs;
- API responses;
- workflow timestamps.

No global timestamp ignore rule.

## Phase 8 — Hostile fixtures

Fixtures must prove:

- warning does not exit nonzero;
- self-repair runs once only;
- cache miss recomputes;
- corrupt cache is discarded;
- failed result is never reused;
- changed registry invalidates dependent pages;
- unknown dependency impact forces full validation;
- cold and warm runs return the same verdict;
- clean builds produce identical governed artifacts;
- cache objects never enter the ZIP;
- social dry run exercises LinkedIn and X without queue mutation;
- missing required social secrets block before any post attempt.

## Phase 9 — CI cache

GitHub Actions cache key includes validation epoch, lock hash, validator/audit hash, runtime/OS class, and safe branch/ref class. A cold runner and restored-cache runner must return identical verdicts. Cache absence is not a failure.

## Phase 10 — Operator docs and packaging

Add Day-0 commands, receipt interpretation, cache clearing, repair behavior, and recovery steps. Packaging must run release, clean parity, cold proof, warm proof, exclude `.validation-cache`, reopen the ZIP, and verify the repo root.
