#!/usr/bin/env node
'use strict';
/**
 * Zero-paid-LLM guard. Owner policy, 11 Oct 2026: "nothing should be paid ...
 * cut the probes and make them free." Fails red when:
 *   A. config/llm_routing.json holds a model not priced $0/$0 in its committed
 *      pricing snapshot, lacks a snapshot date, or allows cost / paid fallback;
 *   B. any script talks to a model provider directly instead of through the
 *      free router - unless it is a registered paid probe lane that carries
 *      paidProbeGate / paid_probe_gate;
 *   C. a free-router consumer stops importing the router;
 *   D. a probe lane workflow has a schedule, lacks confirm_paid (default
 *      false), or lacks the refusing named-stop step; any other workflow
 *      invokes a probe script or sets CONFIRM_PAID;
 *   E. a scheduled workflow passes a model key other than OPENROUTER_API_KEY,
 *      or passes OPENROUTER_API_KEY anywhere but a step that runs a registered
 *      free-router consumer.
 * Usage: node validate_zero_paid_llm.js [repo-root]
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(process.argv[2] || process.cwd());
const problems = [];
const fail = (m) => problems.push(m);
const rel = (p) => path.relative(ROOT, p);
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const exists = (p) => fs.existsSync(path.join(ROOT, p));

const PROVIDER_URL = /openrouter\.ai\/api|generativelanguage\.googleapis\.com|api\.openai\.com\/v1|api\.anthropic\.com|api\.perplexity\.ai/;
const PAID_MODEL_SLUG = /\b(anthropic\/claude[\w.-]*|openai\/gpt[\w.-]*|google\/gemini[\w.-]*|perplexity\/[\w.-]+)\b/;
const OTHER_MODEL_KEYS = /\b(GEMINI_API_KEY|GOOGLE_GEMINI_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|PERPLEXITY_API_KEY)\b/;
const ROUTERS = ['scripts/llm/free_router.js', 'scripts/llm/free_router.py'];

// ---------------------------------------------------------------- A. config
let cfg = null;
try { cfg = JSON.parse(read('config/llm_routing.json')); } catch (e) { fail(`config/llm_routing.json unreadable: ${e.message}`); }
if (cfg) {
  const pol = cfg.policy || {};
  if (pol.max_cost_usd !== 0) fail('policy.max_cost_usd must be exactly 0');
  if (pol.paid_fallback !== false) fail('policy.paid_fallback must be false');
  if (!/^https:\/\/openrouter\.ai\/api\/v1\/chat\/completions$/.test(cfg.endpoint || '')) fail('endpoint must be the OpenRouter chat completions URL');
  const snap = cfg.pricing_snapshot || {};
  if (!/^\d{4}-\d{2}-\d{2}/.test(String(snap.fetched_at || ''))) fail('pricing_snapshot.fetched_at must be a date');
  const models = cfg.free_models || [];
  if (models.length < 3 || models.length > 4) fail(`free_models must hold 3-4 ordered models, holds ${models.length}`);
  for (const m of models) {
    const p = (snap.models || {})[m];
    if (!p) { fail(`free model ${m} has no pricing snapshot row`); continue; }
    if (String(p.prompt) !== '0' || String(p.completion) !== '0' || (p.request !== undefined && String(p.request) !== '0')) fail(`model ${m} is not $0 in the snapshot (prompt ${p.prompt}, completion ${p.completion})`);
    if (!(Number(p.context_length) >= 32768)) fail(`model ${m} has context under 32k`);
  }
}
const lanes = (cfg && cfg.paid_probe_lanes) || [];
const consumers = (cfg && cfg.free_router_consumers) || [];
for (const r of ROUTERS.filter(exists)) {
  const src = read(r);
  if (!/max_price/.test(src) || !/FREE_ROUTER_COST_VIOLATION/.test(src) || !/OPENROUTER_KEY_DISABLED_OR_INVALID/.test(src)) fail(`${r} lost its max_price / cost-violation / key-stop guard`);
}
if (!exists(ROUTERS[0]) && !exists(ROUTERS[1])) fail('no free router found under scripts/llm/');

// ------------------------------------------------------- B/C. script scan
const SCAN_DIRS = ['scripts', 'distribution_scripts', '.github/scripts', '_ops', 'functions'];
const files = [];
const walk = (d) => {
  if (!exists(d)) return;
  for (const e of fs.readdirSync(path.join(ROOT, d), { withFileTypes: true })) {
    if (e.name === 'node_modules') continue;
    const p = path.join(d, e.name);
    if (e.isDirectory()) walk(p);
    else if (/\.(c?js|mjs|py|sh|ts)$/.test(e.name)) files.push(p);
  }
};
SCAN_DIRS.forEach(walk);
const laneScripts = new Set(lanes.map((l) => l.script));
for (const f of files) {
  if (ROUTERS.includes(f) || /validate_zero_paid_llm/.test(f) || /(^|\/)tests?\//.test(f) || /test_[^/]*$/.test(f)) continue;
  const src = read(f);
  if (!PROVIDER_URL.test(src)) continue;
  if (laneScripts.has(f)) continue;
  fail(`${f} calls a model provider directly; route it through scripts/llm/free_router or register it as a paid probe lane`);
}
for (const l of lanes) {
  if (!exists(l.script)) { fail(`probe lane script missing: ${l.script}`); continue; }
  if (!/paidProbeGate\(|paid_probe_gate\(/.test(read(l.script))) fail(`probe lane ${l.script} has no paid-probe gate`);
}
for (const c of consumers) {
  if (!exists(c.script)) { fail(`free-router consumer missing: ${c.script}`); continue; }
  const src = read(c.script);
  if (!/free_router/.test(src)) fail(`free-router consumer ${c.script} does not use the free router`);
  if (PROVIDER_URL.test(src)) fail(`free-router consumer ${c.script} also calls a provider directly`);
}

// ------------------------------------------------------------ D/E. workflows
const wfDir = '.github/workflows';
const wfs = exists(wfDir) ? fs.readdirSync(path.join(ROOT, wfDir)).filter((f) => /\.ya?ml$/.test(f)).map((f) => `${wfDir}/${f}`) : [];
const pkgScripts = exists('package.json') ? (JSON.parse(read('package.json')).scripts || {}) : {};
const aliasesFor = (script) => Object.entries(pkgScripts).filter(([, v]) => String(v).includes(script)).map(([k]) => k);
const invokes = (text, script) => text.includes(script) || aliasesFor(script).some((a) => new RegExp(`npm run ${a.replace(/[:.]/g, '\\$&')}(\\s|$|")`, 'm').test(text));
const laneWorkflows = new Set(lanes.map((l) => l.workflow));
const consumerTokens = [...ROUTERS, ...consumers.flatMap((c) => [c.script, ...(c.invoked_by || [])])];

function stepOf(lines, i) {
  const ind = lines[i].search(/\S/);
  let stepsLine = -1;
  for (let j = i; j >= 0; j--) if (/^\s*steps:\s*$/.test(lines[j])) { stepsLine = j; break; }
  if (stepsLine < 0) return null;
  for (let j = i; j > stepsLine; j--) {
    const m = /^(\s*)- /.exec(lines[j]);
    if (m && m[1].length < ind) {
      if (lines.slice(stepsLine + 1, j).some((l) => /^\s{2}\S[^:]*:\s*$/.test(l))) return null;
      let k = j + 1;
      while (k < lines.length && !(lines[k].trim() && lines[k].search(/\S/) <= m[1].length)) k++;
      return lines.slice(j, k).join('\n');
    }
  }
  return null;
}

for (const wf of wfs) {
  const text = read(wf);
  const scheduled = /^\s*schedule:/m.test(text);
  const isLane = laneWorkflows.has(wf);
  if (isLane) {
    if (scheduled) fail(`${wf} is a paid probe lane and has a schedule`);
    const lns = text.split('\n');
    const ci = lns.findIndex((l) => /^\s+confirm_paid:\s*$/.test(l));
    const block = ci < 0 ? [] : lns.slice(ci + 1, ci + 7).filter((l, k, arr) => arr.slice(0, k + 1).every((x) => x.search(/\S/) > lns[ci].search(/\S/) || !x.trim()));
    if (!block.some((l) => /^\s+default:\s*false\s*$/.test(l))) fail(`${wf} lacks a confirm_paid input defaulting to false`);
    if (!/NAMED_STOP: PAID_PROBE_DISABLED_BY_OWNER_POLICY/.test(text) || !/inputs\.confirm_paid/.test(text)) fail(`${wf} lacks the step that refuses with a named stop unless confirm_paid is true`);
    continue;
  }
  for (const l of lanes) if (invokes(text, l.script)) fail(`${wf} invokes probe lane ${l.script}; only its confirm_paid workflow may`);
  if (/CONFIRM_PAID/.test(text)) fail(`${wf} sets CONFIRM_PAID outside a probe lane workflow`);
  if (!scheduled) continue;
  if (PAID_MODEL_SLUG.test(text.split('\n').filter((l) => !/^\s*#/.test(l)).join('\n'))) fail(`${wf} is scheduled and names a paid model (${text.match(PAID_MODEL_SLUG)[1]})`);
  if (OTHER_MODEL_KEYS.test(text)) fail(`${wf} is scheduled and passes a non-router model key (${text.match(OTHER_MODEL_KEYS)[1]})`);
  const lines = text.split('\n');
  lines.forEach((line, i) => {
    if (!/OPENROUTER_API_KEY/.test(line) || /^\s*#/.test(line)) return;
    const step = stepOf(lines, i);
    if (!step) { fail(`${wf}:${i + 1} passes OPENROUTER_API_KEY at job/workflow level; scope it to the free-router step`); return; }
    if (!consumerTokens.some((t) => invokes(step, t) || step.includes(t))) fail(`${wf}:${i + 1} passes OPENROUTER_API_KEY to a step that runs no registered free-router consumer`);
  });
}

if (problems.length) {
  console.error(`zero-paid-llm: ${problems.length} problem(s)`);
  for (const p of problems) console.error(`  - ${p}`);
  process.exit(1);
}
console.log(`zero-paid-llm OK: ${(cfg.free_models || []).length} free models (snapshot ${cfg.pricing_snapshot.fetched_at}), ${lanes.length} probe lane(s) dispatch-only behind confirm_paid, ${consumers.length} free-router consumer(s), ${files.length} scripts and ${wfs.length} workflows scanned.`);
