# Authority Network V4 — One-Year Autopilot

This patch adds a 365-day programmatic authority engine with a 12-month template pantry, adaptive scaling, optional Gemini rewrite, social draft generation, sitemap/llms updates, and link registry updates.

## Default behavior

- No API key required.
- Generates deterministic editorial pages from the pantry.
- Optional `GEMINI_API_KEY` can polish medium-score pages.
- If Gemini fails, the base page publishes if it passes score >= 72.
- Cloudflare deploy remains handled by your Cloudflare Git integration.

## Scaling

Days 1–14: 3 pages/day.
Days 15–45: 6 pages/day if pass rate is healthy, else 3.
Days 46–90: 6 pages/day unless quality drops.
Days 91–365: 6–9 pages/day based on pass rate, average quality, and duplicate warnings.

Absolute max: 9 pages/day across the 3 publications.

## Variables

Recommended GitHub Variables:

```txt
ENABLE_GEMINI_REWRITE=false
GEMINI_MODEL=gemini-2.5-flash-lite
MIN_BASE_PUBLISH_SCORE=72
LINKEDIN_DAILY_LIMIT=3
X_DAILY_LIMIT=8
FOUNDER_PUBLICATION_DOMAIN=founderoperatorlibrary.com
MEMPHIS_PUBLICATION_DOMAIN=memphisvendorlibrary.com
PROFESSIONAL_PUBLICATION_DOMAIN=professionalresourcelibrary.com
```

Optional Secret:

```txt
GEMINI_API_KEY
```

Do not add OpenAI unless you later choose to.
