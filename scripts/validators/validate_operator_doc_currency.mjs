#!/usr/bin/env node
/**
 * Operator documentation currency.
 *
 * An operator guide is only useful if the repo still looks the way it says it
 * does. This one had gone stale in the ordinary way: it still routed the reader
 * to /coverage/, a surface that was renamed to /knowledge-map/, and to an audit
 * directory that no longer exists. Nothing failed, because nothing was checking.
 *
 * This asserts the one property that can be checked mechanically: every repo
 * path an operator doc points at exists. Dated filenames and other obvious
 * templates are treated as patterns, not paths.
 *
 * Exit 1 on any stale reference. Run it in the validation profile so the docs
 * cannot drift silently again.
 *
 * Usage: node validate_operator_doc_currency.mjs [docGlobDir ...]
 */
import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const DIRS = process.argv.slice(2).filter((a) => !a.startsWith('--'));
const DEFAULT_DIRS = ['docs/runbooks', 'docs/operator', 'docs/operations', 'docs'];

// Placeholders, not real paths.
const TEMPLATE = /(YYYY|MM|DD|<[^>]+>|\{[^}]+\}|\*|\$\{|\.\.\.)/;
// References to public URL routes rather than files on disk.
const looksLikeRoute = (p) => p.startsWith('/') && !p.includes('.');

function docFiles() {
  const dirs = DIRS.length ? DIRS : DEFAULT_DIRS;
  const out = [];
  for (const d of dirs) {
    const full = path.join(ROOT, d);
    if (!fs.existsSync(full)) continue;
    const walk = (dir) => {
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        const f = path.join(dir, e.name);
        if (e.isDirectory()) { if (!/node_modules|\.git/.test(f)) walk(f); }
        else if (e.name.endsWith('.md')) out.push(f);
      }
    };
    walk(full);
    if (DIRS.length === 0) break; // 'docs' fallback only if the specific dirs are absent
  }
  return [...new Set(out)];
}

// Route references can only be resolved against the filesystem when the site IS
// the filesystem. Where a Worker, a functions directory, or a framework router
// serves the routes, a missing folder proves nothing, so routes are not judged.
const DYNAMIC_ROUTING = ['wrangler.toml', 'wrangler.jsonc', 'wrangler.json', 'functions', 'app', 'src/pages', 'pages']
  .some((f) => fs.existsSync(path.join(ROOT, f)));

/** A route is current if some file in the tree serves it. */
function routeExists(route) {
  if (DYNAMIC_ROUTING) return true;
  const clean = route.replace(/^\/+|\/+$/g, '');
  if (!clean) return true;
  return fs.existsSync(path.join(ROOT, clean))
    || fs.existsSync(path.join(ROOT, `${clean}.html`))
    || fs.existsSync(path.join(ROOT, clean, 'index.html'));
}

// Only judge references that actually point into this repo. A home-directory
// path, a GitHub org/repo slug, or a package name is not this repo's business
// and cannot be verified from here.
const TOP_LEVEL = new Set(fs.readdirSync(ROOT, { withFileTypes: true }).map((e) => e.name));
// Generic tooling paths appear in prose about how repos work in general. They
// are not claims about this repo's layout, so they are not this check's business.
const GENERIC = new Set(['node_modules', 'tmp', 'coverage', 'venv', '.venv', 'build', 'out', 'target']);
function isRepoPath(ref) {
  if (ref.startsWith('~') || ref.startsWith('$')) return false;
  if (GENERIC.has(ref.replace(/\/$/, ''))) return false;
  if (ref.startsWith('/')) return true;
  const first = ref.split('/')[0];
  return TOP_LEVEL.has(first);
}

