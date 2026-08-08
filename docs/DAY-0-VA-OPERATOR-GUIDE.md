# Day-0 VA and Operator Guide

## Your job

Your job is to run approved commands, review plain-English receipts, and escalate genuine failures. You do not need to understand the full codebase.

## The four commands you need

### Check current work

```bash
npm run validate:changed
```

Use this while editing. It performs non-destructive page checks and the core safety checks.

### Validate a release

```bash
npm run validate:release
```

Use before committing or deploying. It may repair safe mechanical defects on generated daily pages once, then it rechecks them.

### Run the full uncached proof

```bash
npm run validate:full
```

Use for major releases, after changing templates or validation code, or when a cache concern exists.

### Prove the deterministic rebuild

```bash
npm run validate:clean-rebuild
```

This creates two isolated derived builds and confirms they match.

## How to read the result

### PASS

No blocking issue was found.

### PASS_WITH_SOFT_WARNING

The release is allowed. Typical examples are word-count targets or optional metadata preferences.

### PASS_WITH_STRONG_WARNING

The release is allowed, but a meaningful nonblocking issue needs attention. Generated-page mechanical issues should normally self-repair during release validation.

### FAIL

Stop. This means a real problem such as malformed canonical data, an unsafe claim, a wrong destination, a missing required disclosure, a broken social contract, or an executable error.

## Never “fix” these by weakening validation

- wrong-domain links;
- missing backlink-ledger evidence;
- malformed JSON;
- secret exposure;
- fabricated evidence;
- product/route contradictions;
- unauthorized publication routing.

Repair the source problem instead.

## Safe page self-repair

The release profile may repair generated files inside a `/daily/` folder. The approved repairs are limited to:

- adding a missing `lang="en"` attribute;
- adding a factual meta description derived from the existing H1;
- removing an exact duplicate outbound link.

The repair engine runs once. It cannot invent facts or rewrite editorial meaning.

## Validation cache

The cache lives in `.validation-cache/` and is never committed or packaged.

Clear it safely with:

```bash
npm run cache:clear
```

A missing cache is not an error. A corrupt cache is ignored and the page is validated again.

## Daily content workflow

1. Run the autopilot only through its approved command or workflow.
2. Run release validation.
3. Read `reports/validation-release.json`.
4. Confirm `release_blocked` is `false`.
5. Confirm new pages and links look sensible.
6. Commit through the approved updater or workflow.

## Social posting

Social posting requires real GitHub secrets. A ChatGPT connection does not expose raw LinkedIn or X credentials.

Never paste secrets into source files, reports, screenshots, or chat logs. If credentials are missing, social posting is skipped and recorded as a warning; content generation, backlink publication, validation, and commit continue. Social failures become release-blocking only when `FAIL_ON_SOCIAL_POST_FAILURE=true` is explicitly configured.

## When to escalate

Escalate when:

- validation reports `FAIL`;
- a domain or product route is wrong;
- a secret appears in a file;
- a city publication is active without approval;
- social posting partially succeeds or provider permissions change;
- the clean rebuild differs.

Do not escalate ordinary soft warnings unless they become a persistent editorial quality problem.


## Owner agency dashboard

The owner-facing backlink/operator inventory is generated at:

`https://founderoperatorlibrary.com/agency/`

It is intentionally `noindex` and omitted from public navigation/sitemaps. It shows:

- all canonical publication operators;
- every canonical `npm run` operator currently declared in `package.json`;
- active GitHub workflow operators and schedules;
- every approved target URL, including targets with zero backlinks;
- every Authority Network editorial/backlink recorded for each target URL;
- current repository/live/index evidence state without fabricating external outcomes.

Rebuild it locally with:

```bash
npm run agency:build
```

## v4.6 portfolio citation operations

The goal is a six-month 100K citation/impression objective across all brands. Do not report this as 100K backlinks.

### Every week

1. Run `npm run citation:dashboard`.
2. Review brands with the lowest authority-backlink coverage.
3. Confirm no broken or retired destination is still being used.
4. Run `npm run citation:verify-repo`.
5. Import any configured product-repo manifests with `npm run citation:import-manifests`.

### Evidence language

- `rendered_in_repository` means the link exists in the repo page.
- `live_verified` means someone or an automated verifier observed it on the deployed URL.
- `indexed` requires actual index evidence.
- `ai_cited` requires an observed answer-engine citation or equivalent evidence.

Never manually upgrade a stage just to make the dashboard look better.

### Target variance

Monthly targets are planning guides. Missing a page-count target is not a release failure. Wrong domains, false evidence, unsafe claims, or corrupted state are real failures.
