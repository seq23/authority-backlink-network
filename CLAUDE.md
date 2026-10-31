# Authority Network — rules for anyone working in this repo

This repository publishes three editorial publications as three Cloudflare Pages
projects, one per folder under `sites/`:

| Publication | Domain | Folder |
|---|---|---|
| Founder Operator Library | founderoperatorlibrary.com | `sites/founder-operator` |
| Memphis Vendor Library | memphisvendorlibrary.com | `sites/memphis-local` |
| Professional Resource Library | professionalresourcelibrary.com | `sites/professional-resources` |

`data/publications.json` is the one definition of that table. Read `AGENTS.md`
for the repo-operator entry points, and `docs/WHAT-THIS-SYSTEM-IS.md` for what
the network is for.

## Nothing paid

**Owner policy, 11 Oct 2026: "nothing should be paid … cut the probes and make
them free."** Every model call in this repository goes through the $0-only free
router and **nothing paid** runs on a schedule. The full account of what used to
cost money, what it costs now, and how the rule is enforced in code is
[`docs/cost/zero-paid-llm.md`](docs/cost/zero-paid-llm.md).

In short:

- `config/llm_routing.json` carries `policy.max_cost_usd: 0` and
  `paid_fallback: false`, and every model in it is priced $0/$0 in its committed
  pricing snapshot.
- `scripts/llm/free_router.{js,py}` is the only code allowed to call a model.
  Every request carries `provider.max_price = 0`; a non-zero `usage.cost` throws
  and fails the run.
- The one paid lane, `.github/workflows/paid-citation-probe.yml`, has no
  schedule and refuses to run without `confirm_paid: true`.
- Guard: `npm run validate:zero-paid-llm`, registered in the validation chain.
  It reads this section, so deleting the rule from here fails the build.

## The published tree is generated

`sites/` is committed output. **Never hand-edit a page to fix a title, a
description, a schema node or a link** — the next autopilot run regenerates it
and takes the fix with it. Find the source: a generator in `scripts/`, a data
file in `data/`, the pantry in `content-bank/`, or `scripts/lib/` for anything
that belongs to every page. `scripts/sync_page_meta.py` exists precisely because
scaffold generators do not rewrite a page once it exists.

When several generators have to run, run them in the order
`.github/workflows/authority-v4-autopilot.yml` uses: page meta, strengthening,
navigation, portfolio link rebalance, rel attributes, editorial pages, robots,
chrome. Order is load-bearing and the workflow comments say why.

## Search Readiness

The owner's Search Readiness Checklist audits all three publications every
Monday, and its failures arrive as fix briefs. Several of its items are pinned
here in code rather than in prose:

| Item | Rule | Where |
|---|---|---|
| a1 | one canonical host; every other host 301s to it | `scripts/build_host_canonicalization.py`, `validate_host_canonicalization.py`, `tests/test_host_canonicalization.py` |
| b1, b2 | `<title>` 30–65, meta description 120–160, unique per site | `scripts/lib/meta_description.py`, `validate_page_meta_bounds.py` |
| c1, c2, d4 | Organization with name/url/logo, WebPage on every page, a stated date is a visible date | `scripts/lib/head_seo.py`, `validate_jsonld_types.py` |
| entity | `data/entities/<domain>.json` is the one definition of each editorial company: sameAs holds only real independent profiles (empty until one exists; never the site's own pages), no parent; llms.txt and `/editorial-policy` derive from it | `scripts/lib/head_seo.py`, `scripts/lib/llms_text.py`, `validate_entity_graph.py`, weekly `entity-authority-watch.yml` (`scripts/entity_backlink_watch.py`) |
| delivery | every grid side business in `data/grid-coverage.json` has a rendered network backlink or a named stop | `validate_grid_backlink_coverage.py` |
| earned | `data/earned-mentions.json` is the only evidence for a Wikidata item (>= 2 independent outlets); Wikipedia is earned-only | `scripts/earned_mentions.py`, `validate_earned_mentions.py` |
| g1 | portfolio links are followed; only client and paid links withhold | `data/portfolio-link-policy.json`, `scripts/affiliation.py`, `validate_portfolio_link_policy.py` |
| h4 | post-deploy live check of what the edge serves | `scripts/post_deploy_live_check.py`, `.github/workflows/post-deploy-live-check.yml` |

## Validation

One orchestrator: `python3 scripts/validate.py release` (what CI runs on every
pull request), `changed` for a quicker local pass. A new check is registered in
three places or it does not run: `COMMANDS` in `scripts/validate.py`, the
profiles in `validation/plan.json`, and that file's `severity_matrix` — then
`npm run validation:matrix` to regenerate `_repo_validation_matrix.json`.

Adding an npm script also means `npm run agency:build`, because
`tests/test_recovery_agency_contract.py` requires the operator dashboard to list
every one of them.
