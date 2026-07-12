# Authority Network 100K Citation / Impression Strategy

## Objective

Pursue 100,000 combined citation and impression opportunities across the portfolio within six months.

This is not a promise of 100,000 independent backlinks. The objective combines four evidence classes:

1. owned product-repository content surfaces;
2. Authority Network editorial pages and rendered backlinks;
3. genuinely independent mentions and referring domains;
4. measured search impressions, answer-engine citations, and discoverability evidence.

The system never labels a generated page as indexed, live, or cited without evidence.

## Division of labor

### Product repositories

Each product repository may run its own content automation. Those repos should create the majority of owned citation surfaces: educational pages, FAQs, glossaries, use cases, templates, audience pages, and structured answer-engine content.

Each repo may export a manifest using the contract in `data/product-repo-manifests.json`.

### Authority Network

This repository creates useful editorial pages on separate publication domains. It provides contextual backlinks, anchor and destination diversity, local or professional relevance, and a verifiable repository ledger.

The Authority Network is not a mass backlink mill. Pages must remain useful if the backlink is removed.

### Independent acquisition

Vendor pages, partner resources, directories, contributed articles, communities, and earned media provide genuinely separate references. These are outside this repo but belong in the portfolio objective.

## Evidence lifecycle

Backlinks move through these stages only when evidence exists:

`approved_destination → rendered_in_repository → deployed → live_verified → discoverable → indexed`

AI citation evidence is tracked separately. A generated ledger record proves only repository state.

## Growth profiles

Every brand has a profile in `data/brand-growth-profiles.json` containing:

- growth status;
- monthly authority-page target;
- monthly verified-backlink target;
- minimum-presence guidance;
- maximum publication-share guidance;
- scheduler weight.

These values guide scheduling and reporting. Minor variance never blocks release.

## Portfolio scheduler

The normal content allocation uses a weighted deficit model within each approved publication. A brand with lower coverage relative to its configured target receives more opportunity. Contextual fit still controls the final page and link.

The scheduler may produce no link when no destination genuinely fits.

## Measurement

The dashboard separates:

- repository-rendered authority backlinks;
- live-verified backlinks;
- discoverable or indexed referring pages;
- owned product-repo surfaces;
- independent mentions when imported;
- AI citation evidence;
- search or answer-engine impressions.

Run:

```bash
npm run citation:dashboard
```

## Six-month operating cadence

### Weekly

- review brand underrepresentation;
- inspect destination and anchor distribution;
- verify newly deployed backlinks;
- import available product-repo manifests;
- repair broken links or retired destinations.

### Monthly

- compare actual output with growth profiles;
- rebalance targets without turning variance into a blocker;
- assess referring-domain diversity;
- identify brands needing new publication capacity;
- separate owned surfaces from external evidence.

### At six months

Report the objective by evidence class. Do not collapse generated pages, backlinks, indexed pages, and AI citations into one misleading number.
