#!/usr/bin/env node
/**
 * Cadence gate.
 *
 * The previous gate asked whether pages were earning Google impressions before
 * allowing more publishing. That is the wrong question for an AEO goal: AI
 * citation and Google rank are largely decoupled - most pages AI engines cite do
 * not rank in Google's top 10 - so a page can be invisible in Search and still be
 * cited, or rank and never be cited. Gating publication on Search surfacing
 * measured the wrong thing, and because it never returned a non-zero exit it
 * could not have stopped anything anyway.
 *
 * This gates on freshness and volume, which are the two levers the evidence
 * actually ties to citation:
 *
 *   - Pages not updated within 13 weeks are markedly more likely to lose AI
 *     citations, and recency correlates strongly with being cited at all.
 *   - Publishing faster than a library can be maintained guarantees the tail
 *     ages past that threshold. The ceiling is therefore not a taste question:
 *     it is refresh capacity multiplied by the refresh window.
 *
 * Four blocking conditions, each with an exit code so a pipeline can act on it:
 *
 *   1. new pages in the last 7 days above the weekly cap
 *   2. share of pages older than the refresh window above the tolerance
 *   3. URLs with no lastmod at all - a crawler gets no freshness signal
 *   4. library larger than refresh capacity can keep inside the window
 *
 * It also warns, without blocking, when a very high share of pages carry the
 * same recent lastmod. That is the signature of a date bump rather than a
 * substantive refresh, and it is worth seeing rather than being rewarded by the
 * freshness rules above.
 *
 * THIS SCRIPT IS READ-ONLY WITH RESPECT TO THE LEDGER, AND THAT IS LOAD-BEARING.
 *
 * It used to advance data/cadence/known_urls.json as a side effect of running,
 * on the reasoning that the ledger is "a record of what exists, not a reward for
 * passing". The effect was the opposite of the intent: because the ledger is the
 * only thing that distinguishes a new page from an existing one, writing it
 * during the check meant the check cleared itself. Running the gate twice with
 * no other change produced BLOCKED then CLEAR. Any developer who ran it, looked
 * at the failure, and ran it again saw a pass; any agent that ran it before
 * committing baked the acceptance into the commit without ever deciding to.
 * A gate that erases the evidence it just gated on cannot block anything, which
 * is the same defect this file's header describes in the gate it replaced.
 *
 * Accepting a backlog into the baseline is a real and sometimes correct act -
 * pages that are already published and live cannot be un-published by a CI
 * failure, and a permanently red gate is one people route around. But it is a
 * decision, so it now has to be made deliberately: `npm run cadence:accept --
 * --reason "..."` advances the ledger and records what was accepted and why in
 * data/cadence/acceptances.json. CI never runs it.
 *
 * Usage: node cadence_gate.js [--json] [--policy path]
 */
'use strict';
const fs = require('fs');
const path = require('path');

const DEFAULT_POLICY = {
  refresh_window_days: 91,      // the 13-week threshold
  high_value_window_days: 30,
  stale_tolerance_pct: 20,
  new_pages_per_week: 2,
  refresh_capacity_per_week: 25,
  require_lastmod: true,
};

const LEDGER_REL = 'data/cadence/known_urls.json';

function loadPolicy(ROOT, policyPath) {
  const f = path.join(ROOT, policyPath);
  if (!fs.existsSync(f)) return { ...DEFAULT_POLICY, _source: 'defaults' };
  return { ...DEFAULT_POLICY, ...JSON.parse(fs.readFileSync(f, 'utf8')), _source: policyPath };
}

function sitemapUrls(ROOT) {
  const found = new Map();
  const walk = (dir, depth = 0) => {
    if (depth > 4) return;
    let ents; try { ents = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const e of ents) {
      if (/^(node_modules|\.git|\.pages-output|coverage)$/.test(e.name)) continue;
      const full = path.join(dir, e.name);
      if (e.isDirectory()) walk(full, depth + 1);
      else if (/^sitemap.*\.xml$/i.test(e.name)) {
        const xml = fs.readFileSync(full, 'utf8');
        for (const m of xml.matchAll(/<url>([\s\S]*?)<\/url>/g)) {
          const loc = (m[1].match(/<loc>(.*?)<\/loc>/) || [])[1];
          if (!loc) continue;
          const lm = (m[1].match(/<lastmod>(\d{4}-\d{2}-\d{2})/) || [])[1] || null;
          const prev = found.get(loc);
          if (prev === undefined || (lm && (!prev || lm > prev))) found.set(loc, lm);
        }
      }
    }
  };
  walk(ROOT);
  return found;
}

