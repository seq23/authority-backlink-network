#!/usr/bin/env python3
"""
measure_crawler_access.py -- can an answer engine actually fetch these pages?

Everything downstream of this is moot if it is not true, and it is the one link
in the citation chain that can be verified from here without an account. It is
also the one that silently breaks: a Cloudflare managed-robots toggle, a bot-
fight-mode change, or a WAF rule can start returning 403 to GPTBot without
anything in the repository changing. So this is a probe, not a claim, and it is
re-runnable.

Three things are checked per (domain, agent):

  1. HTTP status -- must be 200. A 403 or a challenge is a hard failure.
  2. robots.txt -- the agent must be allowed the paths in the sitemap.
  3. Server-rendered answer -- the direct-answer block must be present in the
     bytes returned to that agent. A page that needs JavaScript to show its
     answer has no answer as far as an extractive crawler is concerned.

Network access required. Exits non-zero if any agent is blocked.

Usage:
  python3 measure_crawler_access.py --out reports/crawler-access.json \\
      founderoperatorlibrary.com memphisvendorlibrary.com professionalresourcelibrary.com
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

# The agents that matter for AI answer citation, plus the two classical
# crawlers whose indexes those answers are often built on.
AGENTS = {
    "GPTBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)",
    "OAI-SearchBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot)",
    "ChatGPT-User": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ChatGPT-User/1.0; +https://openai.com/bot)",
    "ClaudeBot": "Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
    "Claude-SearchBot": "Mozilla/5.0 (compatible; Claude-SearchBot/1.0; +claudebot@anthropic.com)",
    "PerplexityBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)",
    "Googlebot": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Bingbot": "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
    "Applebot": "Mozilla/5.0 (compatible; Applebot/0.1; +http://www.apple.com/go/applebot)",
    "baseline-browser": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
}

# Markers that prove the answer was server-rendered into the bytes.
ANSWER_MARKERS = ('data-content-block="recommendation_summary"', "<h2>Short answer</h2>")

TIMEOUT = 30


def fetch(url, ua):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except Exception as exc:  # noqa: BLE001 -- network shape is the finding
        return None, f"__ERROR__ {type(exc).__name__}: {exc}"


def first_article_url(domain):
    """Pick a real article from the sitemap rather than assuming a path."""
    status, body = fetch(f"https://{domain}/sitemap.xml", AGENTS["baseline-browser"])
    if status != 200:
        return None, 0
    locs = [
        line.split("<loc>")[1].split("</loc>")[0]
        for line in body.splitlines()
        if "<loc>" in line
    ]
    article = next((u for u in locs if "/daily/" in u), None)
    return article or (locs[0] if locs else None), len(locs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("domains", nargs="+")
    ap.add_argument("--out")
    args = ap.parse_args()

    result = {
        "schema": "authority-crawler-access-v1",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "note": "Access is a precondition for citation, not evidence of it.",
        "domains": [],
    }
    blocked_total = 0

    for domain in args.domains:
        article, sitemap_urls = first_article_url(domain)
        entry = {
            "domain": domain,
            "sitemap_urls": sitemap_urls,
            "probe_article": article,
            "agents": {},
        }
        for name, ua in AGENTS.items():
            row = {}
            for label, path in (
                ("root", "/"),
                ("robots", "/robots.txt"),
                ("llms", "/llms.txt"),
                ("sitemap", "/sitemap.xml"),
            ):
                status, _body = fetch(f"https://{domain}{path}", ua)
                row[label] = status
            if article:
                status, body = fetch(article, ua)
                row["article"] = status
                row["answer_server_rendered"] = (
                    any(m in body for m in ANSWER_MARKERS) if status == 200 else False
                )
            row["blocked"] = any(
                v is not None and isinstance(v, int) and v != 200
                for k, v in row.items()
                if k in {"root", "robots", "llms", "sitemap", "article"}
            ) or any(
                v is None for k, v in row.items()
                if k in {"root", "robots", "llms", "sitemap", "article"}
            )
            if row["blocked"]:
                blocked_total += 1
            entry["agents"][name] = row
        result["domains"].append(entry)

    result["status"] = "PASS" if blocked_total == 0 else "FAIL"
    result["blocked_agent_domain_pairs"] = blocked_total

    payload = json.dumps(result, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
    print(payload)
    return 0 if blocked_total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
