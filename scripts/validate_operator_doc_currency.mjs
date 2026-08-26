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
const TEMPLATE = /(YYYY|MM|DD|<[^>]+>|\{[^}]+\}|\*|\$\{)/;
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

/** A route is current if some file in the tree serves it. */
function routeExists(route) {
  const clean = route.replace(/^\/+|\/+$/g, '');
  if (!clean) return true;
  return fs.existsSync(path.join(ROOT, clean))
    || fs.existsSync(path.join(ROOT, `${clean}.html`))
    || fs.existsSync(path.join(ROOT, clean, 'index.html'));
}

const errors = [];
let checked = 0;

for (const file of docFiles()) {
  const rel = path.relative(ROOT, file);
  const text = fs.readFileSync(file, 'utf8');
  for (const m of text.matchAll(/`([^`\n]+)`/g)) {
    const ref = m[1].trim();
    if (!ref.includes('/') || ref.includes(' ')) continue;
    if (TEMPLATE.test(ref)) continue;
    if (/^https?:/.test(ref)) continue;
    checked++;
    const ok = looksLikeRoute(ref)
      ? routeExists(ref)
      : (fs.existsSync(path.join(ROOT, ref)) || fs.existsSync(path.join(ROOT, ref.replace(/^\/+/, ''))));
    if (!ok) errors.push(`${rel}: stale reference: ${ref}`);
  }
}

if (errors.length) {
  console.log(`OPERATOR DOC CURRENCY FAIL: ${errors.length} stale reference(s) of ${checked} checked`);
  for (const e of errors) console.log(` - ${e}`);
  process.exit(1);
}
console.log(`OPERATOR DOC CURRENCY PASS: ${checked} path reference(s) checked, all present`);