// Topic hubs are generated navigation over pages that already exist, not new
// editorial surface. data/topic-taxonomy.json and data/publications.json give
// their exact URLs - this is not a path heuristic - and they are held out of the
// weekly publishing cap for one reason: the cap exists because publishing faster
// than the library can be refreshed pushes the tail out of the citable window,
// and a hub adds nothing to refresh. Its content is the membership of pages that
// are already counted, and it is rewritten whenever that membership changes.
// They are still counted in urls.size, so they still press on the ceiling
// warning, and they are reported separately rather than disappearing.
function navigationUrls(ROOT) {
  const out = new Set();
  const read = (rel) => {
    const f = path.join(ROOT, rel);
    return fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, 'utf8')) : null;
  };
  const taxonomy = read('data/topic-taxonomy.json');
  const publications = read('data/publications.json');
  if (!taxonomy || !publications) return out;
  const domainById = new Map(publications.map((p) => [p.id, p.working_domain]));
  for (const [pubId, entry] of Object.entries(taxonomy.publications || {})) {
    const domain = domainById.get(pubId);
    if (!domain) continue;
    for (const hub of entry.hubs || []) out.add(`https://${domain}/topics/${hub.slug}`);
  }
  return out;
}

function readLedger(ROOT) {
  const ledgerPath = path.join(ROOT, LEDGER_REL);
  if (!fs.existsSync(ledgerPath)) return { exists: false, urls: new Set() };
  try {
    return { exists: true, urls: new Set(JSON.parse(fs.readFileSync(ledgerPath, 'utf8')).urls || []) };
  } catch {
    return { exists: false, urls: new Set() };
  }
}

/**
 * Everything the gate knows, with no side effects. cadence_accept.js reuses this
 * so that what gets accepted is by construction what the gate blocked on.
 */
