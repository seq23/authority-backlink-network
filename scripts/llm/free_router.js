'use strict';
/**
 * Free-only LLM router. Owner policy, 11 Oct 2026: "nothing should be paid".
 *
 * Every model call in this repo goes through here, and here only reaches
 * OpenRouter models priced $0/$0 (config/llm_routing.json, with the pricing
 * snapshot it was chosen from). Three independent guards keep it free:
 *   1. the model list holds only snapshot-priced $0 models (validated in CI);
 *   2. every request carries provider.max_price = 0, so OpenRouter itself
 *      refuses to route to a paid endpoint;
 *   3. usage.cost is read back on every answer and a non-zero cost throws
 *      FREE_ROUTER_COST_VIOLATION (the run fails loudly).
 * When no free model answers it returns a named stop and never falls back to a
 * paid model. A disabled or invalid key is its own named stop, distinct from
 * "no free model answered", so a receipt can never confuse the two.
 *
 * Paid observation lanes (citation probes, live search observers) are off by
 * owner policy; paidProbeGate() is the single switch that lets one run only
 * when a human dispatches it with confirm_paid=true.
 */
const fs = require('fs');
const path = require('path');

const CONFIG_REL = 'config/llm_routing.json';
const KEY_STOP = 'OPENROUTER_KEY_DISABLED_OR_INVALID';
const KEY_STOP_DETAIL = 'OpenRouter key disabled or invalid; free routing needs an enabled key with a $0 limit';

class FreeRouterCostViolation extends Error {}

function loadConfig(root) {
  const base = root || path.resolve(__dirname, '..', '..');
  return JSON.parse(fs.readFileSync(path.join(base, CONFIG_REL), 'utf8'));
}

function assertFreeConfig(cfg) {
  if (!cfg || !cfg.policy || cfg.policy.max_cost_usd !== 0 || cfg.policy.paid_fallback !== false) {
    throw new FreeRouterCostViolation('FREE_ROUTER_COST_VIOLATION: config/llm_routing.json policy must be max_cost_usd 0 and paid_fallback false');
  }
  const snap = (cfg.pricing_snapshot && cfg.pricing_snapshot.models) || {};
  for (const m of cfg.free_models || []) {
    const p = snap[m];
    if (!p || String(p.prompt) !== '0' || String(p.completion) !== '0') {
      throw new FreeRouterCostViolation(`FREE_ROUTER_COST_VIOLATION: ${m} is not priced $0/$0 in the committed snapshot`);
    }
  }
  if (!(cfg.free_models || []).length) throw new FreeRouterCostViolation('FREE_ROUTER_COST_VIOLATION: no free models configured');
}

function emit(receipt) {
  console.log(`FREE_LLM_RECEIPT ${JSON.stringify(receipt)}`);
  if (receipt.stop) console.log(`NAMED_STOP: ${receipt.stop} - ${receipt.stop_detail}`);
}

function isKeyRefusal(status, message) {
  if (status === 401) return true;
  return status === 403 && /key|disabled|limit|credit|unauthori[sz]ed/i.test(String(message || '')) && !/model|provider|region/i.test(String(message || ''));
}

// GET /api/v1/auth/key once per process. Only label, limit, usage,
// is_free_tier and limit_remaining are kept - never the key itself - so every
// receipt names which key (and whose account) answered.
const KEY_FIELDS = ['label', 'limit', 'usage', 'is_free_tier', 'limit_remaining'];
let keyCheck = null;
async function checkKey(key, timeoutMs) {
  if (keyCheck) return keyCheck;
  try {
    const r = await fetch('https://openrouter.ai/api/v1/auth/key', { headers: { authorization: `Bearer ${key}` }, signal: AbortSignal.timeout(timeoutMs) });
    const raw = await r.text().catch(() => '');
    let data = {};
    try { data = (JSON.parse(raw) || {}).data || {}; } catch { data = {}; }
    const info = {};
    for (const f of KEY_FIELDS) info[f] = data[f] === undefined ? null : data[f];
    keyCheck = { ok: !isKeyRefusal(r.status, raw), http_status: r.status, info };
  } catch (e) {
    keyCheck = { ok: true, http_status: null, info: null, note: `key preflight unreachable: ${e.message}` };
  }
  return keyCheck;
}

