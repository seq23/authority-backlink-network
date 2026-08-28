#!/usr/bin/env node
'use strict';
/**
 * Install the Microsoft Clarity tag into every published page.
 *
 * The Clarity projects already existed - one per property - but no tag was ever
 * installed, so every project sat on "Almost there!" and none of them recorded a
 * single session. This closes that.
 *
 * The snippet resolves its project id from location.hostname rather than being
 * hardcoded, because some trees serve more than one domain from the same files
 * (spryexecutiveos.com and billionairehighperformancecoach.com are one tree with
 * two separate Clarity projects). A hardcoded id would send one domain's sessions
 * to the other domain's project.
 *
 * Idempotent: pages already carrying the marker are left alone, so this can run
 * on every build.
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const CONFIG = path.join(ROOT, 'data/clarity_projects.json');
const MARKER = 'data-clarity-loader';
const REFERRER_MARKER = 'data-ai-referrer-tag';
const REFERRERS = path.join(ROOT, 'data/ai_referrers.json');

if (!fs.existsSync(CONFIG)) {
  console.error(`clarity: missing ${path.relative(ROOT, CONFIG)}`);
  process.exit(1);
}
const cfg = JSON.parse(fs.readFileSync(CONFIG, 'utf8'));
const projects = cfg.projects || {};
const outDir = path.resolve(ROOT, cfg.public_root || '.');
const skipDirs = new Set([
  ...(cfg.skip_dirs || []),
  '.git', 'node_modules', '.pages-output', 'dist', 'scripts', 'data', 'reports',
  'artifacts', 'docs', 'tests', 'fixtures', 'config', 'content', 'templates',
]);
const skipFiles = new Set(cfg.skip_files || []);

if (!Object.keys(projects).length) {
  console.error('clarity: no projects configured');
  process.exit(1);
}

// One loader for every page. It picks the project by host so a shared tree cannot
// report one domain's sessions under another domain's project.
const snippet = `<script ${MARKER}>(function(w,d,m){var h=(w.location.hostname||"").toLowerCase().replace(/^www\\./,"");var id=m[h];if(!id)return;w.clarity=w.clarity||function(){(w.clarity.q=w.clarity.q||[]).push(arguments)};var s=d.createElement("script");s.async=1;s.src="https://www.clarity.ms/tag/"+id;var f=d.getElementsByTagName("script")[0];f.parentNode.insertBefore(s,f)})(window,document,${JSON.stringify(projects)})</script>`;

// Classify the referrer and hand it to Clarity as a custom tag.
//
// The portfolio could measure whether a page is CITED (Bing Webmaster AI
// Performance) and had no way at all to see whether a citation was ever CLICKED.
// Clarity is already installed on all three publications and supports custom tags,
// so this closes the loop with no new infrastructure and no new account.
//
// Hostname only, never the referrer's full URL -- on some engines that carries the
// user's question text. referrer_class is always set so a denominator exists;
// without one, "12 AI arrivals" means nothing.
const AI_ENGINES = {"chatgpt.com": "chatgpt", "chat.openai.com": "chatgpt", "openai.com": "chatgpt", "perplexity.ai": "perplexity", "www.perplexity.ai": "perplexity", "copilot.microsoft.com": "copilot", "www.bing.com": "bing-or-copilot", "bing.com": "bing-or-copilot", "gemini.google.com": "gemini", "bard.google.com": "gemini", "claude.ai": "claude", "you.com": "you", "www.you.com": "you", "search.brave.com": "brave-ai", "duckduckgo.com": "duckduckgo", "phind.com": "phind", "poe.com": "poe"};
const referrerSnippet = '<script ' + REFERRER_MARKER + '>(function(w,d,m){try{'
  + 'var r=d.referrer||"";var host="";try{host=r?new URL(r).hostname.toLowerCase():"";}catch(e){host="";}'
  + 'var self=(w.location.hostname||"").toLowerCase().replace(/^www\\./,"");'
  + 'var cls="direct";var engine="";'
  + 'if(host){var bare=host.replace(/^www\\./,"");'
  + 'if(bare===self){cls="internal";}'
  + 'else if(m[host]||m[bare]){engine=m[host]||m[bare];cls=(engine==="bing-or-copilot")?"search-or-ai":"ai";}'
  + 'else if(/(^|\\.)(google|yahoo|baidu|yandex|ecosia|startpage)\\./.test(host)){cls="search";}'
  + 'else if(/(^|\\.)(facebook|instagram|linkedin|reddit|twitter|x)\\./.test(host)){cls="social";}'
  + 'else{cls="referral";}}'
  + 'w.clarity=w.clarity||function(){(w.clarity.q=w.clarity.q||[]).push(arguments)};'
  + 'w.clarity("set","referrer_class",cls);'
  + 'if(engine){w.clarity("set","ai_engine",engine);}'
  + 'if(cls==="ai"){w.clarity("set","ai_landing_path",(w.location.pathname||"/").slice(0,120));w.clarity("upgrade","ai_referral");}'
  + 'if(host){w.clarity("set","referrer_host",host.slice(0,80));}'
  + '}catch(e){}})(window,document,' + JSON.stringify(AI_ENGINES) + ');<\/script>';

let touched = 0;
let referrerTouched = 0;
let already = 0;
let skipped = 0;

function walk(dir, depth) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name.startsWith('.')) continue;
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) { if (!skipDirs.has(entry.name)) walk(abs, depth + 1); continue; }
    if (!entry.name.endsWith('.html')) continue;
    const rel = path.relative(outDir, abs).replace(/\\/g, '/');
    if (skipFiles.has(rel) || skipFiles.has(entry.name)) { skipped += 1; continue; }
    const html = fs.readFileSync(abs, 'utf8');
    const hasClarity = html.includes(MARKER);
    const hasReferrer = html.includes(REFERRER_MARKER);
    if (hasClarity && hasReferrer) { already += 1; continue; }
    if (!/<\/head>/i.test(html)) { skipped += 1; continue; }
    let out = html;
    if (!hasClarity) out = out.replace(/<\/head>/i, `${snippet}</head>`);
    if (!hasReferrer) { out = out.replace(/<\/head>/i, `${referrerSnippet}</head>`); referrerTouched += 1; }
    fs.writeFileSync(abs, out);
    touched += 1;
  }
}
walk(outDir, 0);

console.log(`clarity: installed on ${touched} page(s); ${already} already had it; ${skipped} skipped; ai-referrer tag on ${referrerTouched} page(s)`);
