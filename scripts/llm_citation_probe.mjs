#!/usr/bin/env node
/**
 * Ask an answer engine a real question and record whether it cites us.
 *
 * This is the measurement the portfolio did not have. The existing
 * query:test:zero-cost task makes no network calls at all - it prints a
 * worksheet and a CSV for a human to fill in by hand - so nothing has ever
 * observed whether these pages are cited. Every statement about AEO progress up
 * to now has been inference from proxies.
 *
 * Gemini's free tier answers with Google Search grounding, and the response
 * carries the sources it actually grounded on. That is a citation observation:
 * the query, the engine, the domains it cited, and whether any of them are ours.
 * It costs nothing.
 *
 * What this does not claim: one engine is not all engines, grounding metadata is
 * not identical to what a user sees in an AI Overview, and absence on a given
 * day is weak evidence. Runs are recorded individually with timestamps so a
 * trend can be read later rather than a single run being treated as a verdict.
 *
 * Without an API key it exits 0 and records that it was skipped. A measurement
 * tool that fails the build when it cannot measure teaches people to remove it.
 *
 * Usage: node llm_citation_probe.mjs [--queries file] [--limit N] [--dry-run]
 */
import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const argv = process.argv.slice(2);
const arg = (name, dflt) => { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : dflt; };
const DRY = argv.includes('--dry-run');
const MODE = arg('--mode', process.env.CITATION_PROBE_MODE || 'knowledge');
const GROUNDED = MODE === 'grounded';
const LIMIT = Number(arg('--limit', '25'));
const OUT = 'data/signals/llm_citation_observations.json';

const CONFIG_PATH = 'data/signals/citation_probe_config.json';
const config = fs.existsSync(path.join(ROOT, CONFIG_PATH))
  ? JSON.parse(fs.readFileSync(path.join(ROOT, CONFIG_PATH), 'utf8'))
  : {};
const OWNED = (config.owned_domains || []).map((d) => d.toLowerCase().replace(/^www\./, ''));
if (!OWNED.length) {
  console.error(`citation probe: no owned_domains in ${CONFIG_PATH} - cannot tell a citation of ours from anyone else's`);
  process.exit(1);
}

function loadQueries() {
  const file = arg('--queries', config.queries_file || 'data/seo/priority_queries.json');
  const full = path.join(ROOT, file);
  if (!fs.existsSync(full)) return [];
  const raw = JSON.parse(fs.readFileSync(full, 'utf8'));
  const rows = Array.isArray(raw) ? raw : (raw.queries || raw.priority_queries || raw.entries || []);
  return rows.map((r) => (typeof r === 'string' ? r : r.query || r.text || '')).filter(Boolean).slice(0, LIMIT);
}

const hostOf = (u) => { try { return new URL(u).hostname.toLowerCase().replace(/^www\./, ''); } catch { return ''; } };

// Two modes, kept distinct because they measure different things and conflating
// them would overstate what is known.
//
//   knowledge (default) - ask without tools and see whether the model names us
//     unprompted. This measures whether we exist in the model's answer at all.
//     It is free.
//   grounded - ask with Google Search grounding and read the sources the answer
//     was actually built from. This is a real citation observation, and it is
//     the stronger signal, but grounding is not free-tier eligible: it returns
//     quota errors on this key today.
//
// Default is knowledge, because a probe that cannot run costs more than a weaker
// probe that does.
async function ask(query, key, model, grounded) {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${encodeURIComponent(key)}`;
  const body = {
    contents: [{ role: 'user', parts: [{ text: query }] }],
    ...(grounded ? { tools: [{ google_search: {} }] } : {}),
    generationConfig: { temperature: 0 },
  };
  const res = await fetch(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return { ok: false, error: data?.error?.message || `HTTP ${res.status}` };
  const cand = data?.candidates?.[0] || {};
  const meta = cand.groundingMetadata || {};
  // Grounding chunks carry the pages the answer was actually built from. The
  // redirect wrapper Google returns is resolved where a real URI is present.
  const uris = [];
  for (const c of meta.groundingChunks || []) {
    const w = c.web || {};
    if (w.uri) uris.push(w.uri);
    if (w.domain) uris.push(`https://${w.domain}`);
  }
  for (const q of meta.webSearchQueries || []) void q;
  const answer = (cand.content?.parts || []).map((p) => p.text || '').join('\n');
  return { ok: true, answer, uris };
}

const queries = loadQueries();
if (!queries.length) { console.error('citation probe: no queries found'); process.exit(1); }

// OpenRouter is preferred when a key is present: its :free models cost nothing
// and asking several of them is a better sample than asking one. Gemini remains
// supported because it is the only one of the two that can ground an answer in
// live search, which is the stronger measurement when its quota allows.
const orKey = process.env.OPENROUTER_API_KEY || '';
const key = process.env.GEMINI_API_KEY || process.env.GOOGLE_GEMINI_API_KEY || '';
const PROVIDER = arg('--provider', orKey && !GROUNDED ? 'openrouter' : 'gemini');
// Three small models rather than one, because a single model's idiosyncrasies
// are not a measurement.
//
// These are the cheapest tier that actually answers, around two to three cents
// per million tokens - a full portfolio run costs roughly a cent. The genuinely
// free tier was tried first and is not usable for this: several :free models are
// agentic-harness only, others return upstream provider errors or hang with no
// response. A probe that silently reports zero because every model failed is
// worse than one that costs a cent and runs, so reliability wins here. Set
// OPENROUTER_MODELS to override, including back to :free variants.
const OR_MODELS = (process.env.OPENROUTER_MODELS || (config.openrouter_models || []).join(',') ||
  'ibm-granite/granite-4.0-h-micro,inclusionai/ling-3.0-flash,mistralai/mistral-nemo')
  .split(',').map((m) => m.trim()).filter(Boolean);

