#!/usr/bin/env node
'use strict';
// Enforce the blocks the external review agent keeps asking for.
//
// Across ~2,750 recommendations audited on the sibling sites, the agent asks
// for the same small set of things over and over, and 27% of distinct defects
// were re-reported on later runs despite being marked released - the same page
// missing the same block, found again. This checks for those blocks before
// publish instead of after audit.
//
// Derived from the recommendations themselves (.clarity/content-pattern-spec.json
// in local-guides-citation-velocity):
//
//   1 checklist / numbered protocol      730 occurrences (36.4%)
//   2 comparison / decision / cost table 529 (26.4%)
//   3 direct-answer block                512 (25.5%)
//   5 concrete numbers                   365 (18.2%)
//   6 named primary sources              288 (14.3%)
//   7 query present in a heading         261 (13.0%)
//   9 FAQ block                          136 (6.8%)
//  10 structured data                     70 (3.5%)
//
// Severity is split: the blocks that decide whether a page can be quoted at all
// block the release; the rest report as gaps so they can be worked without
// stopping a release. All four blocking checks are at 100% on this repo, which
// is why they are registered blocking rather than reported.

const fs = require('fs');
const path = require('path');

const REPO = path.resolve(__dirname, '../..');
// Every publication lives under sites/<publication>/ and is deployed from there
// by its own Cloudflare Pages project.
const ROOT = path.join(REPO, 'sites');
const EVIDENCE = path.join(REPO, 'reports/validation/content-pattern-contract.json');
const ENFORCEMENT = 'block'; // 'block' | 'report'

// The agency directory is an internal dashboard, not a published answer
// surface. About pages state who publishes the site; they answer no search
// query and carry no editorial link by design.
const SKIP_DIRS = new Set(['agency', 'node_modules', '.git']);
const isSkippedFile = (rel) => {
  const base = path.basename(rel);
  return base === '404.html' || base === 'about.html';
};

// A publication's index is a masthead, not a query-answering page; its h1 is
// the publication name. It still owes every other check.
const isHub = (rel) => rel.endsWith('index.html');

const text = (html) => html.replace(/<script[\s\S]*?<\/script>/gi, ' ')
  .replace(/<style[\s\S]*?<\/style>/gi, ' ').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();

// Four shapes count as a direct answer, because the repo emits four. The
// generated families lead with <p class="citation-definition"> or a section
// marked data-llm-answer; older pages use a labelled heading; the rest carry a
// real opening paragraph. A stub of a few words is not self-contained, so the
// unlabelled form has to carry a real sentence.
const MIN_LEAD_CHARS = 80;
const leadLength = (html) => {
  const m = html.match(/<h1[^>]*>[\s\S]*?<\/h1>\s*<p[^>]*>([\s\S]*?)<\/p>/i);
  return m ? text(m[1]).length : 0;
};
const hasAnswer = (h) => /<h[23][^>]*>\s*(?:Quick|Direct|Short)\s+answer/i.test(h)
  || leadLength(h) >= MIN_LEAD_CHARS;

// These publications exist to carry editorial links to the properties they
// cover, so the outbound link IS the conversion path. A page with none is an
// editorial dead end - it costs a page of crawl budget and returns nothing.
const CONVERSION = /<a[^>]+href="https?:\/\//i;

// A "named primary source" has to be a source. This check used to pass on any
// outbound link at all, which meant all 590 pages scored 100% while every one of
// them linked exclusively to domains inside this portfolio - the check reported
// full coverage of a thing that did not exist anywhere on the three sites.
//
// It now counts only links to domains in data/external-sources.json, every one of
// which was fetched and returned 200 before being registered. Affiliated
// portfolio links, which carry rel="sponsored nofollow", no longer satisfy it.
const REGISTERED_SOURCE_DOMAINS = new Set(
  JSON.parse(fs.readFileSync(path.join(REPO, 'data/external-sources.json'), 'utf8'))
    .sources.map((s) => s.domain.toLowerCase().replace(/^www\./, '')));
const EXTERNAL_SOURCE = {
  test: (html) => {
    const hrefs = html.match(/<a[^>]+href="https?:\/\/[^"]+"/gi) || [];
    return hrefs.some((tag) => {
      const m = tag.match(/href="https?:\/\/([^/"]+)/i);
      if (!m) return false;
      return REGISTERED_SOURCE_DOMAINS.has(m[1].toLowerCase().replace(/^www\./, ''));
    });
  },
};

