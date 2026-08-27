#!/usr/bin/env node
/**
 * Deliberate acceptance of published pages into the cadence baseline.
 *
 * The cadence gate blocks when more editorial URLs appear than the weekly cap
 * allows. There are only two honest answers to that block:
 *
 *   1. Do not publish them. This is the answer the cap exists to force, and it
 *      is the right one while the pages are still unpublished.
 *   2. Accept that they are already live, record that you accepted them, and
 *      say why. Pages that are already published cannot be un-published by a
 *      red build, and a gate that stays red over a past action is one people
 *      learn to route around.
 *
 * What is NOT an answer is the third thing that used to happen by accident:
 * cadence_gate.js advanced the ledger itself, every run, so the block cleared
 * on the next invocation with no decision, no record, and nobody's name on it.
 * That is why this file exists and why the gate no longer writes the ledger.
 *
 * Acceptance requires a reason, appends to an auditable log, and is never run
 * by CI - so the cap keeps applying to everything published from here on.
 *
 * Usage:
 *   node scripts/cadence_accept.js --reason "why these pages are being accepted"
 *   node scripts/cadence_accept.js --reason "..." --dry-run
 */
'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = process.cwd();
const args = process.argv.slice(2);
const DRY = args.includes('--dry-run');
const ACCEPTANCES_REL = 'data/cadence/acceptances.json';
const MIN_REASON = 20;

function flag(name) {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : undefined;
}

const reason = (flag('--reason') || '').trim();
if (!reason || reason.startsWith('--')) {
  console.error('cadence:accept requires a reason.');
  console.error('  npm run cadence:accept -- --reason "why this backlog is being accepted"');
  process.exit(2);
}
if (reason.length < MIN_REASON) {
  console.error(`cadence:accept reason must be at least ${MIN_REASON} characters. A reason that does not explain anything is the same as no record at all.`);
  process.exit(2);
}

// Required only after the arguments are known to be good, so that a call with no
// reason is refused on its own merits rather than inheriting whatever the gate
// module does when it is loaded.
const { evaluate, LEDGER_REL } = require('./cadence_gate.js');

const { report, urls, newUrls, newEditorial, newNavigation } = evaluate(ROOT);

if (!newUrls.length) {
  console.log('Nothing to accept: no URLs are new since the ledger was last accepted.');
  process.exit(0);
}

const today = process.env.CADENCE_TODAY || new Date().toISOString().slice(0, 10);
const entry = {
  accepted_at: today,
  reason,
  urls_total_after: urls.size,
  accepted_count: newUrls.length,
  accepted_editorial: newEditorial.length,
  accepted_navigation: newNavigation.length,
  weekly_cap: report.policy.new_pages_per_week,
  over_cap_by: Math.max(0, newEditorial.length - report.policy.new_pages_per_week),
  maintainable_ceiling: report.maintainable_ceiling,
  library_over_ceiling_by: Math.max(0, urls.size - report.maintainable_ceiling),
  accepted_urls: [...newUrls].sort(),
};

console.log(`Accepting ${newUrls.length} URLs into the cadence baseline (${newEditorial.length} editorial, ${newNavigation.length} navigation).`);
console.log(`  weekly cap is ${entry.weekly_cap}; this acceptance is ${entry.over_cap_by} editorial pages over it.`);
if (entry.library_over_ceiling_by > 0) {
  console.log(`  library is ${entry.library_over_ceiling_by} pages above the maintainable ceiling of ${entry.maintainable_ceiling}. Accepting the count does not resolve that.`);
}
console.log(`  reason: ${reason}`);

if (DRY) {
  console.log('\n--dry-run: nothing written.');
  process.exit(0);
}

const ledgerPath = path.join(ROOT, LEDGER_REL);
fs.mkdirSync(path.dirname(ledgerPath), { recursive: true });
fs.writeFileSync(ledgerPath, JSON.stringify({ generated_at: today, urls: [...urls.keys()].sort() }, null, 2) + '\n');

const accPath = path.join(ROOT, ACCEPTANCES_REL);
let log = { acceptances: [] };
if (fs.existsSync(accPath)) {
  try { log = JSON.parse(fs.readFileSync(accPath, 'utf8')); } catch { /* rewrite below */ }
}
if (!Array.isArray(log.acceptances)) log.acceptances = [];
log.acceptances.push(entry);
fs.writeFileSync(accPath, JSON.stringify(log, null, 2) + '\n');

console.log(`\nLedger advanced: ${LEDGER_REL}`);
console.log(`Acceptance recorded: ${ACCEPTANCES_REL} (${log.acceptances.length} total)`);
console.log('Commit both, with the reason in the commit message.');
