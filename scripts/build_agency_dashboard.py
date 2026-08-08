#!/usr/bin/env python3
"""Build the owner-facing /agency backlink and operator dashboard.

The dashboard is a generated, read-only view over canonical repo data. It does not
create a second control plane: targets come from brands.json, backlink evidence from
link-registry.json, publication identities from publications.json, and runtime
operator commands from package.json / active workflow files.
"""
from __future__ import annotations

import html
import json
import os
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA_OUT = ROOT / "data" / "agency-dashboard.json"
PAGE_OUT = ROOT / "sites" / "founder-operator" / "agency" / "index.html"
REPORT_OUT = ROOT / "reports" / "agency-dashboard-build.json"
AS_OF = os.getenv("PUBLIC_RELEASE_DATE") or os.getenv("BUILD_DATE") or date.today().isoformat()


def read_json(rel: str, default):
    path = ROOT / rel
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def clean_url(value: str) -> str:
    return (value or "").rstrip("/")


def source_publication(row: dict, publications: list[dict]) -> dict:
    by_id = {p["id"]: p for p in publications}
    by_folder = {p["folder"]: p for p in publications}
    raw = row.get("source_publication") or ""
    if raw in by_id:
        return by_id[raw]
    source_path = row.get("source_path") or ""
    for folder, pub in by_folder.items():
        if source_path == folder or source_path.startswith(folder + "/"):
            return pub
    # Historical autopilot rows sometimes use folder slugs.
    for pub in publications:
        if pub["folder"].split("/")[-1] == raw:
            return pub
    return {}


def source_url(row: dict, publications: list[dict]) -> str:
    pub = source_publication(row, publications)
    if not pub:
        return ""
    path = row.get("source_path") or ""
    folder = pub["folder"].rstrip("/") + "/"
    if not path.startswith(folder):
        return ""
    rel = path[len(folder):]
    if rel == "index.html":
        rel = ""
    return f"https://{pub['working_domain']}/{rel}".replace("//daily", "/daily")


def source_title(row: dict) -> str:
    path = ROOT / (row.get("source_path") or "")
    if not path.exists() or path.suffix.lower() != ".html":
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.I | re.S)
    if not match:
        match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    if not match:
        return ""
    value = re.sub(r"<[^>]+>", " ", match.group(1))
    return html.unescape(re.sub(r"\s+", " ", value)).strip()


def workflow_registry() -> list[dict]:
    rows = []
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"^name:\s*(.+?)\s*$", text, re.M)
        name = m.group(1).strip().strip('"\'') if m else path.stem
        crons = re.findall(r"cron:\s*['\"]([^'\"]+)['\"]", text)
        rows.append({
            "name": name,
            "path": path.relative_to(ROOT).as_posix(),
            "scheduled": bool(crons),
            "cron": crons,
            "manual_dispatch": "workflow_dispatch:" in text,
        })
    return rows


def operator_category(name: str) -> str:
    if name.startswith(("validate:", "release:", "check", "review", "audit:")):
        return "Validation / release"
    if name.startswith(("backlinks:", "citation:")):
        return "Backlinks / citation"
    if name.startswith(("social:", "distribution:")):
        return "Distribution / social"
    if name.startswith(("cache:", "trace:")):
        return "Support / diagnostics"
    if name.startswith(("autopilot", "agency:", "build:")):
        return "Generation / operator surfaces"
    return "Other"


def operator_registry() -> list[dict]:
    package = read_json("package.json", {})
    scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
    preferred = [
        "autopilot", "agency:build",
        "backlinks:seed", "backlinks:repair", "backlinks:verify", "backlinks:health",
        "citation:dashboard", "citation:verify-repo", "citation:import-manifests",
        "distribution:prepare-indexnow", "distribution:run",
        "social:drafts", "social:dry-run",
        "validate:changed", "validate:release", "validate:full", "validate:clean-rebuild", "validate:cache:self-test",
        "review", "audit:links", "release:prepush", "release:prepush:local", "check",
        "build:deterministic", "cache:clear", "trace:github-actions",
    ]
    order = {name: i for i, name in enumerate(preferred)}
    rows = []
    for name, command in scripts.items():
        rows.append({
            "operator": name,
            "command": f"npm run {name}",
            "implementation": command,
            "category": operator_category(name),
        })
    return sorted(rows, key=lambda r: (order.get(r["operator"], 999), r["operator"]))


