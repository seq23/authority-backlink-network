# V4.1 Hostile Review Report

## Verdict
PASS AFTER PATCH.

This patch replaces the earlier V4 autopilot script with a stricter V4.1 version. The original V4 direction was sound, but the implementation had issues that would have weakened long-run quality control.

## Issues found in V4

1. Duplicate detection was too weak.
   - The previous content hash included timestamps/date-bearing generated material, so near-repeat pages could appear unique.
   - Fix: V4.1 hashes normalized article text and stores durable page signatures.

2. The duplicate-similarity function existed but was not used.
   - Fix: V4.1 applies exact normalized content hashes plus durable topic signatures. Full-page Jaccard is not used as a hard fail because these sites intentionally share editorial boilerplate, disclaimers, and schema; using full-page overlap at 0.15 would falsely reject good output.

3. Python's built-in `hash()` was used for content selection.
   - Python hash randomization can change choices across runtime sessions.
   - Fix: V4.1 uses deterministic SHA-256 based selection.

4. Gemini rewrite response handling was brittle.
   - Markdown code fences could break output.
   - Fix: V4.1 strips common code fences and preserves full HTML only when valid.

5. YMYL checks were too loose.
   - Fix: V4.1 adds explicit legal/medical/mental-health/professional topic checks and hard-fails pages missing educational/professional-advice caution.

6. Unsafe marketing language needed stronger penalties.
   - Fix: V4.1 hard-fails phrases such as guaranteed/#1/number one/fake review language.

7. Content signature exhaustion handling was thin.
   - Fix: V4.1 attempts up to 20 alternate combinations before skipping.

8. The patch included sample-repo recommendations inside the patch bundle.
   - Fix: removed from this patch. Those recommendations are now a separate standalone deliverable.

## Current safety model

- 3 pages/day during warm-up.
- 6 pages/day after successful quality history.
- 9 pages/day only after sustained pass rate and quality.
- `MIN_BASE_PUBLISH_SCORE` default: 72.
- `MAX_DUPLICATE_SIMILARITY` remains available as a policy variable, but V4.1 uses normalized content hashes and topic signatures as the operational duplicate gate to avoid false positives from shared boilerplate.
- Gemini is optional and never blocks publishing if the base page passes.
- Cloudflare deploy remains Git-based; this workflow does not directly deploy.

## Residual risk

This remains a programmatic content system. It can publish at scale, but it still depends on:

- accurate brand/domain registries,
- enough topical breadth in the pantry,
- no manual changes that break site paths,
- no GitHub Actions permission restrictions,
- search engines accepting the quality of the pages over time.

The system is built to slow down when duplicate warnings or hard fails appear.