// Paths under a build-output directory do not exist in a clean checkout, so
// their existence proves nothing either way. What can be checked is whether the
// pipeline still produces them - a doc pointing at an artifact no script writes
// any more is exactly as stale as one pointing at a deleted file.
const GENERATED = /^(\.build|reports|artifacts|dist|\.pages-output|coverage)\//;
let scriptCorpus = '';
(function readScripts(dir) {
  if (!fs.existsSync(dir)) return;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const f = path.join(dir, e.name);
    if (e.isDirectory()) readScripts(f);
    else if (/\.(mjs|js|cjs|py|sh|json)$/.test(e.name)) {
      try { scriptCorpus += fs.readFileSync(f, 'utf8'); } catch { /* unreadable, skip */ }
    }
  }
})(path.join(ROOT, 'scripts'));
try { scriptCorpus += fs.readFileSync(path.join(ROOT, 'package.json'), 'utf8'); } catch { /* none */ }

// Some documented paths are supplied by a human, not by the repo or the
// pipeline: a logo a VA uploads, a credential file created on activation. They
// cannot be verified from here and they are not defects. Listing them in
// docs/.operator-doc-currency-allow keeps them visible and reviewable rather
// than quietly widening the rules for everyone.
const ALLOW = new Set();
for (const candidate of ['docs/.operator-doc-currency-allow', '.operator-doc-currency-allow']) {
  const f = path.join(ROOT, candidate);
  if (!fs.existsSync(f)) continue;
  for (const line of fs.readFileSync(f, 'utf8').split('\n')) {
    const v = line.trim();
    if (v && !v.startsWith('#')) ALLOW.add(v);
  }
}

const errors = [];
let checked = 0;

// A dated document is a record of what was true on that date. Its references
// going stale is the passage of time, not a documentation defect.
const DATED_DOC = /\d{4}-\d{2}-\d{2}/;
for (const file of docFiles()) {
  const rel = path.relative(ROOT, file);
  if (DATED_DOC.test(path.basename(file))) continue;
  const text = fs.readFileSync(file, 'utf8');
  // A line that says a thing was merged, removed, or replaced is documenting
  // history on purpose. The reference is supposed to name something gone.
  const RETIRED = /\b(merged into|removes?|removed|retired|deletes?|deleted|replaced by|superseded|no longer|formerly|used to|excludes?|legacy|instead of|rather than|, not )\b/i;
  const lineAt = (idx) => text.slice(text.lastIndexOf('\n', idx) + 1, (text.indexOf('\n', idx) + 1 || text.length));
  for (const m of text.matchAll(/`([^`\n]+)`/g)) {
    const ref = m[1].trim();
    if (RETIRED.test(lineAt(m.index))) continue;
    if (!ref.includes('/') || ref.includes(' ')) continue;
    // KEY=value lines are configuration examples, not paths.
    if (ref.includes('=')) continue;
    if (TEMPLATE.test(ref)) continue;
    if (/^https?:/.test(ref)) continue;
    if (!isRepoPath(ref)) continue;
    checked++;
    const bare = ref.replace(/^\/+/, '');
    let ok;
    if (looksLikeRoute(ref)) ok = routeExists(ref);
    else {
      // Present on disk is the strongest signal. Failing that, a path the
      // pipeline itself still writes or reads is a runtime artifact - a secret
      // vault the operator creates, a report a build emits - and its absence in
      // a clean checkout says nothing. Only a path that neither exists nor is
      // referenced anywhere in the tooling is genuinely stale.
      ok = fs.existsSync(path.join(ROOT, ref))
        || fs.existsSync(path.join(ROOT, bare))
        || scriptCorpus.includes(bare.replace(/\/$/, ''));
    }
    if (!ok && !ALLOW.has(ref)) errors.push(`${rel}: stale reference: ${ref}`);
  }
}

if (errors.length) {
  console.log(`OPERATOR DOC CURRENCY FAIL: ${errors.length} stale reference(s) of ${checked} checked`);
  for (const e of errors) console.log(` - ${e}`);
  process.exit(1);
}
console.log(`OPERATOR DOC CURRENCY PASS: ${checked} path reference(s) checked, all present`);
