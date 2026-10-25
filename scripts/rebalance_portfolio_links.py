#!/usr/bin/env python3
"""Spread each publication's portfolio links across targets, onto the pages they strengthen.

Owner decision, 11 Oct 2026 (data/portfolio-link-policy.json):

  * no target domain receives more than `max_target_domain_share_of_site_portfolio_links`
    (25%) of one site's portfolio links;
  * no single target URL receives more than `max_links_per_target_url_per_site` (10);
  * every kept link points at a page listed in data/portfolio-deep-targets.json --
    a page the target site is measurably strengthening, live at build time -- and
    its anchor text is that page's own title.

What it changes on a page, and nothing else
-------------------------------------------
Only the portfolio <a> element itself. A kept link gets the best-matching deep
URL on the same domain (word overlap between this page's title/H1/cluster and
the target page's title and measured queries; the URL the generator originally
chose wins ties) and that page's title as its anchor. A surplus link -- one the
caps leave no room for -- is unlinked: the element is replaced by its own text,
so the sentence still reads and the page still answers its question. No link is
ever added to a page that did not already cite that domain, which keeps every
link contextual: it sits where the generator put it, inside the article body.

Which links survive a cap is chosen by topic fit first, then article pages over
hub/index lists, then newest first. data/link-registry.json is updated in the
same pass (retargeted rows get the new URL and anchor; unlinked rows move to
`withdrawn` with the reason), so citation_control keeps agreeing with the pages.

The same selection is imported by scripts/authority_v4_autopilot.py, so a newly
generated page is held to the caps at the moment its link is chosen.

    python3 scripts/rebalance_portfolio_links.py            # dry run, prints the plan
    python3 scripts/rebalance_portfolio_links.py --write
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from affiliation import host_of, is_portfolio, link_policy  # noqa: E402

SITES = ROOT / "sites"
TARGETS_PATH = ROOT / "data/portfolio-deep-targets.json"
ANCHOR_RE = re.compile(r'<a\s+([^>]*?)>(.*?)</a>', re.I | re.S)
HREF_RE = re.compile(r'href="([^"]+)"', re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
SKIP_PARTS = ("/agency/",)
STOP = set("""a an and are as at be before by can choose do does for from guide guides how i in is it
its of on or the this to what when where which who why with you your vs versus near me my
checklist question questions page pages template templates""".split())


def caps() -> tuple[float, int]:
    c = link_policy()["caps"]
    return float(c["max_target_domain_share_of_site_portfolio_links"]), int(c["max_links_per_target_url_per_site"])


_DEEP = None


def deep_targets() -> dict[str, list[dict]]:
    """data/portfolio-deep-targets.json, with each URL spelled as brands.json registers it.

    A target page reachable at both https://example.com/ and https://www.example.com/
    is linked at the spelling the allowlist already holds, so hostile_review's
    exact-URL metadata lookup and the live link agree.
    """
    global _DEEP
    if _DEEP is None:
        data = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))["targets"]
        registered = {}
        for b in json.loads((ROOT / "data/brands.json").read_text(encoding="utf-8")):
            for l in b.get("approved_links", []):
                u = str(l.get("url", ""))
                if u.startswith("http") and l.get("source") != "data/portfolio-deep-targets.json":
                    registered.setdefault(norm_url(u), u)
        for rows in data.values():
            for t in rows:
                t["url"] = registered.get(norm_url(t["url"]), t["url"])
        _DEEP = data
    return _DEEP


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", html.unescape(text).lower())
            if len(w) > 2 and w not in STOP}


def norm_url(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url.strip()).rstrip("/").lower()


def page_subject(text: str, cluster: str = "") -> set[str]:
    parts = [cluster]
    for rx in (TITLE_RE, H1_RE):
        m = rx.search(text)
        if m:
            parts.append(TAG_RE.sub(" ", m.group(1)))
    return words(" ".join(parts))


def fit(subject: set[str], target: dict) -> int:
    tw = words(target["title"] + " " + " ".join(target.get("queries", [])))
    return len(subject & tw)


def rank_targets(domain: str, subject: set[str], original_url: str = "",
                 campaign: str = "") -> list[tuple[int, dict]]:
    """Deep targets on `domain`, best first: (fit score, target).

    A campaign with a declared destination (portfolio-link-policy
    `campaign_destinations`) is offered that page only.
    """
    pinned = link_policy().get("campaign_destinations", {}).get(campaign) if campaign else None
    out = []
    for t in deep_targets().get(domain, []):
        if pinned and norm_url(t["url"]) != norm_url(pinned):
            continue
        # No bonus for the URL the page already carries: the choice must depend
        # only on the page's subject, so a second run reproduces the first.
        score = fit(subject, t) * 2
        if t.get("home"):
            score -= 2
        out.append((score, t))
    out.sort(key=lambda x: (-x[0], x[1]["url"]))
    return out


def domain_quota(counts: dict[str, int], share: float) -> dict[str, int]:
    """Largest per-domain K with sum(min(c, K)) * share >= K, applied to every domain."""
    if not counts:
        return {}
    best = 0
    for k in range(1, max(counts.values()) + 1):
        total = sum(min(c, k) for c in counts.values())
        if k <= total * share + 1e-9:
            best = k
    return {d: min(c, best) for d, c in counts.items()}


def is_article(rel: str) -> bool:
    return "/daily/" in rel or "/articles/" in rel


def registry_campaigns() -> dict[tuple[str, str], list[str]]:
    """(source_path, normalised url) -> campaign ids of the published registry rows."""
    out: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in json.loads((ROOT / "data/link-registry.json").read_text(encoding="utf-8")):
        if row.get("status") == "published" and row.get("campaign_id"):
            out[(row.get("source_path", ""), norm_url(row.get("target_url", "")))].append(row["campaign_id"])
    return out


def campaign_floors() -> dict[str, int]:
    doc = json.loads((ROOT / "data/portfolio-backlink-campaigns.json").read_text(encoding="utf-8"))
    return {c["id"]: int(c.get("minimum_rendered_coverage", 0)) for c in doc.get("campaigns", [])}


def campaign_destination_floors() -> dict[str, int]:
    """{campaign id: minimum_distinct_destinations}.

    The count floor above says how many links a campaign keeps; this says how
    many different pages they may not collapse onto. Both are asserted by
    tests/test_portfolio_backlink_system.py, and until 25 Oct 2026 this one was
    asserted and nothing honoured it: the spread penalty below is site-wide, so
    two links of one campaign could both take the destination with the best fit
    whenever the runner-up scored more than the penalty lower.
    dentistry-guides-authority went from two destinations to one that way, the
    moment a nineteenth portfolio domain changed the quota arithmetic.
    """
    doc = json.loads((ROOT / "data/portfolio-backlink-campaigns.json").read_text(encoding="utf-8"))
    return {c["id"]: int(c.get("minimum_distinct_destinations", 0)) for c in doc.get("campaigns", [])}


def survey(site: Path) -> list[dict]:
    """Every portfolio link on a site: page, element span, url, domain, subject."""
    import measure_affiliate_topical_fit as fitmod
    subjects = fitmod.page_subjects()
    campaigns = registry_campaigns()
    rows = []
    for path in sorted(site.rglob("*.html")):
        rel = path.relative_to(ROOT).as_posix()
        if any(p in "/" + rel for p in SKIP_PARTS) or path.name == "404.html":
            continue
        text = path.read_text(encoding="utf-8")
        key = path.relative_to(SITES).as_posix()
        subject = page_subject(text, subjects.get(key, ("", ""))[1])
        for m in ANCHOR_RE.finditer(text):
            href = HREF_RE.search(m.group(1))
            if not href or not is_portfolio(href.group(1)):
                continue
            rows.append({"path": path, "rel": rel, "start": m.start(), "end": m.end(),
                         "attrs": m.group(1), "inner": m.group(2), "url": href.group(1),
                         "domain": host_of(href.group(1)), "subject": subject,
                         "article": is_article(rel), "name": path.name,
                         "campaign": (campaigns.get((rel, norm_url(href.group(1)))) or [""])[0]})
    return rows


def plan_site(rows: list[dict]) -> list[dict]:
    """Decide, per link: keep (with its new url/anchor) or unlink."""
    share, per_url = caps()
    by_domain: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        r["ranked"] = rank_targets(r["domain"], r["subject"], r["url"], r["campaign"])
        r["fit"] = r["ranked"][0][0] if r["ranked"] else -99
        by_domain[r["domain"]].append(r)
    # A domain can hold at most per_url links per catalogued URL.
    capacity = {d: min(len(rs), per_url * len(deep_targets().get(d, []))) for d, rs in by_domain.items()}
    quota = domain_quota({d: c for d, c in capacity.items() if c > 0}, share)
    floors = campaign_floors()
    dest_floors = campaign_destination_floors()
    campaign_used: dict[str, set] = defaultdict(set)
    for d, rs in by_domain.items():
        order = sorted(rs, key=lambda r: (-r["fit"], 0 if r["article"] else 1,
                                          "".join(chr(255 - ord(ch)) for ch in r["name"])))
        # Campaign floors first: the best-fitting `floor` rows of each campaign.
        protected, seen = [], Counter()
        for r in order:
            if r["campaign"] and seen[r["campaign"]] < floors.get(r["campaign"], 0):
                seen[r["campaign"]] += 1
                protected.append(r)
        rs_sorted = protected + [r for r in order if r not in protected]
        used: Counter = Counter()
        on_page: dict[Path, set] = defaultdict(set)
        kept = 0
        for r in rs_sorted:
            r["action"] = "unlink"
            if kept >= quota.get(d, 0):
                continue
            # Spread: each earlier use of a URL on this site costs it 2 points, so
            # equally good pages share the links instead of one page taking them all.
            ranked = sorted(r["ranked"], key=lambda st: (-(st[0] - 2 * used[st[1]["url"]]), st[1]["url"]))
            # A campaign still short of its distinct-destination floor takes a
            # page it has not used yet, before fit. Fit decides WHICH unused
            # page; it cannot decide to use none. Once the floor is met the
            # campaign chooses on fit like any other link.
            campaign = r["campaign"]
            need_spread = (campaign
                           and len(campaign_used[campaign]) < dest_floors.get(campaign, 0))
            passes = ([[st for st in ranked if st[1]["url"] not in campaign_used[campaign]]]
                      if need_spread else []) + [ranked]
            for candidates in passes:
                for score, t in candidates:
                    if used[t["url"]] >= per_url or t["url"] in on_page[r["path"]]:
                        continue
                    used[t["url"]] += 1
                    on_page[r["path"]].add(t["url"])
                    if campaign:
                        campaign_used[campaign].add(t["url"])
                    r.update(action="keep", new_url=t["url"], new_anchor=t["title"])
                    kept += 1
                    break
                if r["action"] == "keep":
                    break
    return rows


def render(r: dict) -> str:
    if r["action"] == "unlink":
        return r["inner"]
    attrs = HREF_RE.sub(f'href="{html.escape(r["new_url"], quote=True)}"', r["attrs"], count=1)
    attrs = re.sub(r'\s+rel="[^"]*"', "", attrs)  # portfolio links are followed
    return f"<a {attrs.strip()}>{html.escape(r['new_anchor'], quote=False)}</a>"


def apply(rows: list[dict], write: bool) -> int:
    by_path: dict[Path, list[dict]] = defaultdict(list)
    for r in rows:
        by_path[r["path"]].append(r)
    changed = 0
    for path, rs in by_path.items():
        text = path.read_text(encoding="utf-8")
        out = text
        for r in sorted(rs, key=lambda r: r["start"], reverse=True):
            out = out[:r["start"]] + render(r) + out[r["end"]:]
        if out != text:
            changed += 1
            if write:
                path.write_text(out, encoding="utf-8")
    return changed


def registered_meta(url: str) -> dict:
    """The brands.json approved_links entry for `url` (exact spelling, then normalised)."""
    for b in json.loads((ROOT / "data/brands.json").read_text(encoding="utf-8")):
        for l in b.get("approved_links", []):
            if str(l.get("url", "")).rstrip("/") == url.rstrip("/"):
                return l
    return {}


def update_registry(rows: list[dict], write: bool) -> tuple[int, int]:
    path = ROOT / "data/link-registry.json"
    reg = json.loads(path.read_text(encoding="utf-8"))
    today = date.today().isoformat()
    moves: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        moves[(r["rel"], norm_url(r["url"]))].append(r)
    retargeted = withdrawn = 0
    for row in reg:
        if row.get("status") != "published":
            continue
        key = (row.get("source_path", ""), norm_url(row.get("target_url", "")))
        if key not in moves or not moves[key]:
            continue
        r = moves[key].pop(0)
        if r["action"] == "keep":
            meta_now = registered_meta(r["new_url"])
            stale = any(row.get(f, "") != meta_now.get(k, "") for f, k in (
                ("product_id", "product_id"), ("destination_type", "destination_type"), ("target_route", "route")))
            if row.get("target_url") != r["new_url"] or row.get("anchor") != r["new_anchor"] or stale:
                row.setdefault("previous_target_url", row.get("target_url"))
                row["target_url"] = r["new_url"]
                row["anchor"] = r["new_anchor"]
                meta = registered_meta(r["new_url"])
                for field, key in (("product_id", "product_id"), ("destination_type", "destination_type"),
                                   ("product_name", "product_name"), ("target_route", "route")):
                    row[field] = meta.get(key, "")
                row["retargeted_on"] = today
                row["retargeted_reason"] = ("portfolio-link-policy: deep link to a page the target "
                                            "site is strengthening, anchor = that page's title")
                retargeted += 1
        else:
            row["status"] = "withdrawn"
            row["lifecycle_stage"] = "approved_destination"
            row["withdrawn_on"] = today
            row["withdrawn_reason"] = ("portfolio-link-policy caps: unlinked to keep the target under "
                                       "25% of this site's portfolio links / 10 links per URL")
            for k in list((row.get("evidence") or {}).keys()):
                row["evidence"][k] = False
            withdrawn += 1
    if write:
        path.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return retargeted, withdrawn


_SITE_URL_COUNTS: dict[str, Counter] = {}


def choose_for_new_page(site_folder: str, domain: str, subject_text: str,
                        campaign: str = "") -> dict | None:
    """The deep target a NEW page on `site_folder` should link for `domain`.

    Called by scripts/authority_v4_autopilot.py when it picks a portfolio link,
    so a generated page starts on a strengthened page with that page's title as
    anchor, and never on a URL that already holds the per-URL cap on this site.
    Returns None when every catalogued URL on the domain is full: the slot is
    declined rather than given an off-cap link. The domain-share cap is then
    restored by this script's --write pass, which the autopilot workflow runs
    right after generation (an equal 25/25/25/25 split can only grow one link
    at a time, so the share is settled after the page exists, not before).
    """
    _, per_url = caps()
    site = SITES / site_folder
    if site_folder not in _SITE_URL_COUNTS:
        used: Counter = Counter()
        for path in site.rglob("*.html"):
            for m in ANCHOR_RE.finditer(path.read_text(encoding="utf-8", errors="ignore")):
                href = HREF_RE.search(m.group(1))
                if href and is_portfolio(href.group(1)):
                    used[norm_url(href.group(1))] += 1
        _SITE_URL_COUNTS[site_folder] = used
    used = _SITE_URL_COUNTS[site_folder]
    for _score, t in rank_targets(domain, words(subject_text), campaign=campaign):
        if used[norm_url(t["url"])] < per_url:
            used[norm_url(t["url"])] += 1
            return t
    return None


def register_destinations(rows: list[dict], write: bool) -> int:
    """Register every kept deep URL in data/brands.json approved_links.

    scripts/hostile_review.py refuses a destination with no registered metadata,
    which is the right rule: brands.json is the allowlist of where these
    publications may link. A deep target joins it with its own title as anchor
    and the measured queries that admitted it as topics. An already-registered
    URL keeps its existing metadata.
    """
    from urllib.parse import urlparse
    path = ROOT / "data/brands.json"
    brands = json.loads(path.read_text(encoding="utf-8"))
    by_host = {}
    for b in brands:
        for d in (b.get("domains") or [b.get("domain", "")]):
            by_host[host_of("https://" + d)] = b
    by_url = {(r["new_url"], r["new_anchor"]) for r in rows if r["action"] == "keep"}
    added = 0
    for url, anchor in sorted(by_url):
        brand = by_host.get(host_of(url))
        if brand is None:
            continue
        links = brand.setdefault("approved_links", [])
        if any(norm_url(l.get("url", "")) == norm_url(url) for l in links):
            continue
        target = next((t for t in deep_targets().get(host_of(url), []) if t["url"] == url), {})
        entry = {"url": url, "destination_type": "educational_guide", "anchor": anchor,
                 "topics": ["*"], "source": "data/portfolio-deep-targets.json",
                 "measured_queries": target.get("queries", [])[:6]}
        if brand.get("id") == "dream-wedding-builder":
            entry["route"] = urlparse(url).path or "/"
        links.append(entry)
        added += 1
    if write and added:
        path.write_text(json.dumps(brands, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return added


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    all_rows = []
    print("PORTFOLIO LINK REBALANCE")
    for site in sorted(p for p in SITES.iterdir() if p.is_dir()):
        rows = plan_site(survey(site))
        all_rows += rows
        kept = Counter(r["domain"] for r in rows if r["action"] == "keep")
        total = sum(kept.values())
        top = max(kept.values()) / total if total else 0
        print(f"  {site.name}: {len(rows)} -> {total} links kept, max domain share {top:.0%}")
        for d, n in kept.most_common():
            print(f"      {d:40s} {n}")
    pages = apply(all_rows, args.write)
    registered = register_destinations(all_rows, args.write)
    retargeted, withdrawn = update_registry(all_rows, args.write)
    unlinked = sum(1 for r in all_rows if r["action"] == "unlink")
    print(f"  pages {'rewritten' if args.write else 'to rewrite'}: {pages}; links unlinked: {unlinked}; "
          f"registry rows retargeted {retargeted}, withdrawn {withdrawn}; destinations registered {registered}")
    if not args.write:
        print("  dry run; re-run with --write to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