function evaluate(ROOT, policyPath = 'data/cadence/policy.json') {
  const policy = loadPolicy(ROOT, policyPath);
  const urls = sitemapUrls(ROOT);
  const today = new Date(process.env.CADENCE_TODAY || new Date().toISOString().slice(0, 10));
  const ageDays = (d) => Math.floor((today - new Date(d)) / 86400000);

  // A page that changed is not a page that was published. Counting any recent
  // lastmod as a new page made a one-off structural edit across the library look
  // like a publishing spree, which is exactly the signal this is meant to
  // distinguish. New means a URL that was not in the ledger.
  const ledger = readLedger(ROOT);
  const newUrls = [...urls.keys()].filter((u) => !ledger.urls.has(u));

  const navigation = navigationUrls(ROOT);
  const newNavigation = newUrls.filter((u) => navigation.has(u));
  const newEditorial = newUrls.filter((u) => !navigation.has(u));

  const dated = [...urls.entries()].filter(([, d]) => d);
  const undated = [...urls.entries()].filter(([, d]) => !d);
  const ages = dated.map(([, d]) => ageDays(d));
  const stale = ages.filter((a) => a > policy.refresh_window_days).length;
  const fresh30 = ages.filter((a) => a <= policy.high_value_window_days).length;
  const publishedThisWeek = ages.filter((a) => a <= 7).length;
  const stalePct = dated.length ? (100 * stale) / dated.length : 0;
  const ceiling = policy.refresh_capacity_per_week * Math.floor(policy.refresh_window_days / 7);

  const blocking = [];
  const warnings = [];

  if (ledger.exists && newEditorial.length > policy.new_pages_per_week) {
    blocking.push(`weekly_cap: ${newEditorial.length} editorial URLs are new since the ledger was last accepted, cap is ${policy.new_pages_per_week} per week`);
  }
  if (stalePct > policy.stale_tolerance_pct) {
    blocking.push(`refresh_debt: ${stale} of ${dated.length} pages (${stalePct.toFixed(0)}%) are older than ${policy.refresh_window_days} days, tolerance is ${policy.stale_tolerance_pct}%`);
  }
  if (undated.length) {
    const msg = `no_freshness_signal: ${undated.length} sitemap URLs have no lastmod, so a crawler cannot tell when they changed`;
    if (policy.require_lastmod) blocking.push(msg);
    else warnings.push(`${msg} (reported only: ${policy._lastmod_note || 'enforcement disabled for this repo'})`);
  }
  if (urls.size > ceiling) {
    // Reported, not blocking. A library above the ceiling is a strategic problem -
    // the tail cannot be kept inside the refresh window, so it decays toward zero
    // citation value - but it is not something a publish step can fix, and a gate
    // that is permanently red teaches people to ignore it. It has to be worked
    // down by pruning or by raising real refresh capacity.
    warnings.push(`library_over_ceiling: ${urls.size} pages against a ceiling of ${ceiling} (${policy.refresh_capacity_per_week} substantive refreshes per week held inside ${policy.refresh_window_days} days). ${urls.size - ceiling} pages cannot be kept current at this capacity.`);
  }
  if (dated.length && publishedThisWeek === dated.length && dated.length > 20) {
    warnings.push(`uniform_lastmod: ${publishedThisWeek} of ${dated.length} pages share a lastmod inside 7 days - that is a date bump pattern, not a refresh, and it makes the freshness signal meaningless`);
  }
  if (dated.length && fresh30 === 0) {
    warnings.push('no_recent_refresh: nothing has been updated in the last 30 days, where recency correlates most strongly with citation');
  }

  const report = {
    generated_at: today.toISOString().slice(0, 10),
    policy_source: policy._source,
    urls: urls.size,
    dated: dated.length,
    undated: undated.length,
    stale_over_window: stale,
    stale_pct: Number(stalePct.toFixed(1)),
    fresh_within_30d: fresh30,
    lastmod_within_7d: publishedThisWeek,
    new_since_last_run: ledger.exists ? newUrls.length : null,
    new_editorial_urls: ledger.exists ? newEditorial.length : null,
    new_navigation_urls: ledger.exists ? newNavigation.length : null,
    ledger_initialised: ledger.exists,
    maintainable_ceiling: ceiling,
    policy: { ...policy, _source: undefined },
    blocking,
    warnings,
    status: blocking.length ? 'BLOCKED' : 'CLEAR',
  };

  return { report, policy, urls, navigation, newUrls, newEditorial, newNavigation, ledger };
}

function main() {
  const ROOT = process.cwd();
  const args = process.argv.slice(2);
  const JSON_ONLY = args.includes('--json');
  const i = args.indexOf('--policy');
  const policyPath = i >= 0 ? args[i + 1] : 'data/cadence/policy.json';

  const { report, policy, urls, newEditorial, newNavigation, ledger } = evaluate(ROOT, policyPath);

  // The report is an output of the check, not its input, so writing it does not
  // change what the next run sees. The ledger is the input, and the gate must
  // never write it - see the header.
  fs.mkdirSync(path.join(ROOT, 'reports/cadence'), { recursive: true });
  fs.writeFileSync(path.join(ROOT, 'reports/cadence/cadence-gate.json'), JSON.stringify(report, null, 2) + '\n');

  if (JSON_ONLY) console.log(JSON.stringify(report, null, 2));
  else {
    console.log(`CADENCE GATE ${report.status}: ${urls.size} urls; ${report.stale_over_window} past ${policy.refresh_window_days}d (${report.stale_pct}%); ${report.fresh_within_30d} fresh within ${policy.high_value_window_days}d; ceiling ${report.maintainable_ceiling}`);
    if (ledger.exists) console.log(`  new since last accepted: ${newEditorial.length} editorial, ${newNavigation.length} navigation`);
    for (const b of report.blocking) console.log(`  BLOCK  ${b}`);
    for (const w of report.warnings) console.log(`  WARN   ${w}`);
    if (report.blocking.length) {
      console.log('');
      console.log('  To accept already-published pages into the baseline deliberately:');
      console.log('    npm run cadence:accept -- --reason "why this backlog is being accepted"');
    }
  }
  process.exit(report.blocking.length ? 1 : 0);
}

module.exports = { evaluate, sitemapUrls, navigationUrls, readLedger, loadPolicy, LEDGER_REL };

if (require.main === module) main();