def release_operator_registry() -> list[dict]:
    contract = read_json("_repo_update_contract.json", {})
    commands = contract.get("commands", {}) if isinstance(contract, dict) else {}
    return [
        {"operator": name, "command": command or "NOT_APPLICABLE"}
        for name, command in commands.items()
    ]


def build_model() -> dict:
    brands = read_json("data/brands.json", [])
    publications = read_json("data/publications.json", [])
    campaigns = read_json("data/portfolio-backlink-campaigns.json", {"campaigns": []}).get("campaigns", [])
    links = read_json("data/link-registry.json", [])
    if isinstance(links, dict):
        links = links.get("links", [])

    link_rows_by_target: dict[str, list[dict]] = defaultdict(list)
    for row in links:
        target = clean_url(row.get("target_url") or "")
        if not target:
            continue
        evidence = row.get("evidence") or {}
        link_rows_by_target[target].append({
            "source_path": row.get("source_path", ""),
            "source_url": source_url(row, publications),
            "source_title": source_title(row),
            "publication": (source_publication(row, publications) or {}).get("title", row.get("source_publication", "")),
            "publication_id": (source_publication(row, publications) or {}).get("id", row.get("source_publication", "")),
            "scheduled_content_date": row.get("scheduled_content_date") or row.get("date") or "",
            "release_date": row.get("release_date") or row.get("date") or "",
            "anchor": row.get("anchor", ""),
            "campaign_id": row.get("campaign_id", ""),
            "status": row.get("status", ""),
            "lifecycle_stage": row.get("lifecycle_stage", ""),
            "repository_rendered": bool(evidence.get("repository_rendered")),
            "deployed": bool(evidence.get("deployed")),
            "live_verified": bool(evidence.get("live_verified")),
            "indexed": bool(evidence.get("indexed")),
            "search_visibility_observed": bool(evidence.get("search_visibility_observed")),
            "ai_cited": bool(evidence.get("ai_cited")),
            "score": row.get("score"),
        })

    campaigns_by_brand: dict[str, list[dict]] = defaultdict(list)
    for campaign in campaigns:
        campaigns_by_brand[campaign.get("brand_id", "")].append(campaign)

    targets = []
    seen = set()
    for brand in brands:
        for approved in brand.get("approved_links", []):
            target_url = approved.get("url") or ""
            key = clean_url(target_url)
            if not key or key in seen:
                continue
            seen.add(key)
            backrefs = sorted(link_rows_by_target.get(key, []), key=lambda r: (r.get("release_date", ""), r.get("source_path", "")), reverse=True)
            targets.append({
                "brand_id": brand.get("id", ""),
                "brand": brand.get("name", brand.get("id", "")),
                "lane": brand.get("lane", ""),
                "category": brand.get("category", ""),
                "target_url": target_url,
                "target_domain": urlparse(target_url).netloc.replace("www.", ""),
                "default_anchor": approved.get("anchor", ""),
                "destination_type": approved.get("destination_type", ""),
                "product_id": approved.get("product_id", ""),
                "product_name": approved.get("product_name", ""),
                "campaign_ids": sorted({c.get("id", "") for c in campaigns_by_brand.get(brand.get("id", ""), []) if c.get("id")}),
                "backlink_count": len(backrefs),
                "live_verified_count": sum(r["live_verified"] for r in backrefs),
                "indexed_count": sum(r["indexed"] for r in backrefs),
                "backlinks": backrefs,
            })

    # Truthfully surface any historical ledger target that no longer appears in the approved registry.
    for key, backrefs in link_rows_by_target.items():
        if key in seen:
            continue
        sample = next((row for row in links if clean_url(row.get("target_url") or "") == key), {})
        normalized = sorted(backrefs, key=lambda r: (r.get("release_date", ""), r.get("source_path", "")), reverse=True)
        targets.append({
            "brand_id": sample.get("target_brand_id", ""),
            "brand": sample.get("brand", sample.get("target_brand_id", "Historical / retired target")),
            "lane": "historical",
            "category": "ledger target not present in current approved registry",
            "target_url": sample.get("target_url", key),
            "target_domain": sample.get("target_domain", urlparse(key).netloc.replace("www.", "")),
            "default_anchor": sample.get("anchor", ""),
            "destination_type": sample.get("destination_type", ""),
            "product_id": sample.get("product_id", ""),
            "product_name": sample.get("product_name", ""),
            "campaign_ids": sorted({r.get("campaign_id", "") for r in normalized if r.get("campaign_id")}),
            "backlink_count": len(normalized),
            "live_verified_count": sum(r["live_verified"] for r in normalized),
            "indexed_count": sum(r["indexed"] for r in normalized),
            "backlinks": normalized,
            "registry_status": "HISTORICAL_NOT_CURRENTLY_APPROVED",
        })

    targets.sort(key=lambda r: (r["brand"].lower(), r["target_url"]))
    runtime_operators = operator_registry()
    release_operators = release_operator_registry()
    workflows = workflow_registry()
    publication_operators = [
        {
            "id": p.get("id", ""),
            "name": p.get("title", ""),
            "domain": p.get("working_domain", ""),
            "folder": p.get("folder", ""),
            "status": p.get("status", "active"),
            "supports": p.get("supports", []),
        }
        for p in publications
    ]

    total_backlinks = sum(len(v) for v in link_rows_by_target.values())
    serviced = sum(1 for t in targets if t["backlink_count"] > 0)
    unique_sources = len({r["source_path"] for rows in link_rows_by_target.values() for r in rows if r.get("source_path")})
    return {
        "schema": "authority-agency-dashboard-v1",
        "as_of": AS_OF,
        "truth_boundary": "Repository backlink rows prove owned-network editorial placement only. Live, indexed, search-visible, or AI-cited states require their own evidence flags.",
        "summary": {
            "publication_operators": len(publication_operators),
            "runtime_operators": len(runtime_operators),
            "release_operators": len(release_operators),
            "workflow_operators": len(workflows),
            "approved_target_urls": sum(1 for t in targets if t.get("registry_status") != "HISTORICAL_NOT_CURRENTLY_APPROVED"),
            "serviced_target_urls": serviced,
            "backlink_rows": total_backlinks,
            "unique_source_editorials": unique_sources,
            "live_verified_rows": sum(t["live_verified_count"] for t in targets),
            "indexed_rows": sum(t["indexed_count"] for t in targets),
        },
        "publication_operators": publication_operators,
        "runtime_operators": runtime_operators,
        "release_operators": release_operators,
        "workflow_operators": workflows,
        "targets": targets,
    }


def esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


def status_label(row: dict) -> str:
    if row.get("ai_cited"):
        return "AI cited"
    if row.get("search_visibility_observed"):
        return "Search visibility observed"
    if row.get("indexed"):
        return "Indexed"
    if row.get("live_verified"):
        return "Live verified"
    if row.get("deployed"):
        return "Deployed"
    if row.get("repository_rendered"):
        return "In repository"
    return row.get("lifecycle_stage") or row.get("status") or "Recorded"


def render_html(model: dict) -> str:
    summary = model["summary"]
    publication_cards = "".join(
        f'''<article class="operator-card"><p class="kicker">Publication operator</p><h3>{esc(p['name'])}</h3><p><code>{esc(p['id'])}</code></p><p><a href="https://{esc(p['domain'])}/">{esc(p['domain'])}</a></p><p class="muted">Source: <code>{esc(p['folder'])}</code></p></article>'''
        for p in model["publication_operators"]
    )
    runtime_rows = "".join(
        f'''<tr><td><strong>{esc(o['operator'])}</strong><br><span class="pill">{esc(o['category'])}</span></td><td><code>{esc(o['command'])}</code></td><td><code>{esc(o['implementation'])}</code></td></tr>'''
        for o in model["runtime_operators"]
    )
    release_rows = "".join(
        f"<tr><td><strong>{esc(o['operator'])}</strong></td><td><code>{esc(o['command'])}</code></td></tr>"
        for o in model["release_operators"]
    )
    workflow_rows = "".join(
        f'''<tr><td><strong>{esc(w['name'])}</strong></td><td><code>{esc(w['path'])}</code></td><td>{'Manual + scheduled' if w['manual_dispatch'] and w['scheduled'] else ('Scheduled' if w['scheduled'] else ('Manual' if w['manual_dispatch'] else 'Event-driven'))}</td><td>{esc(', '.join(w['cron']) or '—')}</td></tr>'''
        for w in model["workflow_operators"]
    )
    target_blocks = []
    for target in model["targets"]:
        rows = []
        for backlink in target["backlinks"]:
            source_link = f'<a href="{esc(backlink["source_url"])}">{esc(backlink["source_title"] or backlink["source_path"])}</a>' if backlink.get("source_url") else esc(backlink["source_title"] or backlink["source_path"])
            rows.append(
                f'''<tr><td>{source_link}<br><span class="muted">{esc(backlink['publication'])}</span></td><td>{esc(backlink['scheduled_content_date'])}</td><td>{esc(backlink['release_date'])}</td><td>{esc(backlink['anchor'])}</td><td><span class="status">{esc(status_label(backlink))}</span></td><td><code>{esc(backlink['campaign_id'])}</code></td></tr>'''
            )
        body = "".join(rows) if rows else '<tr><td colspan="6" class="empty">No Authority Network editorial has been recorded for this approved target URL yet.</td></tr>'
        registry_note = '<span class="warn">Historical / no longer in current approved target registry</span>' if target.get("registry_status") else ''
        target_blocks.append(
            f'''<details class="target" data-search="{esc(' '.join([target['brand'], target['target_url'], target.get('category',''), ' '.join(target.get('campaign_ids',[]))]).lower())}">
<summary><span><strong>{esc(target['brand'])}</strong><br><a href="{esc(target['target_url'])}">{esc(target['target_url'])}</a> {registry_note}</span><span class="counts">{target['backlink_count']} backlink{'' if target['backlink_count']==1 else 's'} · {target['live_verified_count']} live verified</span></summary>
<div class="target-meta"><span>Lane: <strong>{esc(target['lane'])}</strong></span><span>Default anchor: <strong>{esc(target['default_anchor'])}</strong></span><span>Campaigns: <code>{esc(', '.join(target['campaign_ids']) or '—')}</code></span></div>
<div class="table-wrap"><table><thead><tr><th>Editorial / source URL</th><th>Scheduled</th><th>Released</th><th>Anchor</th><th>Evidence</th><th>Campaign</th></tr></thead><tbody>{body}</tbody></table></div>
</details>'''
        )

    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive"><title>Authority Network Agency | Backlink Operations</title>
