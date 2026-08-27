#!/usr/bin/env python3
"""Generate a robots.txt per publication that describes that publication's own site.

Why
---
All three sites served a byte-identical robots.txt whose only difference was the
Sitemap line. A robots.txt is a public statement about a site's structure, and
three identical ones say the three sites have the same structure -- which, since
they do not, is simply inaccurate.

What this does and does not do
------------------------------
It differentiates them by describing what is actually there: each publication's
real sections, its real page counts, its own governance routes, its own sitemap
and llms.txt. That is a robots.txt being correct about its own site.

It does NOT contort the file to make the three look unrelated. Differentiating
because the sites genuinely differ is correct; differentiating to defeat
fingerprinting would be the opposite of what the rest of this work is for, and
would not work anyway -- shared build config, shared templates and whois all
remain.

WHAT MUST NOT CHANGE
--------------------
The per-agent `Allow:` groups are reproduced verbatim from the committed files
and must stay that way. They are deliberate: under RFC 9309 a crawler merges
same-name groups, and an explicit `Allow: /` of equal specificity beats a
prepended blanket `Disallow: /` from a managed robots.txt. Removing or reordering
them would silently cut off AI answer engines and search crawlers. AGENT_GROUPS
below is the source of truth; do not prune it.
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Verbatim from the committed robots.txt files (commit b52ac32, "Welcome AI
# answer engines on all three library domains"). Order preserved.
AGENT_GROUPS = [
    "Googlebot", "Bingbot", "DuckDuckBot",
    "OAI-SearchBot", "GPTBot", "ChatGPT-User",
    "ClaudeBot", "Claude-User", "Claude-SearchBot", "anthropic-ai",
    "PerplexityBot", "Perplexity-User",
    "Google-Extended", "Applebot", "Applebot-Extended", "DuckAssistBot",
    "Amazonbot", "CCBot", "meta-externalagent", "Bytespider", "cohere-ai",
    "CloudflareBrowserRenderingCrawler",
]

PREAMBLE = """\
# {title} -- crawl policy
# {domain}
#
# {mission}
#
# Search engines and AI answer engines are explicitly welcome here.
# The per-agent Allow groups below are deliberate: they override any
# prepended blanket Disallow (e.g. Cloudflare managed robots.txt) for the
# same agent, because merged same-name groups resolve equal-length
# Allow/Disallow conflicts in favour of Allow.
#
# What is on this site:
{sections}#
# Editorial governance (who is responsible, how to report an error):
#   /masthead             ownership and the responsible editor
#   /editorial-standards  sourcing, AI-use disclosure, conflicts of interest
#   /corrections          corrections policy and the correction log
#   /contributors         byline policy
#
# Machine-readable summary of this publication: {home}/llms.txt
"""


def section_lines(folder: pathlib.Path) -> str:
    """Describe the real shape of this site, counted from the tree."""
    root_pages = sorted(p for p in folder.glob("*.html") if p.name != "404.html")
    daily = list((folder / "daily").glob("*.html"))
    topics = sorted((folder / "topics").glob("*.html"))

    out = []
    if topics:
        out.append(f"#   /topics/              {len(topics)} topic hubs, one per subject area")
        for t in topics:
            out.append(f"#     /topics/{t.stem}")
    if daily:
        out.append(f"#   /daily/               {len(daily)} dated articles")
    if root_pages:
        out.append(f"#   /                     {len(root_pages)} standing pages")
    return "".join(line + "\n" for line in out)


def render(pub: dict) -> str:
    folder = ROOT / pub["folder"]
    domain = pub["working_domain"]
    home = f"https://{domain}"
    body = PREAMBLE.format(
        title=pub["title"], domain=domain, mission=pub["mission"],
        sections=section_lines(folder), home=home,
    )
    groups = "\n".join(f"User-agent: {a}\nAllow: /\n" for a in AGENT_GROUPS)
    return (
        f"{body}\n{groups}\n"
        "User-agent: *\n"
        "Allow: /\n\n"
        f"Sitemap: {home}/sitemap.xml\n"
    )


def main() -> int:
    write = "--write" in sys.argv
    publications = json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))
    changed = []
    for pub in publications:
        target = ROOT / pub["folder"] / "robots.txt"
        text = render(pub)

        # Guard: every agent group that was in the committed file must survive.
        for agent in AGENT_GROUPS:
            if f"User-agent: {agent}\nAllow: /" not in text:
                raise SystemExit(f"{target}: lost the Allow group for {agent}")

        if target.exists() and target.read_text(encoding="utf-8") == text:
            continue
        changed.append(str(target.relative_to(ROOT)))
        if write:
            target.write_text(text, encoding="utf-8")
    print(json.dumps({"mode": "write" if write else "check", "changed": changed}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
