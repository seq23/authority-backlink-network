# Page quality diagnosis — 2026-11-04
Baseline: 73782f22ea14ce3dec3531d3085fab1664cd0182; worktree .wt-quality-authority-backlink-network; branch fix/page-quality-2026-11-03; origin seq23/authority-backlink-network.
Method: fetched apex live sitemap and 10 evenly spaced daily URLs/site using curl; strip head/script/style/nav/footer, compare five-word shingle containment over all 45 pairs.
Raw audit: docs/page-quality-live-audit.json (sample URLs, word counts, metric).
founderoperatorlibrary.com: live sitemap 120 URLs; sample mean shared passages 28.1%; sampled visible words 584–1409.
Thin (<300 visible words, complete local tree): sites/founder-operator/404.html; only error pages, excluded from content consolidation.
GSC 2026-10-03–2026-10-30, collected 2026-11-02T15:26:46+00:00: 168 impressions, 1 clicks; query and by_page rows available in data/search_intelligence/founderoperatorlibrary.com/gsc_truth.json.
Decision: keep 44 sitemap pages; redirect 76 generated daily pages; exact kept/retired/routes in data/page-quality-consolidation.json.
memphisvendorlibrary.com: live sitemap 109 URLs; sample mean shared passages 32.0%; sampled visible words 579–1428.
Thin (<300 visible words, complete local tree): sites/memphis-local/404.html; only error pages, excluded from content consolidation.
GSC 2026-10-03–2026-10-30, collected 2026-11-02T15:26:46+00:00: 147 impressions, 0 clicks; query and by_page rows available in data/search_intelligence/memphisvendorlibrary.com/gsc_truth.json.
Decision: keep 47 sitemap pages; redirect 62 generated daily pages; exact kept/retired/routes in data/page-quality-consolidation.json.
Founder duplicate intent clusters: broadcast/event planning, automation/AI delegation, review cadence/accountability, lean-team tools and community operations; formats/modifiers do not create new intent.
Memphis duplicate intent clusters: wedding checklist/planning tools, timelines, budgets, seating charts, porch installs and event styling; consolidate permutations into the matching authored guide or hub.
No demand is inferred from missing query rows: GSC anonymises queries. Same-intent consolidation uses recorded cluster identity, including pages with impressions, and preserves routes with direct 301s.
Operational/editorial/legal/contact/admin pages are preserved. No client publication pages changed.
Earlier debloating still describes page scope instead of answering the query; shared source/affiliate and internal-system blocks amplify repetition.
Implement shape in existing renderers, use real publication-company bylines and fixed editorial dates; no wording validator.
No deployment requested: live verification after deployment remains separate from PR-local evidence.
Resume: re-fetched both live sitemaps and the same 10 samples/site on 2026-11-04; measurements above refreshed.
Requested external page-shape.md was absent (exact path and /private/tmp filename search); used the explicit shape in the brief.
Resume fixes: authored definitions survive strengthening; citation blocks survive chrome; federal care/reading sources verified; missing hub and dataset introduction repaired.
PR rebased onto d5f77672446183edcffa3d594d5835c4307c6fb9; preserved current GSC truth and regenerated search plans, reports and discovery artifacts.
Final rebased release validation: 66 checks passed; 520 pages; 0 hard failures, 3 soft warnings, no duplicate-content groups.
