#!/usr/bin/env python3
"""Post-publish distribution, live backlink verification, and observation feedback.

Truth boundary: provider submission and URL inspection are observations only. They do
not prove indexing, ranking, independent backlinks, LLM surfacing, or citations.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from lib import site_urls  # noqa: E402

DATA = ROOT / "data"
REPORTS = ROOT / "reports"
USER_AGENT = "AuthorityNetworkDistribution/1.0 (+https://founderoperatorlibrary.com/)"


def read_json(path: str | Path, default: Any) -> Any:
    p = ROOT / path if not isinstance(path, Path) or not path.is_absolute() else path
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def write_json(path: str | Path, value: Any) -> None:
    p = ROOT / path if not isinstance(path, Path) or not path.is_absolute() else path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def receipt_id(now: str) -> str:
    run = os.getenv("GITHUB_RUN_ID", "local")
    return re.sub(r"[^0-9A-Za-z_.-]+", "-", f"{now}-{run}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# IndexNow accepts 10,000 URLs per request, but it throttles a caller that posts
# three full sitemaps in a row. Batches of 200 with a pause between them cleared
# every publication where one request per publication did not.
INDEXNOW_BATCH = 200
INDEXNOW_MAX_URLS = 10000
INDEXNOW_PACING_SECONDS = 2
# 403 from IndexNow is documented as an invalid key, but it is also what the
# endpoint returns when it is throttling. A key that is genuinely wrong fails
# every attempt, so retrying costs nothing and tells the two apart.
RETRYABLE_STATUSES = {403, 429}


def request_json(url: str, method: str = "GET", headers: dict[str, str] | None = None,
                 payload: Any = None, timeout: int = 30, attempts: int = 3) -> dict[str, Any]:
    headers = {"User-Agent": USER_AGENT, **(headers or {})}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    last_error = ""
    last_status: int | None = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, data=body, method=method, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                parsed = json.loads(raw) if raw.strip() else {}
                return {"ok": 200 <= response.status < 300, "http_status": response.status, "body": parsed}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                parsed = {"raw": raw[:2000]}
            if exc.code < 500 and exc.code not in RETRYABLE_STATUSES:
                return {"ok": False, "http_status": exc.code, "body": parsed}
            last_status = exc.code
            last_error = f"HTTP {exc.code}: {raw[:500]}"
        except Exception as exc:  # noqa: BLE001 - receipt must retain provider error
            last_error = str(exc)
        if attempt + 1 < attempts:
            time.sleep(min(2 ** attempt, 4))
    return {"ok": False, "http_status": last_status, "body": {}, "error": last_error}


def request_text(url: str, timeout: int = 30, attempts: int = 3) -> dict[str, Any]:
    last_error = ""
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return {
                    "ok": 200 <= response.status < 400,
                    "http_status": response.status,
                    "final_url": response.geturl(),
                    "text": response.read().decode("utf-8", errors="replace"),
                    "content_type": response.headers.get("content-type", ""),
                }
        except urllib.error.HTTPError as exc:
            if exc.code < 500 and exc.code != 429:
                return {"ok": False, "http_status": exc.code, "final_url": url, "text": "", "error": f"HTTP {exc.code}"}
            last_error = f"HTTP {exc.code}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        if attempt + 1 < attempts:
            time.sleep(min(2 ** attempt, 4))
    return {"ok": False, "http_status": None, "final_url": url, "text": "", "error": last_error}


def base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def google_access_token() -> tuple[str | None, str]:
    direct = os.getenv("GSC_ACCESS_TOKEN", "").strip()
    if direct:
        return direct, "direct_access_token"
    raw = os.getenv("GSC_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        return None, "not_configured"
    try:
        account = json.loads(raw)
        now = int(time.time())
        oauth_base = os.getenv("GOOGLE_OAUTH_BASE", "https://oauth2.googleapis.com").rstrip("/")
        header = base64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
        claims = base64url(json.dumps({
            "iss": account["client_email"],
            "scope": "https://www.googleapis.com/auth/webmasters",
            "aud": f"{oauth_base}/token",
            "iat": now,
            "exp": now + 3600,
        }, separators=(",", ":")).encode())
        signing_input = f"{header}.{claims}".encode()
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as key_file:
            key_file.write(account["private_key"])
            key_path = key_file.name
        try:
            signature = subprocess.run(
                ["openssl", "dgst", "-sha256", "-sign", key_path],
                input=signing_input,
                capture_output=True,
                check=True,
            ).stdout
        finally:
            Path(key_path).unlink(missing_ok=True)
        assertion = f"{header}.{claims}.{base64url(signature)}"
        token_url = f"{oauth_base}/token"
        encoded = urllib.parse.urlencode({
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }).encode()
        req = urllib.request.Request(token_url, data=encoded, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as response:
            token = json.loads(response.read().decode("utf-8"))["access_token"]
        return token, "service_account"
    except Exception as exc:  # noqa: BLE001
        return None, f"token_error:{exc}"


def public_url(publication: dict[str, Any], source_path: str, base_overrides: dict[str, str]) -> str:
    """The URL this repository path is served at.

    Built through lib.site_urls so it matches the sitemap and the canonical tag.
    It used to append the repository filename, which named the .html form: live
    verification followed a 308 on every request, and a GSC URL inspection would
    have been asking about a URL that redirects rather than the one indexed.
    """
    base = base_overrides.get(publication["id"], f"https://{publication['working_domain']}").rstrip("/")
    folder = publication["folder"].rstrip("/") + "/"
    rel = source_path[len(folder):] if source_path.startswith(folder) else Path(source_path).name
    return f"{base}/{site_urls.url_path(rel.lstrip('/'))}"


def parse_sitemap_urls(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [html.unescape(x.strip()) for x in re.findall(r"<loc>(.*?)</loc>", text, flags=re.I | re.S)]


def indexed_from_inspection(result: dict[str, Any]) -> bool:
    verdict = str(result.get("verdict", "")).upper()
    coverage = str(result.get("coverage_state", "")).lower()
    indexing = str(result.get("indexing_state", "")).upper()
    return verdict == "PASS" and ("indexed" in coverage or indexing in {"INDEXING_ALLOWED", "INDEXING_STATE_UNSPECIFIED"} and "not indexed" not in coverage)


def main() -> None:
    now = iso_now()
    rid = receipt_id(now)
    publications = read_json("data/publications.json", [])
    links = read_json("data/link-registry.json", [])
    campaigns = read_json("data/portfolio-backlink-campaigns.json", {"campaigns": []}).get("campaigns", [])
    overrides = json.loads(os.getenv("AUTHORITY_PUBLICATION_BASE_URLS_JSON", "{}") or "{}")
    gsc_sites = json.loads(os.getenv("GSC_SITE_URLS_JSON", "{}") or "{}")
    indexnow_endpoint = os.getenv("INDEXNOW_ENDPOINT", "https://api.indexnow.org/indexnow")
    gsc_webmasters_base = os.getenv("GSC_WEBMASTERS_BASE", "https://www.googleapis.com/webmasters/v3").rstrip("/")
    gsc_inspection_endpoint = os.getenv("GSC_INSPECTION_ENDPOINT", "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect")
    live_verify = os.getenv("LIVE_BACKLINK_VERIFY", "true").lower() not in {"0", "false", "no"}
    deployment_settle_seconds = max(0, min(int(os.getenv("DEPLOYMENT_SETTLE_SECONDS", "0")), 900))
    inspection_limit = max(0, min(int(os.getenv("GSC_INSPECTION_LIMIT", "20")), 200))
    # IndexNow keys are public verification tokens, not credentials, and this
    # repository commits one at data/indexnow_key.txt and serves it from all
    # three publication roots. Reading only the environment variable - which is
    # not set anywhere - made every receipt say NOT_CONFIGURED with
    # submitted_urls 0, so the lane had never once run.
    # scripts/prepare_indexnow_keys.py already has this fallback; this is the
    # same resolution order, so the file it writes is the key that gets used.
    key = os.getenv("INDEXNOW_KEY", "").strip()
    key_source = "env"
    if not key:
        committed = ROOT / "data/indexnow_key.txt"
        if committed.is_file():
            key = committed.read_text(encoding="utf-8").strip()
            key_source = "data/indexnow_key.txt"
    key_location_template = os.getenv("INDEXNOW_KEY_LOCATION_TEMPLATE", "https://{domain}/{key}.txt")
    token, token_source = google_access_token()

    publication_by_id = {p["id"]: p for p in publications}
    rows_by_pub: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in links:
        if row.get("status") != "published" or not row.get("source_path"):
            continue
        pub_id = row.get("source_publication") or row.get("publication")
        if pub_id not in publication_by_id:
            pub_id = next((p["id"] for p in publications if row["source_path"].startswith(p["folder"].rstrip("/") + "/")), None)
        if pub_id in publication_by_id:
            rows_by_pub[pub_id].append(row)

    if live_verify and deployment_settle_seconds:
        time.sleep(deployment_settle_seconds)

    publication_receipts: list[dict[str, Any]] = []
    observation_rows: list[dict[str, Any]] = []
    provider_failure = False

    for publication in publications:
        pub_id = publication["id"]
        domain = publication["working_domain"]
        sitemap_path = ROOT / publication["folder"] / "sitemap.xml"
        sitemap_urls = parse_sitemap_urls(sitemap_path) if sitemap_path.exists() else []
        sitemap_url = f"{overrides.get(pub_id, f'https://{domain}').rstrip('/')}/sitemap.xml"
        pub_rows = rows_by_pub.get(pub_id, [])
        source_urls = [(row, public_url(publication, row["source_path"], overrides)) for row in pub_rows]
        priority = [url for row, url in source_urls if not (row.get("evidence") or {}).get("live_verified")]
        priority = list(dict.fromkeys(priority))[:inspection_limit]

        # IndexNow submits the full sitemap set for the property, bounded by provider maximum.
        if key:
            key_location = key_location_template.format(domain=domain, key=key)
            public_key_file = ROOT / publication["folder"] / f"{key}.txt"
            if not public_key_file.exists() or public_key_file.read_text(encoding="utf-8").strip() != key:
                indexnow = {"status": "FAILED", "attempted": False, "submitted_urls": 0, "key_location": key_location, "error": f"Missing or mismatched public key file: {public_key_file.relative_to(ROOT)}"}
            else:
                # Submitted in batches, paced. One 402-URL request for the third
                # publication came back 403 while the same payload succeeded on
                # its own moments later: the endpoint throttles a caller that
                # posts three whole sitemaps back to back, and a throttle
                # answered 403 is indistinguishable from a bad key unless the
                # batches are recorded separately. Each batch carries its own
                # HTTP status in the receipt, and a batch that fails is retried
                # by request_json's 403/429/5xx backoff before it is believed.
                batches = []
                for start in range(0, len(sitemap_urls[:INDEXNOW_MAX_URLS]), INDEXNOW_BATCH):
                    chunk = sitemap_urls[start:start + INDEXNOW_BATCH]
                    if batches:
                        time.sleep(INDEXNOW_PACING_SECONDS)
                    result = request_json(indexnow_endpoint, method="POST", payload={"host": domain, "key": key, "keyLocation": key_location, "urlList": chunk})
                    batches.append({"urls": len(chunk), "http_status": result.get("http_status"), "ok": bool(result.get("ok")), "error": result.get("error")})
                submitted = sum(b["urls"] for b in batches if b["ok"])
                indexnow = {"status": "SUCCESS" if all(b["ok"] for b in batches) else ("PARTIAL" if submitted else "FAILED"), "attempted": True, "submitted_urls": submitted, "offered_urls": len(sitemap_urls[:INDEXNOW_MAX_URLS]), "batches": batches, "key_source": key_source, "key_location": key_location, "key_file": str(public_key_file.relative_to(ROOT))}
        else:
            indexnow = {"status": "NOT_CONFIGURED", "attempted": False, "submitted_urls": 0, "reason": "no INDEXNOW_KEY in the environment and no data/indexnow_key.txt"}

        site_url = gsc_sites.get(pub_id, f"sc-domain:{domain}")
        if token:
            endpoint = f"{gsc_webmasters_base}/sites/{urllib.parse.quote(site_url, safe='')}/sitemaps/{urllib.parse.quote(sitemap_url, safe='')}"
            result = request_json(endpoint, method="PUT", headers={"Authorization": f"Bearer {token}"})
            gsc_sitemap = {"status": "SUCCESS" if result.get("ok") else "FAILED", "attempted": True, "http_status": result.get("http_status"), "site_url": site_url, "sitemap_url": sitemap_url}
            if result.get("error"): gsc_sitemap["error"] = result["error"]
        else:
            gsc_sitemap = {"status": "NOT_CONFIGURED", "attempted": False, "site_url": site_url, "sitemap_url": sitemap_url, "token_state": token_source}

        inspections: list[dict[str, Any]] = []
        if token:
            for url in priority:
                result = request_json(gsc_inspection_endpoint, method="POST", headers={"Authorization": f"Bearer {token}"}, payload={"inspectionUrl": url, "siteUrl": site_url, "languageCode": "en-US"})
                state = (result.get("body") or {}).get("inspectionResult", {}).get("indexStatusResult", {})
                inspections.append({
                    "url": url,
                    "status": "SUCCESS" if result.get("ok") else "FAILED",
                    "http_status": result.get("http_status"),
                    "verdict": state.get("verdict", "UNKNOWN"),
                    "coverage_state": state.get("coverageState", "UNKNOWN"),
                    "indexing_state": state.get("indexingState", "UNKNOWN"),
                    "last_crawl_time": state.get("lastCrawlTime"),
                    "google_canonical": state.get("googleCanonical"),
                    "user_canonical": state.get("userCanonical"),
                })
        inspection_status = "NOT_CONFIGURED" if not token else ("SUCCESS" if not any(x["status"] == "FAILED" for x in inspections) else ("FAILED" if inspections and all(x["status"] == "FAILED" for x in inspections) else "PARTIAL"))

        live_results: list[dict[str, Any]] = []
        source_map = {url: row for row, url in source_urls}
        if live_verify:
            for row, url in source_urls:
                response = request_text(url)
                text = html.unescape(response.get("text", ""))
                link_present = bool(row.get("target_url")) and row["target_url"] in text
                anchor_present = bool(row.get("anchor")) and row["anchor"] in text
                noindex = bool(re.search(r'<meta[^>]+name=["\']robots["\'][^>]+content=["\'][^"\']*noindex', text, re.I))
                verified = bool(response.get("ok") and link_present and anchor_present and not noindex)
                live_results.append({"source_url": url, "target_url": row.get("target_url"), "anchor": row.get("anchor"), "http_status": response.get("http_status"), "final_url": response.get("final_url"), "source_live": bool(response.get("ok")), "target_link_present": link_present, "anchor_present": anchor_present, "indexable": not noindex, "live_verified": verified, "error": response.get("error")})
                evidence = row.setdefault("evidence", {})
                evidence["repository_rendered"] = True
                evidence["deployed"] = bool(response.get("ok"))
                evidence["live_verified"] = verified
                evidence["discoverable"] = verified and url in sitemap_urls
                if verified:
                    row["lifecycle_stage"] = "live_verified"
        else:
            live_results = [{"status": "NOT_CONFIGURED", "reason": "LIVE_BACKLINK_VERIFY=false"}]

        inspection_by_url = {x["url"]: x for x in inspections}
        for url, row in source_map.items():
            inspection = inspection_by_url.get(url)
            if inspection and inspection["status"] == "SUCCESS":
                row.setdefault("evidence", {})["gsc_inspected"] = True
                row["evidence"]["indexed"] = indexed_from_inspection(inspection)
                if row["evidence"]["indexed"]:
                    row["lifecycle_stage"] = "source_indexed"
                elif row["evidence"].get("live_verified"):
                    row["lifecycle_stage"] = "source_discovered"
            row.setdefault("evidence", {})["ai_cited"] = bool(row.get("evidence", {}).get("ai_cited", False))

        # Pace the next publication's submissions too, not just the batches
        # within one: three sitemaps posted back to back is what drew the
        # throttle in the first place.
        if indexnow.get("attempted"):
            time.sleep(INDEXNOW_PACING_SECONDS)
        statuses = [indexnow["status"], gsc_sitemap["status"], inspection_status]
        if "FAILED" in statuses:
            provider_failure = True
        pub_receipt = {
            "publication_id": pub_id,
            "domain": domain,
            "successful_publish_gate": "workflow_run_success_or_manual_dispatch",
            "sitemap_refresh": {"status": "SUCCESS" if sitemap_path.exists() else "FAILED", "path": str(sitemap_path.relative_to(ROOT)), "sitemap_url": sitemap_url, "sha256": sha256(sitemap_path) if sitemap_path.exists() else None, "url_count": len(sitemap_urls)},
            "indexnow": indexnow,
            "gsc_sitemap_submission": gsc_sitemap,
            "priority_url_inspection": {"status": inspection_status, "requested_urls": len(priority), "inspected_urls": len(inspections), "results": inspections},
            "live_backlink_verification": {"status": "SUCCESS" if live_verify and not any(not x.get("live_verified") for x in live_results) else ("PARTIAL" if live_verify and any(x.get("live_verified") for x in live_results) else "NOT_CONFIGURED"), "checked": len(live_results) if live_verify else 0, "verified": sum(bool(x.get("live_verified")) for x in live_results), "results": live_results},
        }
        publication_receipts.append(pub_receipt)
        observation_rows.append({
            "publication_id": pub_id,
            "domain": domain,
            "rendered_backlinks": len(pub_rows),
            "live_verified_backlinks": sum(bool((r.get("evidence") or {}).get("live_verified")) for r in pub_rows),
            "indexed_referring_pages": sum(bool((r.get("evidence") or {}).get("indexed")) for r in pub_rows),
            "indexnow_status": indexnow["status"],
            "gsc_sitemap_status": gsc_sitemap["status"],
            "gsc_inspection_status": inspection_status,
        })

    write_json("data/link-registry.json", links)
    campaign_counts = []
    for campaign in campaigns:
        rows = [r for r in links if r.get("campaign_id") == campaign["id"] and r.get("status") == "published"]
        campaign_counts.append({
            "campaign_id": campaign["id"],
            "brand_id": campaign["brand_id"],
            "rendered": sum(bool((r.get("evidence") or {}).get("repository_rendered")) for r in rows),
            "deployed": sum(bool((r.get("evidence") or {}).get("deployed")) for r in rows),
            "live_verified": sum(bool((r.get("evidence") or {}).get("live_verified")) for r in rows),
            "indexed": sum(bool((r.get("evidence") or {}).get("indexed")) for r in rows),
            "verified_external_citations": sum(bool((r.get("evidence") or {}).get("ai_cited")) for r in rows),
        })

    receipt = {
        "schema": "authority-network-post-publish-distribution-v1",
        "receipt_id": rid,
        "attempted_at": now,
        "chain": ["successful_publish", "sitemap_refresh", "indexnow", "gsc_sitemap_submission", "priority_url_inspection_where_configured", "durable_distribution_receipt", "live_backlink_verification", "observation_feedback"],
        "trigger_contract": "AUTOMATIC_ONLY_AFTER_AUTHORITY_AUTOPILOT_WORKFLOW_SUCCESS; manual dispatch and scheduled retry are also allowed.",
        "publications": publication_receipts,
        "durable_receipt": {"latest": "data/distribution/provider-receipt.json", "history": f"data/distribution/receipts/{rid}.json"},
        "provider_success_claimed": any(x["indexnow"]["status"] == "SUCCESS" or x["gsc_sitemap_submission"]["status"] == "SUCCESS" for x in publication_receipts),
        "verified_external_citations_delta": 0,
        "truth_boundary": "Rendered, deployed, live-verified, discovered, indexed, independently referenced, LLM-surfaced, and cited are separate evidence states. Provider submission is not proof of indexing or citation.",
    }
    feedback = {
        "schema": "authority-network-observation-feedback-v1",
        "observed_at": now,
        "source_receipt_id": rid,
        "publication_health": observation_rows,
        "campaign_health": campaign_counts,
        "portfolio_totals": {
            "rendered_backlinks": sum(x["rendered_backlinks"] for x in observation_rows),
            "live_verified_backlinks": sum(x["live_verified_backlinks"] for x in observation_rows),
            "indexed_referring_pages": sum(x["indexed_referring_pages"] for x in observation_rows),
            "verified_external_citations": sum(x["verified_external_citations"] for x in campaign_counts),
        },
        "recommended_action": "REVIEW_PROVIDER_FAILURES" if provider_failure else ("CONTINUE_YIELD_GOVERNOR" if receipt["provider_success_claimed"] else "CONFIGURE_PROVIDER_CREDENTIALS_AND_DEPLOY_PUBLICATION_PROPERTIES"),
        "truth_boundary": receipt["truth_boundary"],
    }
    write_json("data/distribution/provider-receipt.json", receipt)
    write_json(f"data/distribution/receipts/{rid}.json", receipt)
    write_json("data/distribution/observation-feedback.json", feedback)
    write_json("reports/post-publish-distribution-latest.json", receipt)
    print(json.dumps(receipt, indent=2))
    if provider_failure and os.getenv("FAIL_ON_PROVIDER_ERROR", "false").lower() in {"1", "true", "yes"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