<meta name="description" content="Owner operational view of Authority Network target URLs, editorial backlinks, publication operators, and canonical commands.">
<link rel="canonical" href="https://founderoperatorlibrary.com/agency/"><link rel="stylesheet" href="../styles.css">
<style>
body{{background:#f4f1ea}} main.agency{{max-width:1500px;padding-top:32px}} .top{{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;flex-wrap:wrap}} .top h1{{font-size:38px}} .badge{{display:inline-block;background:#162033;color:#fff;padding:7px 11px;border-radius:999px;font-size:12px;font-weight:700;letter-spacing:.04em}} .truth{{background:#fff7dc;border:1px solid #ead28e;border-radius:12px;padding:14px 16px;max-width:950px}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:22px 0}} .stat{{background:#fff;border:1px solid #ddd3c3;border-radius:14px;padding:16px}} .stat strong{{display:block;font-size:28px}} .stat span{{font-size:13px;color:#665b4f}}
.operator-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}} .operator-card{{background:white;border:1px solid #ddd3c3;border-radius:14px;padding:16px}} .operator-card h3{{margin:3px 0 8px}} .kicker{{font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:#7a6132;font-weight:700}} code{{white-space:normal;overflow-wrap:anywhere}}
.table-wrap{{overflow:auto}} table{{width:100%;border-collapse:collapse;background:white}} th,td{{text-align:left;vertical-align:top;padding:10px 12px;border-bottom:1px solid #ece5da;font-size:13px}} th{{background:#f0eadf;position:sticky;top:0}} .pill,.status{{display:inline-block;padding:3px 7px;border-radius:999px;background:#ece8df;font-size:11px}} .muted{{color:#766b60;font-size:12px}} .warn{{font-size:11px;color:#8b3d00;margin-left:8px}}
.filters{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:16px 0}} .filters input{{flex:1;min-width:260px;padding:12px 14px;border:1px solid #cfc4b3;border-radius:10px;font:inherit}} .filters button{{padding:10px 14px;border:0;border-radius:10px;background:#162033;color:#fff;cursor:pointer}}
.target{{background:#fff;border:1px solid #dcd1c0;border-radius:14px;margin:10px 0;overflow:hidden}} .target summary{{cursor:pointer;padding:15px 16px;display:flex;justify-content:space-between;gap:20px;align-items:center;list-style:none}} .target summary::-webkit-details-marker{{display:none}} .target summary:hover{{background:#fbf8f2}} .counts{{white-space:nowrap;font-size:12px;color:#665b4f}} .target-meta{{display:flex;gap:16px;flex-wrap:wrap;padding:10px 16px;background:#f8f4ed;font-size:12px}} .empty{{padding:20px;color:#766b60;font-style:italic}}
section{{margin:34px 0}} h2{{margin-bottom:10px}} .section-note{{margin-top:0;color:#655d55}} @media(max-width:700px){{.target summary{{align-items:flex-start;flex-direction:column}}.counts{{white-space:normal}}}}
</style></head>
<body><header><strong>Authority Network — Agency Operations</strong><nav><a href="/agency/">Agency Dashboard</a></nav></header>
<main class="agency">
<div class="top"><div><span class="badge">OWNER / OPERATOR VIEW · NOINDEX</span><p class="eyebrow">Authority Network control visibility</p><h1>Targets, backlinks, and canonical operators</h1><p class="dek">One read-only page showing which URLs the network is servicing, every editorial backlink recorded for each target, and the commands/workflows that operate the system.</p></div><p class="muted">As of {esc(model['as_of'])}</p></div>
<p class="truth"><strong>Truth boundary:</strong> {esc(model['truth_boundary'])}</p>
<div class="stats"><div class="stat"><strong>{summary['approved_target_urls']}</strong><span>approved target URLs</span></div><div class="stat"><strong>{summary['serviced_target_urls']}</strong><span>serviced target URLs</span></div><div class="stat"><strong>{summary['backlink_rows']}</strong><span>backlink ledger rows</span></div><div class="stat"><strong>{summary['unique_source_editorials']}</strong><span>unique source editorials</span></div><div class="stat"><strong>{summary['live_verified_rows']}</strong><span>live-verified rows</span></div><div class="stat"><strong>{summary['indexed_rows']}</strong><span>indexed rows</span></div></div>
<section><h2>Canonical publication operators</h2><p class="section-note">These are the three publication identities that publish Authority Network editorials.</p><div class="operator-grid">{publication_cards}</div></section>
<section><h2>Canonical runtime operators</h2><p class="section-note">Complete current <code>package.json</code> command inventory. Use these names when you forget which operator does what; the implementation column shows the exact underlying command.</p><div class="table-wrap"><table><thead><tr><th>Operator</th><th>Canonical command</th><th>Implementation</th></tr></thead><tbody>{runtime_rows}</tbody></table></div></section>
<section><h2>Canonical release operators</h2><p class="section-note">Repository update-contract operators used for validation, release, post-push observation, and live proof.</p><div class="table-wrap"><table><thead><tr><th>Operator</th><th>Exact contract command</th></tr></thead><tbody>{release_rows}</tbody></table></div></section>
<section><h2>Canonical workflow operators</h2><p class="section-note">Active GitHub Actions entry points that run the system on schedules, events, or manual dispatch.</p><div class="table-wrap"><table><thead><tr><th>Workflow</th><th>File</th><th>Trigger model</th><th>Cron</th></tr></thead><tbody>{workflow_rows}</tbody></table></div></section>
<section><h2>Target URL → editorial backlink ledger</h2><p class="section-note">All currently approved target URLs are listed, even when backlink count is zero. Historical ledger targets that are no longer approved remain visible and labeled rather than being silently dropped.</p><div class="filters"><input id="filter" type="search" placeholder="Filter brand, target URL, campaign…"><button type="button" onclick="setOpen(true)">Expand all</button><button type="button" onclick="setOpen(false)">Collapse all</button></div><div id="targets">{''.join(target_blocks)}</div></section>
<section><h2>Operator note</h2><p><strong>Affiliation disclosed:</strong> this is an owner operations page for an affiliated network. It is intentionally excluded from public navigation, sitemap discovery, and answer-engine inventory. It does not change campaign routing or backlink evidence; it only renders canonical repository state.</p></section>
</main><footer><p>Authority Network agency operations · generated from canonical repository data.</p></footer>
<script>
const input=document.getElementById('filter'); input.addEventListener('input',()=>{{const q=input.value.trim().toLowerCase();document.querySelectorAll('.target').forEach(el=>{{el.style.display=!q||el.dataset.search.includes(q)?'block':'none'}})}});function setOpen(v){{document.querySelectorAll('.target').forEach(el=>{{if(el.style.display!=='none')el.open=v}})}}
</script></body></html>'''


def main() -> None:
    model = build_model()
    write_json(DATA_OUT, model)
    PAGE_OUT.parent.mkdir(parents=True, exist_ok=True)
    PAGE_OUT.write_text(render_html(model), encoding="utf-8")
    receipt = {
        "schema": "authority-agency-dashboard-build-v1",
        "status": "PASS",
        "as_of": model["as_of"],
        **model["summary"],
        "page": PAGE_OUT.relative_to(ROOT).as_posix(),
        "data": DATA_OUT.relative_to(ROOT).as_posix(),
    }
    write_json(REPORT_OUT, receipt)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
