#!/usr/bin/env python3
"""What the edge actually serves, after a deploy -- not what the build produced.

Search Readiness checklist item h4. The build can pass and the edge can still
serve the wrong thing: every validator in this repository reads files in git,
and the three publications are served by Cloudflare Pages with a Pages
middleware, a _redirects file, a _headers file and three custom-domain
bindings in front of them. None of those are in the tree the validators read.

So this fetches each publication over HTTPS and checks the things that are only
true at the edge:

  canonical host    the apex answers 200 and www answers 301/308 to the apex on
                    the same path (item a1, the one the middleware implements)
  crawl files       robots.txt and sitemap.xml answer 200, are not redirected,
                    and robots.txt is served as text rather than the SPA
                    fallback -- a Worker that 301'd robots.txt is the failure
                    the checklist names
  icons and og      favicon.ico, favicon.svg, apple-touch-icon, the manifest
                    and the og:image the pages advertise all answer 200
  schema types      the homepage's JSON-LD parses and carries WebSite, WebPage
                    and an Organization with name, url, logo and sameAs
  measured URLs     a sample of sitemap URLs answer 200 without a redirect, so
                    a route that moved is caught before Search Console reports it
  IndexNow key      the key file named in the sitemap host's indexnow.txt
                    answers 200 with its own key as the body, when one is set

Spends nothing: plain GETs, no model, no paid API.

Exit 0 = every publication healthy. Exit 1 = a real defect at the edge.
Exit 2 = NAMED STOP: the site could not be reached at all (DNS, TLS, a
Cloudflare challenge), which is not the same as a defect in it and says so.

    python3 scripts/post_deploy_live_check.py [--wait-seconds N] [--domain d]
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib import head_seo as hs  # noqa: E402
from byline import entity_for  # noqa: E402

UA = "Mozilla/5.0 (compatible; AuthorityNetworkPostDeployCheck/1.0)"
TIMEOUT = 25
SITEMAP_SAMPLE = 8
CHALLENGE_RE = re.compile(r"cf-browser-verification|Just a moment|challenge-platform", re.I)


def get(url: str, *, follow: bool = False):
    """(status, final_url, body, error). `follow=False` reports the 3xx itself."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **kw):
            return None

    ctx = ssl.create_default_context()
    handlers = [] if follow else [NoRedirect()]
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), *handlers)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.geturl(), resp.read(400_000).decode("utf-8", "ignore"), None
    except urllib.error.HTTPError as exc:
        location = exc.headers.get("Location", "") if exc.headers else ""
        body = ""
        try:
            body = exc.read(4000).decode("utf-8", "ignore")
        except Exception:  # noqa: BLE001
            pass
        return exc.code, urljoin(url, location) if location else url, body, None
    except Exception as exc:  # noqa: BLE001 - DNS, TLS, timeout: unreachable, not a defect
        return 0, url, "", f"{type(exc).__name__}: {exc}"