const CHECKS = [
  { id: 'direct_answer', blocking: true, test: hasAnswer,
    why: 'no direct-answer block - nothing here is quotable without surrounding context' },
  { id: 'query_in_heading', blocking: true,
    test: (h, rel) => {
      const m = h.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i);
      if (!m) return false;
      const len = text(m[1]).length;
      return isHub(rel) ? len > 0 : len > 10;
    },
    why: 'h1 missing or too short to carry the searcher phrasing' },
  { id: 'no_empty_table_cells', blocking: true,
    test: (h) => !/<t[dh][^>]*>\s*<\/t[dh]>/i.test(h),
    why: 'table ships empty cells - the agent calls these impossible to cite' },
  { id: 'conversion_path', blocking: true, test: (h) => CONVERSION.test(h),
    why: 'no outbound editorial link - the page is a dead end that returns nothing' },
  { id: 'checklist', blocking: false, test: (h) => /<ol[\s>]|<ul[\s>]/i.test(h),
    why: 'no checklist or numbered protocol (agent request #1, 730 occurrences)' },
  { id: 'comparison_table', blocking: false, test: (h) => /<table[\s>]/i.test(h),
    why: 'no comparison or cost table (agent request #2, 529 occurrences)' },
  { id: 'concrete_numbers', blocking: false,
    test: (h) => /\$\s?\d|\d+\s?(?:days?|weeks?|months?|years?|hours?|minutes?)\b/i.test(text(h)),
    why: 'no concrete cost or timeline figures (agent request #5, 365 occurrences)' },
  { id: 'named_sources', blocking: false,
    test: (h) => EXTERNAL_SOURCE.test(h),
    why: 'no link to a verified outside source - the page cites only domains this network owns' },
  { id: 'faq', blocking: false, test: (h) => /FAQPage|data-faq|class="[^"]*faq/i.test(h),
    why: 'no FAQ block or FAQPage schema (agent request #9)' },
  { id: 'structured_data', blocking: false, test: (h) => /application\/ld\+json/i.test(h),
    why: 'no JSON-LD structured data (agent request #10)' },
];

const pages = [];
(function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name.startsWith('.')) continue;
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) { if (!SKIP_DIRS.has(entry.name)) walk(abs); continue; }
    if (!entry.name.endsWith('.html')) continue;
    const rel = path.relative(ROOT, abs);
    if (isSkippedFile(rel)) continue;
    pages.push(rel);
  }
})(ROOT);
pages.sort();

// Rule 0: zero pages is not full compliance.
//
// coverage_pct is computed as 100 * (1 - missing / max(pages.length, 1)), so an
// empty scan yields 100% on every check and zero blocking failures. Proved by
// deleting every file under sites/: this printed "0 pages checked" alongside
// "BLOCKING direct_answer coverage 100%" on all four blocking checks, and
// exited 0. The severity rationale for this gate reads "all four checks measure
// 100% across the 495 published pages, so blocking cannot regress a clean
// surface" - and a 100% derived from nothing is indistinguishable from that.
//
// sites/ is tracked in git, so a fresh checkout always has pages. An empty scan
// means the walk root moved, the skip rules widened, or the tree is absent.
if (pages.length === 0) {
  console.error(
    'CONTENT PATTERN CONTRACT: FAIL - scanned 0 pages under ' +
    (path.relative(REPO, ROOT) || '.') + '.\n' +
    '  Coverage is a ratio over the pages scanned, so an empty scan reports 100% on\n' +
    '  every check and blocks nothing. sites/ is committed and always contains pages,\n' +
    '  so finding none means a broken scan root or skip rule, not a compliant library.'
  );
  process.exit(1);
}

const blockingFailures = [];
const gaps = {};
for (const check of CHECKS) gaps[check.id] = [];

for (const rel of pages) {
  const html = fs.readFileSync(path.join(ROOT, rel), 'utf8');
  for (const check of CHECKS) {
    if (check.test(html, rel)) continue;
    if (check.blocking) blockingFailures.push({ path: rel, check: check.id, why: check.why });
    else gaps[check.id].push(rel);
  }
}

const summary = CHECKS.map((check) => {
  const missing = check.blocking
    ? blockingFailures.filter((f) => f.check === check.id).length
    : gaps[check.id].length;
  return {
    id: check.id,
    blocking: check.blocking,
    pages_missing: missing,
    coverage_pct: Number((100 * (1 - missing / Math.max(pages.length, 1))).toFixed(1)),
    why: check.why,
  };
});

fs.mkdirSync(path.dirname(EVIDENCE), { recursive: true });
fs.writeFileSync(EVIDENCE, `${JSON.stringify({
  schema_version: '1.0',
  validator: 'content-pattern-contract',
  generated_at: new Date().toISOString(),
  enforcement: ENFORCEMENT,
  scanned_root: path.relative(REPO, ROOT) || '.',
  pages_checked: pages.length,
  status: blockingFailures.length ? (ENFORCEMENT === 'block' ? 'FAIL' : 'REPORTED') : 'PASS',
  blocking_failures: blockingFailures.length,
  summary,
  worst_gaps: Object.fromEntries(Object.entries(gaps).map(([k, v]) => [k, v.slice(0, 25)])),
  blocking_backlog: blockingFailures.slice(0, 200),
}, null, 2)}\n`);

console.log(`CONTENT PATTERN CONTRACT: ${pages.length} pages checked (enforcement: ${ENFORCEMENT})`);
for (const s of summary) {
  const tag = s.blocking ? 'BLOCKING' : 'gap     ';
  console.log(`  ${tag} ${s.id.padEnd(22)} coverage ${String(s.coverage_pct).padStart(5)}%  missing on ${s.pages_missing}`);
}
if (blockingFailures.length) {
  const log = ENFORCEMENT === 'block' ? console.error : console.warn;
  log(`\nCONTENT PATTERN CONTRACT: ${blockingFailures.length} blocking gap(s)`);
  for (const f of blockingFailures.slice(0, 15)) log(`  ${f.path} :: ${f.why}`);
  if (blockingFailures.length > 15) log(`  ...and ${blockingFailures.length - 15} more`);
  if (ENFORCEMENT === 'block') process.exit(1);
  console.warn('  reported, not blocking, while the backlog above is worked.');
  process.exit(0);
}
console.log('\nCONTENT PATTERN CONTRACT PASS');
