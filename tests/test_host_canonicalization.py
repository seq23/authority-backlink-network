#!/usr/bin/env python3
"""Exercise the generated Pages middleware the way Cloudflare will call it.

The generator could write a plausible-looking file that redirects the canonical
host to itself (an infinite loop), drops the path (every deep link lands on the
homepage) or answers 302. None of those are visible by reading the repository,
so this runs the real file in node with a fake Pages context and asserts the
answers that matter: the canonical host is passed through untouched, and every
other host answers 301 to the same path and query on the canonical host.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_host_canonicalization import plan  # noqa: E402

# (request URL, expected Location) with {d} the canonical domain. "next" means
# the request must be handed to the static asset handler, not redirected.
CASES = [
    ("https://{d}/about?x=1", "next"),
    ("https://www.{d}/about?x=1", "https://{d}/about?x=1"),
    ("https://authority-preview.pages.dev/daily/a", "https://{d}/daily/a"),
    ("http://www.{d}/", "https://{d}/"),
]

HARNESS = r"""
const [file, cases] = process.argv.slice(2);
const mod = await import(file);
const out = [];
for (const url of JSON.parse(cases)) {
  const res = await mod.onRequest({ request: new Request(url), next: async () => "NEXT" });
  out.push(res === "NEXT" ? [url, "next", 0] : [url, res.headers.get("location"), res.status]);
}
console.log(JSON.stringify(out));
"""


def publications() -> dict[str, str]:
    """{publication folder: canonical domain}."""
    pubs = json.loads((ROOT / "data/publications.json").read_text(encoding="utf-8"))
    return {p["folder"]: p["working_domain"].strip().lower() for p in pubs}


def main() -> int:
    domains = publications()
    failures: list[str] = []
    checked = 0
    harness = ROOT / "reports" / ".host-canonicalization-harness.mjs"
    harness.parent.mkdir(parents=True, exist_ok=True)
    harness.write_text(HARNESS, encoding="utf-8")
    try:
        for rel in sorted(plan()):
            folder = next((f for f in domains if rel.startswith(f + "/")), None)
            if folder is None:
                failures.append(f"{rel}: no publication in data/publications.json owns this path")
                continue
            domain = domains[folder]
            urls = [url.format(d=domain) for url, _ in CASES]
            proc = subprocess.run(["node", str(harness), (ROOT / rel).as_uri(), json.dumps(urls)],
                                  capture_output=True, text=True, cwd=ROOT)
            if proc.returncode != 0:
                failures.append(f"{rel}: middleware did not run: {proc.stderr.strip()[-300:]}")
                continue
            checked += 1
            for (url, want_raw), (_, location, status) in zip(CASES, json.loads(proc.stdout)):
                want = want_raw.format(d=domain)
                if want == "next":
                    if location != "next":
                        failures.append(f"{rel}: the canonical host answered {status} to "
                                        f"{url.format(d=domain)} -> {location}; that is a redirect loop")
                    continue
                if status != 301:
                    failures.append(f"{rel}: {url.format(d=domain)} answered {status}, want 301")
                if location != want:
                    failures.append(f"{rel}: {url.format(d=domain)} redirected to {location}, want {want}")
    finally:
        harness.unlink(missing_ok=True)
    # Rule 0: no middleware exercised means this proved nothing.
    if not checked:
        failures.append("inert: zero middlewares exercised")
    print(json.dumps({"status": "FAIL" if failures else "PASS",
                      "middlewares_exercised": checked,
                      "cases_per_middleware": len(CASES),
                      "hard_failures": len(failures),
                      "failures": failures[:20]}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