def check_publication(pub: dict) -> dict:
    domain = pub["working_domain"]
    base = f"https://{domain}"
    entity = entity_for(pub["title"])
    failures: list[str] = []
    unreachable: list[str] = []
    checked = 0

    def note(status, final, err, url, want_status, *, want_final=None, label=""):
        nonlocal checked
        checked += 1
        if err:
            unreachable.append(f"{url}: {err}")
            return False
        if status not in want_status:
            failures.append(f"{label or url}: answered {status}, want {' or '.join(map(str, want_status))}")
            return False
        if want_final and final.rstrip("/") != want_final.rstrip("/"):
            failures.append(f"{label or url}: went to {final}, want {want_final}")
            return False
        return True

    # ---- canonical host (item a1, as the edge actually serves it)
    status, final, home, err = get(base + "/", follow=True)
    ok_home = note(status, final, err, base + "/", (200,), label=f"{domain} homepage")
    if home and CHALLENGE_RE.search(home):
        unreachable.append(f"{base}/: Cloudflare challenge page, not the site")
        ok_home = False
    status, final, _, err = get(f"https://www.{domain}/about")
    note(status, final, err, f"https://www.{domain}/about", (301, 308),
         want_final=f"{base}/about", label=f"www.{domain}/about")

    # ---- crawl files
    status, final, robots, err = get(base + "/robots.txt")
    if note(status, final, err, base + "/robots.txt", (200,), label=f"{domain} robots.txt"):
        if "sitemap" not in robots.lower():
            failures.append(f"{domain} robots.txt: names no sitemap")
        if "<html" in robots.lower():
            failures.append(f"{domain} robots.txt: served HTML, not robots.txt")
    status, final, sitemap, err = get(base + "/sitemap.xml")
    note(status, final, err, base + "/sitemap.xml", (200,), label=f"{domain} sitemap.xml")

    # ---- icons, manifest and the og:image the pages advertise
    for path in (hs.FAVICON_ICO, hs.FAVICON_SVG, hs.APPLE_TOUCH_ICON, hs.MANIFEST, hs.OG_IMAGE):
        status, final, _, err = get(f"{base}/{path}", follow=True)
        note(status, final, err, f"{base}/{path}", (200,), label=f"{domain}/{path}")

    # ---- schema types on the homepage, read from what the edge served
    if ok_home:
        types = hs.types_on(home)
        for want in ("WebSite", "WebPage"):
            if want not in types:
                failures.append(f"{domain} homepage: live HTML has no {want} node")
        ours = {entity.casefold(), pub["title"].casefold()}
        orgs = [n for n in hs.jsonld_nodes(home)
                if "Organization" in hs.node_types(n)
                and str(n.get("name", "")).casefold() in ours]
        if not orgs:
            failures.append(f"{domain} homepage: live HTML has no Organization for {entity}")
        for n in orgs:
            thin = [k for k in ("name", *hs.organization_identity(domain)) if not n.get(k)]
            if thin:
                failures.append(f"{domain} homepage: Organization {n.get('name')!r} lacks {', '.join(thin)}")

    # ---- measured URLs: a sample of the sitemap must answer 200 un-redirected
    urls = re.findall(r"<loc>([^<]+)</loc>", sitemap or "")
    if not urls:
        failures.append(f"{domain} sitemap.xml: no <loc> entries")
    step = max(1, len(urls) // SITEMAP_SAMPLE)
    for url in urls[::step][:SITEMAP_SAMPLE]:
        status, final, _, err = get(url)
        note(status, final, err, url, (200,), label=url)

    # ---- IndexNow key, when the site publishes one
    status, _, indexnow, err = get(base + "/indexnow.txt")
    if status == 200 and indexnow.strip():
        key = indexnow.strip().splitlines()[0].strip()
        if re.fullmatch(r"[A-Za-z0-9-]{8,128}", key):
            status, final, body, err = get(f"{base}/{key}.txt")
            if note(status, final, err, f"{base}/{key}.txt", (200,),
                    label=f"{domain} IndexNow key file") and body.strip() != key:
                failures.append(f"{domain} IndexNow key file: body is not the key")

    return {"domain": domain, "checks": checked,
            "failures": failures, "unreachable": unreachable}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait-seconds", type=int, default=0,
                    help="Re-run the whole check until it passes, up to this many seconds. "
                         "Cloudflare Pages builds AFTER the push that triggers this check, so "
                         "for a minute or two the edge is still serving the previous commit. "
                         "Waiting on the homepage answering 200 would not do: it answers 200 "
                         "throughout. Only the check itself can tell the new deploy from the old.")
    ap.add_argument("--domain", action="append", default=[],
                    help="Check only these domains (repeatable).")
    args = ap.parse_args()

    pubs = json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))
    if args.domain:
        wanted = {d.lower().removeprefix("www.") for d in args.domain}
        pubs = [p for p in pubs if p["working_domain"].lower() in wanted]

    deadline = time.time() + args.wait_seconds
    attempts = 0
    while True:
        attempts += 1
        results = [check_publication(p) for p in pubs]
        failures = [f for r in results for f in r["failures"]]
        unreachable = [u for r in results for u in r["unreachable"]]
        checks = sum(r["checks"] for r in results)
        if (not failures and not unreachable) or time.time() >= deadline:
            break
        time.sleep(20)

    # Rule 0: a check that examined nothing has proved nothing.
    if not pubs or not checks:
        print(json.dumps({"check": "post_deploy_live", "status": "FAIL",
                          "detail": "examined zero publications or zero URLs; this check vouches "
                                    "for what the edge serves and with nothing fetched it vouches "
                                    "for nothing",
                          "publications": len(pubs), "checks": checks}, indent=2))
        return 1

    status = "PASS" if not failures and not unreachable else ("FAIL" if failures else "NAMED_STOP")
    print(json.dumps({"check": "post_deploy_live", "status": status,
                      "publications": len(pubs), "urls_checked": checks,
                      "attempts": attempts, "hard_failures": len(failures),
                      "failures": failures, "unreachable": unreachable}, indent=2))
    if failures:
        return 1
    if unreachable:
        print("NAMED STOP: the site could not be reached, which is not the same as a defect in "
              "it. DNS, TLS or a Cloudflare challenge -- see `unreachable` above.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
