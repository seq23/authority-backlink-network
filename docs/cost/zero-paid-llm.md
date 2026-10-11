# Zero paid LLM calls

Owner instruction, 11 Oct 2026: "nothing should be paid … cut the probes and make them free."

## What was paid, and what it is now

| Call site | Ran | Model / provider | What it did | Now |
|---|---|---|---|---|
| `scripts/llm_citation_probe.mjs` in `authority-v4-autopilot.yml` | daily 14:22 UTC | OpenRouter (grounded) | asked 25 queries, checked whether answers cite the publications | **Off.** `paid-citation-probe.yml`, dispatch only, `confirm_paid` |
| `scripts/journalist_query_scan.py` (`journalist-query-scan.yml`) | weekdays 12:00 + 18:15 UTC | OpenRouter `anthropic/claude-sonnet-4.5` | drafts first-hand pitch replies (send stays human) | **Free.** $0 models via `scripts/llm/free_router.py` |
| `scripts/uscis_changelog.py` (`uscis-changelog.yml`) | Tuesdays 13:11 UTC | OpenRouter `anthropic/claude-sonnet-4.5` | describes a USCIS page diff; quotes verified against the diff | **Free.** $0 models via the free router (JSON mode kept) |
| `scripts/authority_v4_autopilot.py` `maybe_gemini_rewrite` | daily, only if `ENABLE_GEMINI_REWRITE` var is true (it is not) | Gemini `gemini-2.5-flash-lite` | optional editorial rewrite | **Free when enabled** (`ENABLE_LLM_REWRITE`), via the free router; Gemini key no longer passed |

The `JOURNALIST_QUERY_MODEL` / `USCIS_CHANGELOG_MODEL` variables that could select a paid model were removed from the workflows and from `trace_github_actions.py`; `--model` is now a receipt label only. `validate_citation_probe_wiring.py` still runs the probe in dry-run (no key, no spend), which the gate leaves open.

## How free is enforced

- `config/llm_routing.json`: ordered $0/$0 model list, pricing snapshot (fetched 2026-10-11 from the unauthenticated `https://openrouter.ai/api/v1/models`), `policy.max_cost_usd: 0`, `paid_fallback: false`.
- `scripts/llm/free_router.*`: the only code allowed to call a model. Every request carries `provider.max_price = 0` (OpenRouter refuses paid endpoints), `usage.cost` is read back and a non-zero cost throws `FREE_ROUTER_COST_VIOLATION` (the run fails). Every call prints `FREE_LLM_RECEIPT {...}` with `outcome`, `model`, `cost_usd`, `key_label` and `key_info` (label, limit, usage, is_free_tier, limit_remaining from `GET /api/v1/auth/key`; never the key).
- Named stops, exit 0: `FREE_ROUTER_NO_KEY`, `OPENROUTER_KEY_DISABLED_OR_INVALID` ("OpenRouter key disabled or invalid; free routing needs an enabled key with a $0 limit"), `NO_FREE_MODEL_ANSWERED`. There is no paid fallback.
- Paid probe lanes call `paidProbeGate()` and stop with `PAID_PROBE_DISABLED_BY_OWNER_POLICY` unless `CONFIRM_PAID=true`, which only `.github/workflows/paid-citation-probe.yml` sets, and only when dispatched with `confirm_paid: true` (default false). That workflow has no schedule.
- Guard: `validate_zero_paid_llm.js` (registered in the repo validation chain). It fails on a non-$0 model or undated snapshot, any script calling a provider outside the router, a probe lane with a schedule or without `confirm_paid`, a scheduled workflow passing a non-router model key or naming a paid model, or `OPENROUTER_API_KEY` given to a step that runs no registered free-router consumer. Each check was proven to fail once against a mutated copy.

## Free models (ordered fallback)

1. `nvidia/nemotron-3-ultra-550b-a55b:free` (1M ctx)
2. `nvidia/nemotron-3-super-120b-a12b:free` (262k ctx)
3. `google/gemma-4-31b-it:free` (262k ctx)
4. `openrouter/free` ($0-only meta-router, last resort)