// Free models are heavily shared and some hang. Without a deadline one slow
// model stalls the whole run, which is how a measurement quietly stops being
// taken. A timed-out model is recorded as an error against that model, not as
// an absence of citations.
const REQUEST_TIMEOUT_MS = Number(process.env.PROBE_TIMEOUT_MS || 25000);
async function withTimeout(fn) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);
  try { return await fn(ctrl.signal); }
  finally { clearTimeout(t); }
}

async function askOpenRouter(query, model) {
  const res = await withTimeout((signal) => fetch('https://openrouter.ai/api/v1/chat/completions', {
    method: 'POST',
    signal,
    headers: { 'content-type': 'application/json', authorization: `Bearer ${orKey}` },
    body: JSON.stringify({ model, temperature: 0, max_tokens: 400, messages: [{ role: 'user', content: query }] }),
  }));
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return { ok: false, error: data?.error?.message || `HTTP ${res.status}` };
  const answer = data?.choices?.[0]?.message?.content || '';
  return { ok: true, answer, uris: [] };
}
const model = process.env.GEMINI_MODEL || 'gemini-3.6-flash';
const now = new Date().toISOString();

const haveKey = PROVIDER === 'openrouter' ? Boolean(orKey) : Boolean(key);
if (!haveKey || DRY) {
  const reason = DRY ? 'dry_run' : 'no_api_key';
  console.log(`citation probe: skipped (${reason}); mode=${MODE}; ${queries.length} queries ready, owned domains: ${OWNED.join(', ')}`);
  process.exit(0);
}

const observations = [];
// One model can be idiosyncratic. Asking several and reporting each separately
// says more than averaging them into a single number would.
const engines = PROVIDER === 'openrouter' ? OR_MODELS : [model];
for (const q of queries) {
 for (const engineModel of engines) {
  let r;
  try {
    r = PROVIDER === 'openrouter' ? await askOpenRouter(q, engineModel) : await ask(q, key, engineModel, GROUNDED);
  } catch (e) { r = { ok: false, error: String(e.message || e) }; }
  if (!r.ok) {
    observations.push({ query: q, engine: `${PROVIDER}:${engineModel}`, mode: MODE, observed_at: now, status: 'provider_error', error: r.error });
    console.log(`  ERROR  ${engineModel} :: ${q} :: ${String(r.error).slice(0, 70)}`);
    continue;
  }
  const domains = [...new Set(r.uris.map(hostOf).filter(Boolean))];
  const ours = domains.filter((d) => OWNED.some((o) => d === o || d.endsWith(`.${o}`)));
  // In knowledge mode there are no grounded sources, so presence means the model
  // named the brand or domain in its own answer.
  const answerLower = (r.answer || '').toLowerCase();
  const named = OWNED.filter((o) => answerLower.includes(o) || answerLower.includes(o.split('.')[0]));
  observations.push({
    query: q, engine: `${PROVIDER}:${engineModel}`, mode: MODE, observed_at: now,
    status: 'observed',
    cited_domains: domains,
    cited_ours: ours,
    self_cited: GROUNDED ? ours.length > 0 : named.length > 0,
    named_in_answer: named,
    answer_mentions_brand: named.length > 0,
  });
  const hit = GROUNDED ? ours.length > 0 : named.length > 0;
  console.log(`  ${hit ? 'PRESENT' : '   --  '} ${engineModel.split('/').pop()} :: ${q}${hit ? ` (${(GROUNDED ? ours : named).join(', ')})` : ''}`);
 }
}

const prior = fs.existsSync(path.join(ROOT, OUT))
  ? JSON.parse(fs.readFileSync(path.join(ROOT, OUT), 'utf8'))
  : { schema_version: '1.0', runs: [] };
prior.runs = (prior.runs || []).slice(-49);
prior.runs.push({ run_at: now, provider: PROVIDER, engines, mode: MODE, queries: queries.length, observations });

const cited = observations.filter((o) => o.self_cited).length;
const errored = observations.filter((o) => o.status === 'provider_error').length;
prior.latest_summary = {
  run_at: now, provider: PROVIDER, engines, mode: MODE,
  queries: queries.length, observations: observations.length, self_cited: cited, errored,
  _mode_note: GROUNDED
    ? 'grounded: counted when the answer was built from one of our pages'
    : 'knowledge: counted when the model named us unprompted, with no retrieval. Weaker than a citation and must not be reported as one.',
  self_cited_rate_pct: observations.length ? Number(((100 * cited) / observations.length).toFixed(1)) : 0,
};

fs.mkdirSync(path.join(ROOT, path.dirname(OUT)), { recursive: true });
fs.writeFileSync(path.join(ROOT, OUT), JSON.stringify(prior, null, 2) + '\n');
console.log(`citation probe [${PROVIDER}/${MODE}]: ${cited}/${observations.length} observations named one of our domains (${prior.latest_summary.self_cited_rate_pct}%); ${errored} provider error(s). Recorded in ${OUT}`);
