# Final Hostile Review Manifest

Generated for the targeted Authority Network zip.

## Target domains locked in `data/brands.json`

These are the only backlink/citation targets configured:

1. `theindustryguides.com`
2. `theaccidentguides.com`
3. `dentistryguides.com`
4. `hormonesivhair.com`
5. `neuroevalguides.com`
6. `uscisexam.com`
7. `billionairehighperformancecoach.com`
8. `aplayermode.com`
9. `virtualagency-os.com`
10. `westpeekproductions.com`
11. `horselegalguide.com`
12. `hicksconsulting.org`
13. `porchandparty901.com`

## New publication domains assumed in `data/publications.json`

These are the three domains the repo assumes you may buy and connect to Cloudflare Pages:

1. `founderoperatorlibrary.com`
2. `memphisvendorlibrary.com`
3. `professionalresourcelibrary.com`

## Routing rules verified

- Founder/Operator publication points only to A Player Mode, Billionaire High Performance Coach, Virtual Agency OS, and West Peek Productions.
- Memphis publication points only to Porch & Party from the target set.
- Professional Resource publication points only to The Industry Guides, the five canonical guide sites, Horse Legal Guide, and Hicks Consulting.
- The Industry Guides/canonical direction rule is documented and enforced in registry review: canonicals may not point back to The Industry Guides through approved target links.
- No non-registry external target domains are allowed in HTML pages, except `schema.org` inside JSON-LD context.
- Social drafts remain draft-only and require human approval.

## Final validation commands run

```bash
python3 scripts/hostile_review.py
python3 scripts/link_audit.py
```

Expected result:

- Hostile Review: `PASS`
- Link Audit: `PASS`
- Link violations: `0`
- Hostile review warnings: `0`

## Important remaining human setup

Before deploying, add these GitHub repository secrets:

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`

Then create Cloudflare Pages projects named:

- `authority-founder`
- `authority-memphis`
- `authority-professional`

or edit `.github/workflows/deploy-*.yml` to match your preferred Cloudflare project names.
