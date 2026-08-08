#!/usr/bin/env python3
"""Deterministically backfill missed Authority V4 scheduled publication days.

This is an operator recovery tool. It preserves the existing daily volume contract,
uses the normal generator and its repair/revalidation loop, and refuses to call a
missed day complete unless the requested number of pages is admitted with zero
remaining hard failures.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "autopilot-state.json"
REPORT = ROOT / "reports" / "v4-autopilot-report.json"


def read(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def daterange(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--release-date", required=True)
    ap.add_argument("--expected-per-day", type=int, default=9)
    ap.add_argument("--self-heal-attempts", type=int, default=96)
    args = ap.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    release = date.fromisoformat(args.release_date)
    if end < start:
        raise SystemExit("end must be on or after start")
    if args.expected_per_day < 1:
        raise SystemExit("expected-per-day must be positive")

    days = list(daterange(start, end))
    expected_total = len(days) * args.expected_per_day
    results = []

    for day in days:
        day_s = day.isoformat()
        state = read(STATE, {})
        prior = [r for r in state.get("history", []) if r.get("date") == day_s]
        if prior:
            best = prior[-1]
            if best.get("published") == args.expected_per_day and not best.get("hard_fails"):
                results.append({"date": day_s, "status": "ALREADY_COMPLETE", "published": best.get("published"), "self_heal_recoveries": best.get("self_heal_recoveries", 0)})
                continue
            raise SystemExit(f"Existing incomplete history for {day_s}; refusing to layer a second run over ambiguous state")

        env = {
            **os.environ,
            "BUILD_DATE": day_s,
            "PUBLIC_RELEASE_DATE": release.isoformat(),
            "DAILY_PAGE_LIMIT": str(args.expected_per_day - 6 if args.expected_per_day >= 7 else args.expected_per_day),
            "ABSOLUTE_MAX_PAGES_PER_DAY": str(args.expected_per_day),
            "MIN_BASE_PUBLISH_SCORE": os.getenv("MIN_BASE_PUBLISH_SCORE", "60"),
            "ENABLE_GEMINI_REWRITE": "false",
            "SELF_HEAL_MAX_ATTEMPTS": str(args.self_heal_attempts),
        }
        proc = subprocess.run([sys.executable, "scripts/authority_v4_autopilot.py"], cwd=ROOT, env=env, text=True, capture_output=True)
        if proc.returncode != 0:
            raise SystemExit(f"Backfill generator failed for {day_s}:\n{proc.stdout[-3000:]}\n{proc.stderr[-3000:]}")
        receipt = read(REPORT, {}).get("run", {})
        if receipt.get("date") != day_s:
            raise SystemExit(f"Backfill receipt date mismatch for {day_s}: {receipt.get('date')}")
        if receipt.get("target_volume") != args.expected_per_day or receipt.get("published") != args.expected_per_day or receipt.get("hard_fails"):
            raise SystemExit(
                f"Backfill day {day_s} did not fully self-heal: target={receipt.get('target_volume')} "
                f"published={receipt.get('published')} hard_fails={receipt.get('hard_fails')} blocked={receipt.get('blocked_slots')}"
            )
        results.append({
            "date": day_s,
            "status": "COMPLETE",
            "published": receipt.get("published"),
            "self_heal_recoveries": receipt.get("self_heal_recoveries", 0),
            "self_heal_attempts": receipt.get("self_heal_attempts", 0),
        })

    # Refresh the owner /agency view from the final canonical backlink ledger.
    env = {**os.environ, "PUBLIC_RELEASE_DATE": release.isoformat()}
    agency = subprocess.run([sys.executable, "scripts/build_agency_dashboard.py"], cwd=ROOT, env=env, text=True, capture_output=True)
    if agency.returncode != 0:
        raise SystemExit(f"Agency dashboard rebuild failed:\n{agency.stdout}\n{agency.stderr}")

    state = read(STATE, {})
    history = [r for r in state.get("history", []) if start.isoformat() <= r.get("date", "") <= end.isoformat()]
    total = sum(int(r.get("published", 0)) for r in history)
    unresolved = [r for r in history if r.get("published") != args.expected_per_day or r.get("hard_fails")]
    summary = {
        "schema": "authority-v4-backfill-receipt-v1",
        "status": "PASS" if total == expected_total and not unresolved and len({r.get('date') for r in history}) == len(days) else "FAIL",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "release_date": release.isoformat(),
        "scheduled_days": len(days),
        "expected_per_day": args.expected_per_day,
        "expected_total": expected_total,
        "published_total": total,
        "self_healed_slots": sum(int(r.get("self_heal_recoveries", 0)) for r in history),
        "self_heal_attempts": sum(int(r.get("self_heal_attempts", 0)) for r in history),
        "unresolved_days": unresolved,
        "days": results,
    }
    out = ROOT / "reports" / f"backfill-authority-v4-{start.isoformat()}_{end.isoformat()}.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if summary["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
