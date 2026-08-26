#!/usr/bin/env node
/**
 * Decide whether adding MORE pages is currently being absorbed - but refuse to
 * decide on contaminated data.
 *
 * The honest problem
 * ------------------
 * Search Console shows surfacing flat or falling across the last 90 days while
 * ~2,300 pages were published:
 *
 *   spryexecutiveos.com    46 -> 35 -> 31 pages surfacing per month
 *   bhpc                   802 -> 643 -> 527 impressions per month
 *
 * It is tempting to read that as "the cadence publishes waste" and cut it. That
 * would be wrong twice over.
 *
 * First, most of the corpus was simply young: pages older than 90 days surface
 * at 20.2%, pages newer than 90 days at 0.1%. An age-blind reading measures
 * youth and calls it failure.
 *
 * Second - and this is the disqualifying one - that entire window predates the
 * structural fixes. During those 90 days every unknown URL on thirteen domains
 * returned 200 with a copy of the homepage, so crawl budget went to infinite
 * synthetic duplicates; sitemaps were never submitted to Search Console at all;
 * three sitemaps were addressed to a host literally named "None"; and tens of
 * thousands of internal links resolved through redirects. Surfacing under those
 * conditions is not evidence about publishing volume. It is evidence the site
 * was hard to crawl.
 *
 * The existing cadence was derived from research. Overriding it with a number
 * produced by a broken crawl would be replacing reasoning with noise.
 *
 * So this gate will not hold publishing using data from before the fixes
 * landed. It reports how much clean data exists, and starts gating only once
 * there is enough of it. Until then the declared cadence stands.
 */
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const ROOT = process.cwd();
const OUT = path.join(ROOT, 'reports/cadence/publish-headroom.json');

// The day the structural crawl fixes went live. Data before this measures a
// site that could not be crawled properly, not a cadence that was too fast.
const CLEAN_BASELINE_START = '2026-08-26';
// Two 30-day windows after the fixes before any hold decision is defensible.
const REQUIRED_CLEAN_DAYS = 60;

const SITES = (process.env.GSC_SITES || '').split(',').map((s) => s.trim()).filter(Boolean);
const KEY = process.env.GSC_SERVICE_ACCOUNT_JSON || '';

const cleanDays = Math.max(0, Math.floor(
  (Date.now() - Date.parse(`${CLEAN_BASELINE_START}T00:00:00Z`)) / 86400000));

const report = {
  schema_version: '1.0',
  generated_at: new Date().toISOString(),
  clean_baseline_start: CLEAN_BASELINE_START,
  clean_days_available: cleanDays,
  required_clean_days: REQUIRED_CLEAN_DAYS,
  status: 'ESTABLISHING_BASELINE',
  publish_new_pages: true,
  reason: '',
  sites: {},
};

if (cleanDays < REQUIRED_CLEAN_DAYS) {
  report.reason =
    `Only ${cleanDays} of ${REQUIRED_CLEAN_DAYS} days of post-fix data. Search Console history before ` +
    `${CLEAN_BASELINE_START} measures a site whose sitemaps were never submitted and whose unknown URLs ` +
    `returned 200 with the homepage, so it cannot be used to judge publishing volume. The declared ` +
    `cadence stands until a clean baseline exists.`;
} else if (KEY && SITES.length) {
  try {
    const raw = execFileSync(process.env.PYTHON || 'python3',
      [path.join(ROOT, 'scripts/cadence/gsc_surfacing.py'), ...SITES],
      { encoding: 'utf8', env: { ...process.env, GSC_WINDOW_START: CLEAN_BASELINE_START } });
    const data = JSON.parse(raw);
    const falling = [];
    for (const [site, months] of Object.entries(data)) {
      const [, prev, now] = months;
      const publish = now >= prev;
      report.sites[site] = {
        monthly_pages_surfacing: months,
        publish,
        why: publish
          ? `surfacing holding or growing (${prev} -> ${now} pages)`
          : `surfacing falling (${prev} -> ${now} pages) on post-fix data`,
      };
      if (!publish) falling.push(site);
    }
    report.status = 'MEASURED';
    report.publish_new_pages = falling.length === 0;
    report.reason = falling.length
      ? `Hold new volume: ${falling.join(', ')} surfacing fewer pages than the prior window, measured entirely after the crawl fixes. Improve existing pages instead.`
      : 'Publish: surfacing holding or growing on post-fix data across all measured properties.';
  } catch (error) {
    report.status = 'UNMEASURED';
    report.reason = `Search Console read failed (${String(error.message).slice(0, 110)}); publishing allowed rather than frozen by a credential problem.`;
  }
} else {
  report.status = 'UNMEASURED';
  report.reason = 'No Search Console credentials; publishing allowed rather than frozen by a credential problem.';
}

fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, `${JSON.stringify(report, null, 2)}\n`);
console.log(`[cadence] ${report.status}: publish_new_pages=${report.publish_new_pages}`);
console.log(`  ${report.reason}`);
for (const [site, s] of Object.entries(report.sites)) {
  console.log(`  ${site}: ${s.monthly_pages_surfacing.join(' -> ')}; ${s.why}`);
}
