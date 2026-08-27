#!/usr/bin/env node
/**
 * The cadence gate must be able to block twice.
 *
 * This exists because it could not. cadence_gate.js used to rewrite
 * data/cadence/known_urls.json - the ledger that is the sole input distinguishing
 * a new page from an existing one - as a side effect of running. The observed
 * behaviour on a real blocked tree was:
 *
 *   $ node scripts/cadence_gate.js   ->  CADENCE GATE BLOCKED ... exit 1
 *   $ node scripts/cadence_gate.js   ->  CADENCE GATE CLEAR   ... exit 0
 *
 * with nothing else changed. The publishing cap was therefore unenforceable:
 * running the check consumed the evidence the check was reading. Anyone who ran
 * it, saw red, and ran it again saw green; any process that ran it before
 * committing silently committed the acceptance.
 *
 * This validator asserts the property that failure violated:
 *
 *   1. Running the gate does not modify the ledger. Byte comparison.
 *   2. Running the gate twice yields the same verdict and the same new-URL
 *      counts. A check whose result depends on how many times it has run is not
 *      a check.
 *   3. The gate is actually invoked by a workflow. A gate nothing calls is the
 *      documented prior state of this file across nine repositories, and it is
 *      indistinguishable from having no gate at all.
 *   4. Acceptance is a separate, reason-bearing command, and CI does not run it.
 *      If CI could accept, the block would clear itself again by another route.
 *
 * It deliberately does not care whether the gate currently passes or blocks.
 * Freshness and volume are the gate's business; this is only about whether the
 * gate is capable of holding a verdict.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = process.cwd();
const LEDGER = path.join(ROOT, 'data/cadence/known_urls.json');
const GATE = 'scripts/cadence_gate.js';
const ACCEPT = 'scripts/cadence_accept.js';
const WORKFLOWS = path.join(ROOT, '.github/workflows');

const failures = [];

function runGate() {
  try {
    const stdout = execFileSync('node', [GATE, '--json'], { cwd: ROOT, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
    return { exit: 0, report: JSON.parse(stdout) };
  } catch (err) {
    if (typeof err.status !== 'number') throw err;
    let report = null;
    try { report = JSON.parse(err.stdout); } catch { /* reported below */ }
    return { exit: err.status, report };
  }
}

// --- 1 & 2: the gate holds its verdict and leaves the ledger alone -----------
if (!fs.existsSync(LEDGER)) {
  failures.push(`ledger_missing: ${path.relative(ROOT, LEDGER)} does not exist, so "new since last accepted" is unanswerable and the weekly cap cannot fire at all`);
} else {
  const before = fs.readFileSync(LEDGER);

  const first = runGate();
  const afterFirst = fs.readFileSync(LEDGER);
  if (!before.equals(afterFirst)) {
    failures.push('gate_mutates_ledger: running the cadence gate rewrote data/cadence/known_urls.json. The gate reads that file to decide what is new, so writing it means the next run cannot see what this run blocked on. Accepting a backlog belongs in cadence:accept, which records a reason.');
  }

  const second = runGate();
  const afterSecond = fs.readFileSync(LEDGER);
  if (!afterFirst.equals(afterSecond)) {
    failures.push('gate_mutates_ledger: the second cadence gate run rewrote data/cadence/known_urls.json.');
  }

  if (first.exit !== second.exit) {
    failures.push(`gate_not_idempotent: two consecutive runs with no change between them exited ${first.exit} then ${second.exit}. A gate that clears itself on a retry cannot enforce anything.`);
  }
  if (first.report && second.report) {
    if (first.report.status !== second.report.status) {
      failures.push(`gate_not_idempotent: status changed from ${first.report.status} to ${second.report.status} across two identical runs.`);
    }
    if (first.report.new_editorial_urls !== second.report.new_editorial_urls) {
      failures.push(`gate_not_idempotent: new_editorial_urls changed from ${first.report.new_editorial_urls} to ${second.report.new_editorial_urls} across two identical runs.`);
    }
  } else {
    failures.push('gate_no_receipt: the cadence gate did not emit a parseable --json report, so its verdict cannot be checked.');
  }
}

// --- 3: the gate is wired to something ---------------------------------------
function workflowFiles() {
  if (!fs.existsSync(WORKFLOWS)) return [];
  return fs.readdirSync(WORKFLOWS).filter((f) => /\.ya?ml$/i.test(f)).map((f) => path.join(WORKFLOWS, f));
}
const wfs = workflowFiles();
const invoking = wfs.filter((f) => /cadence:gate/.test(fs.readFileSync(f, 'utf8')));
if (!invoking.length) {
  failures.push('gate_not_registered: no workflow in .github/workflows invokes `npm run cadence:gate`. A gate nothing runs is not a gate.');
}

// --- 4: acceptance is deliberate, and CI cannot perform it -------------------
if (!fs.existsSync(path.join(ROOT, ACCEPT))) {
  failures.push(`accept_missing: ${ACCEPT} does not exist, so the only way past a cadence block is to edit the ledger by hand or weaken the policy.`);
} else {
  try {
    execFileSync('node', [ACCEPT], { cwd: ROOT, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
    failures.push('accept_without_reason: cadence:accept succeeded with no --reason. Acceptance must carry a recorded justification.');
  } catch (err) {
    if (err.status !== 2) {
      failures.push(`accept_without_reason: cadence:accept exited ${err.status} with no --reason; expected 2 (refusal).`);
    }
  }
}
const ciAccepts = wfs.filter((f) => /cadence:accept/.test(fs.readFileSync(f, 'utf8')));
if (ciAccepts.length) {
  failures.push(`ci_can_accept: ${ciAccepts.map((f) => path.basename(f)).join(', ')} invokes cadence:accept. If CI can advance the ledger, the cap clears itself exactly as it did when the gate wrote the ledger.`);
}

const receipt = {
  validator: 'cadence_gate_integrity',
  status: failures.length ? 'FAIL' : 'PASS',
  hard_failures: failures.length,
  strong_warnings: 0,
  soft_warnings: 0,
  gate_invoked_by: invoking.map((f) => path.basename(f)),
  failures,
};
console.log(JSON.stringify(receipt, null, 2));
process.exit(failures.length ? 1 : 0);
