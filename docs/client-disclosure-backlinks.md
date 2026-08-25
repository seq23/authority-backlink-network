# Backlink attribution disclosure

**Prepared:** 2026-08-24 · WO-1 · **Not sent.** For human review before any client conversation.

## What changed

Every outbound link from this network to an affiliated property now carries
`rel="sponsored nofollow"`. Nothing else changed: no link was removed, no anchor
text altered, no page unpublished, no disclosure string edited.

## Why

Semrush independently flagged a PBN anchor-text pattern across 13 domains. Before
this change, 19 affiliated domains received followed links from
self-owned publications, with only 28 `nofollow` attributes across 499 pages.
`data/network-rules.json` already declared
`targets_are_locked_to_listed_owned_sites_only: true` — the network was known to be
self-referential; the link attributes did not say so.

Manual action notices for an unnatural-links pattern are delivered to the **linked
site's** Search Console. For `horselegalguide.com` / `wisecovington.com` (Wise
Covington) and `hicksconsulting.org` (Monika Hicks, LCSW) that means the notice
lands with the client, not with us. That is the exposure this closes.

## Effect on search and AI answers

- **Google:** followed links between commonly-owned sites do not earn ranking
  credit and can be treated as a link scheme. Correct attribution removes the risk.
- **AI answer engines:** unaffected. LLMs do not compute PageRank. Citation runs on
  mention and corroboration, and a nofollowed link supplies both in full.

Expect the follow-link count to drop in Ahrefs/Bing. That drop is this change
working as intended, not a new problem.

## Per-domain link counts (indexable pages only)

| Affiliated domain | Links | Attribution now |
|---|---|---|
| approvalprep.com | 270 | `rel="sponsored nofollow"` |
| virtualagency-os.com | 26 | `rel="sponsored nofollow"` |
| aplayermode.com | 24 | `rel="sponsored nofollow"` |
| porchandparty901.com | 21 | `rel="sponsored nofollow"` |
| westpeekproductions.com | 17 | `rel="sponsored nofollow"` |
| weddingbudgetspreadsheet.com | 17 | `rel="sponsored nofollow"` |
| weddingtimelinetemplate.com | 17 | `rel="sponsored nofollow"` |
| diannesplacerecoveryservices.com | 13 | `rel="sponsored nofollow"` |
| billionairehighperformancecoach.com | 11 | `rel="sponsored nofollow"` |
| horselegalguide.com | 11 | `rel="sponsored nofollow"` |
| hicksconsulting.org | 10 | `rel="sponsored nofollow"` |
| hormonesivhair.com | 10 | `rel="sponsored nofollow"` |
| theindustryguides.com | 9 | `rel="sponsored nofollow"` |
| theaccidentguides.com | 9 | `rel="sponsored nofollow"` |
| weddingseatingchartmaker.com | 8 | `rel="sponsored nofollow"` |
| dentistryguides.com | 8 | `rel="sponsored nofollow"` |
| neuroevalguides.com | 8 | `rel="sponsored nofollow"` |
| uscisexam.com | 8 | `rel="sponsored nofollow"` |
| weddingchecklistpdf.com | 7 | `rel="sponsored nofollow"` |

## By publication

| Publication | Affiliated links |
|---|---|
| professional-resources | 356 |
| founder-operator | 78 |
| memphis-local | 70 |

Operator pages under `/agency/` are excluded throughout: they are
`noindex,nofollow,noarchive` and are not published content.

## Enforcement

`scripts/link_audit.py` now fails the release on
`affiliated_link_missing_sponsored_nofollow`. This cannot silently regress: a new
followed affiliated link blocks the build rather than shipping.