async function freeChat({ messages, max_tokens = 1500, temperature = 0.2, purpose = 'unspecified', timeoutMs = 120000, env = process.env, root } = {}) {
  const cfg = loadConfig(root);
  assertFreeConfig(cfg);
  const receipt = { purpose, policy: 'free_only', max_cost_usd: 0, at: new Date().toISOString(), outcome: null, model: null, cost_usd: null, key_label: null, key_info: null, attempts: [] };
  const key = String(env.OPENROUTER_API_KEY || '').trim();
  const stop = (code, detail, outcome) => { receipt.outcome = outcome; receipt.stop = code; receipt.stop_detail = detail; emit(receipt); return { ok: false, stop: code, receipt }; };
  if (!key) return stop('FREE_ROUTER_NO_KEY', 'OPENROUTER_API_KEY is not set for this step; no model was called and nothing was paid', 'credential_missing');
  const kc = await checkKey(key, Math.min(timeoutMs, 20000));
  receipt.key_label = kc.info ? kc.info.label : null;
  receipt.key_info = kc.info;
  if (!kc.ok) return stop(KEY_STOP, `${KEY_STOP_DETAIL} (GET /api/v1/auth/key HTTP ${kc.http_status})`, 'credential_refused');
  for (const model of cfg.free_models) {
    let res; let data;
    try {
      res = await fetch(cfg.endpoint, {
        method: 'POST',
        headers: { authorization: `Bearer ${key}`, 'content-type': 'application/json' },
        body: JSON.stringify({ model, messages, max_tokens, temperature, usage: { include: true }, provider: { max_price: { prompt: 0, completion: 0, request: 0 } } }),
        signal: AbortSignal.timeout(timeoutMs),
      });
      data = await res.json().catch(() => ({}));
    } catch (e) {
      receipt.attempts.push({ model, status: 'error', error: String(e.message || e).slice(0, 200) });
      continue;
    }
    if (!res.ok || data.error) {
      const msg = String((data.error && data.error.message) || '').slice(0, 200);
      receipt.attempts.push({ model, status: 'refused', http_status: res.status, error: msg });
      if (isKeyRefusal(res.status, msg)) return stop(KEY_STOP, `${KEY_STOP_DETAIL} (HTTP ${res.status} on ${model})`, 'credential_refused');
      continue;
    }
    const reported = data.usage ? data.usage.cost : undefined;
    if (reported !== undefined && reported !== null && Number(reported) !== 0) {
      receipt.attempts.push({ model, status: 'cost_violation', cost_usd: reported });
      emit(receipt);
      throw new FreeRouterCostViolation(`FREE_ROUTER_COST_VIOLATION: ${model} reported cost ${reported} USD; the free-only policy allows 0`);
    }
    const choice = (data.choices && data.choices[0]) || {};
    const content = (choice.message && choice.message.content) || '';
    if (!String(content).trim()) { receipt.attempts.push({ model, status: 'empty' }); continue; }
    receipt.attempts.push({ model, status: 'ok' });
    receipt.outcome = 'free_model_answered';
    receipt.model = data.model || model;
    receipt.cost_usd = reported === undefined ? null : Number(reported);
    emit(receipt);
    return { ok: true, content, model: receipt.model, finish_reason: choice.finish_reason || null, receipt };
  }
  return stop('NO_FREE_MODEL_ANSWERED', `none of ${cfg.free_models.length} free models answered; no paid fallback exists by owner policy`, 'no_free_model_answered');
}

function paidProbeGate(lane, env = process.env) {
  if (String(env.CONFIRM_PAID || '').toLowerCase() === 'true') {
    console.log(`PAID_PROBE_CONFIRMED: ${lane} runs because a human dispatched it with confirm_paid=true`);
    return true;
  }
  console.log(`NAMED_STOP: PAID_PROBE_DISABLED_BY_OWNER_POLICY - ${lane} calls a paid model to observe this loop's own output; off by owner policy (11 Oct 2026). Dispatch its workflow with confirm_paid=true to run it once.`);
  return false;
}

module.exports = { freeChat, paidProbeGate, loadConfig, assertFreeConfig, FreeRouterCostViolation, KEY_STOP };

if (require.main === module && process.argv.includes('--selftest')) {
  freeChat({ messages: [{ role: 'user', content: 'Reply with the single word OK.' }], max_tokens: 200, temperature: 0, purpose: 'selftest' })
    .then(() => process.exit(0))
    .catch((e) => { console.error(e.message); process.exit(1); });
}
