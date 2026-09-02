#!/usr/bin/env python3
"""The regulated-change changelog: watch USCIS form and fee pages, publish what moved.

The gap this fills
------------------
USCIS publishes what is true *now*. It does not publish a readable, dated record
of what changed and when. That record is what a journalist cites when they need
to write "this changed in March", and what somebody halfway through a filing
needs and cannot find anywhere. Building it is ordinary primary-source
journalism: fetch the page every week, keep the previous copy, and describe the
difference.

docs/EXTERNAL-AUTHORITY-PLAN.md ranks this fourth and warns about it twice: it is
YMYL material, and a stale entry is a harmful entry. Both warnings are why this
file is shaped the way it is.

The one guard everything else hangs off
---------------------------------------
A language model writes each entry. It is given exactly one job -- describe the
difference between two versions of a page -- and it is never asked to reason
about immigration law. Even so, the failure mode of a model is to produce a
fluent sentence that is not in the source, and on a page about filing fees a
fluent wrong sentence is a harmful one.

So **every entry must quote text that is actually present in the fetched page,
and every quote must appear in the stored diff.** A model output whose quotes do
not verify is discarded; it is not published, not repaired, and not published in
a weakened form. `scripts/validators/validate_uscis_changelog.py` re-checks every
published entry against the stored diff independently, without a network call,
so a hand-edited entry fails the same way a hallucinated one does.

What a run does
---------------
    fetch each tracked page
      unreachable        -> NAMED STOP. The snapshot is not touched, the source
                            is marked stale, and it is never recorded as "no
                            change". Two consecutive misses exit non-zero so the
                            workflow goes red rather than going quietly blind.
      no material change -> say so, in the receipt and on the page, and stop.
      changed            -> diff it, ask the model to describe the diff, verify
                            every quote against the fetched text, publish the
                            entry, and only then advance the snapshot.

That last ordering matters. The snapshot advances only once an entry exists for
the change. If OpenRouter is down, the old snapshot stays put and next week's run
sees the same difference again -- an outage costs a week of latency, never a
lost change, and never takes the lane down.

    python3 scripts/uscis_changelog.py            # a real run
    python3 scripts/uscis_changelog.py --offline  # diff/verify only, no network

Key: OPENROUTER_API_KEY, or .secrets/openrouter_key.txt locally. Never printed.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import html as html_mod
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANE = ROOT / "data/uscis-changelog"
TRACKED = LANE / "tracked-sources.json"
ENTRIES = LANE / "entries.json"
STATE = LANE / "state.json"
SNAPSHOTS = LANE / "snapshots"
RECEIPT = ROOT / "reports/uscis-changelog-latest.json"
KEY_FILE = Path.home() / "GitHub/how-we-know/.secrets/openrouter_key.txt"

API = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"

# Two consecutive misses is the line. One miss is a bad afternoon at an agency
# whose site is genuinely flaky; two in a row means the URL moved or the fetch
# broke, and a changelog that has not seen its source in a fortnight is exactly
# the thing that goes stale while its own green receipt says it is healthy.
MAX_CONSECUTIVE_FAILURES = 2

# A diff smaller than this is boilerplate churn, not a change worth an entry.
# Measured against the real pages: USCIS rotates alert banners and reorders a
# couple of list items without anything actually changing.
MIN_CHANGED_LINES = 1
MIN_CHANGED_CHARS = 40

MIN_QUOTE_CHARS = 25

# Language that would cross the publication's advice boundary. This lane reports
# what a page says; it never tells a reader what to do about it. Checked on the
# model's prose, and again by the validator on what was published.
ADVICE_PATTERNS = [
    re.compile(r"\byou (?:should|must|need to|will need to|have to|can now|may now)\b", re.I),
    re.compile(r"\bwe recommend\b", re.I),
    re.compile(r"\bmake sure (?:you|to)\b", re.I),
    re.compile(r"\b(?:be sure|remember) to\b", re.I),
    re.compile(r"\bapplicants? should\b", re.I),
    re.compile(r"\bif you (?:are|have|filed|plan)\b", re.I),
    re.compile(r"\byour (?:application|petition|case|filing)\b", re.I),
]


class NamedStop(Exception):
    """An expected, nameable reason a run produced nothing. Never a crash."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code, self.message = code, message


# --------------------------------------------------------------------- text

SCRIPT_RE = re.compile(r"<(script|style|noscript|svg)\b[^>]*>.*?</\1>", re.S | re.I)
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
NAV_RE = re.compile(r"<(nav|header|footer|form)\b[^>]*>.*?</\1>", re.S | re.I)
MAIN_RE = re.compile(r"<main\b[^>]*>(.*?)</main>", re.S | re.I)
BLOCK_RE = re.compile(r"</(p|div|li|tr|h[1-6]|section|table|ul|ol|dd|dt)>", re.I)
TAG_RE = re.compile(r"<[^>]+>")

# Lines that differ between two fetches of an unchanged page. Every one of these
# was observed on the real USCIS pages; each is dropped so that a run does not
# generate an entry about a rotating banner.
VOLATILE_RE = [
    re.compile(r"^last (?:reviewed|updated)\b", re.I),
    re.compile(r"^\s*\d{1,2}/\d{1,2}/\d{2,4}\s*$"),
    re.compile(r"^(?:skip to|return to top|back to top)\b", re.I),
    re.compile(r"^(?:an official website|official websites use|secure \.gov)", re.I),
    re.compile(r"^\s*(?:share|print|email this page)\s*$", re.I),
    re.compile(r"csrf|session|nonce|__cf|cache-?bust", re.I),
]


def visible_text(raw: str) -> list[str]:
    """Reduce a page to the stable lines a reader would actually see.

    Deliberately crude and dependency-free. The point is not a faithful render;
    it is a normalisation that produces the *same* lines for two fetches of an
    unchanged page, so that every line in a diff is a real difference.
    """
    body = raw
    main = MAIN_RE.search(body)
    if main:
        body = main.group(1)
    body = SCRIPT_RE.sub(" ", body)
    body = COMMENT_RE.sub(" ", body)
    body = NAV_RE.sub(" ", body)
    body = BLOCK_RE.sub("\n", body)
    body = re.sub(r"<br\s*/?>", "\n", body, flags=re.I)
    body = TAG_RE.sub(" ", body)
    body = html_mod.unescape(body)

    lines: list[str] = []
    for line in body.split("\n"):
        line = re.sub(r"[   ]", " ", line)
        line = re.sub(r"\s+", " ", line).strip()
        if len(line) < 3:
            continue
        if any(p.search(line) for p in VOLATILE_RE):
            continue
        lines.append(line)
    return lines


def sha(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


# -------------------------------------------------------------------- fetch

def fetch(url: str, cfg: dict) -> str:
    last: Exception | None = None
    for attempt in range(1, int(cfg.get("attempts", 3)) + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": cfg["user_agent"],
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=int(cfg.get("timeout_seconds", 45))) as r:
                if r.status != 200:
                    raise urllib.error.HTTPError(url, r.status, "non-200", r.headers, None)
                return r.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 - every transport failure is one outcome
            last = exc
            if attempt < int(cfg.get("attempts", 3)):
                time.sleep(int(cfg.get("backoff_seconds", 5)) * attempt)
    raise NamedStop("SOURCE_UNREACHABLE", f"{url}: {last}")


# --------------------------------------------------------------------- diff

def diff_lines(before: list[str], after: list[str]) -> dict:
    """The stored evidence. Everything downstream verifies against this object."""
    sm = difflib.SequenceMatcher(None, before, after, autojunk=False)
    added: list[str] = []
    removed: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            removed.extend(before[i1:i2])
        if tag in ("replace", "insert"):
            added.extend(after[j1:j2])
    return {
        "added": added,
        "removed": removed,
        "added_chars": sum(len(x) for x in added),
        "removed_chars": sum(len(x) for x in removed),
    }


def material(d: dict) -> bool:
    changed = len(d["added"]) + len(d["removed"])
    chars = d["added_chars"] + d["removed_chars"]
    return changed >= MIN_CHANGED_LINES and chars >= MIN_CHANGED_CHARS


# ---------------------------------------------------------------------- key

def api_key() -> str | None:
    env = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if env:
        return env
    if KEY_FILE.exists():
        k = KEY_FILE.read_text(encoding="utf-8").strip()
        if k:
            return k
    return None


def call_openrouter(messages: list[dict], model: str, key: str, timeout: int = 180) -> dict:
    body = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": 2000,
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
        "usage": {"include": True},
    }).encode()
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://professionalresourcelibrary.com/",
        "X-Title": "Professional Resource Library - USCIS changelog",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


PROMPT = """You are a copy editor comparing two versions of one page on uscis.gov.

Your ONLY job is to describe what changed between the two versions. You are not
reasoning about immigration law, you are not interpreting a rule, and you are not
telling anyone what to do. If you cannot tell what changed from the lines below,
say so; that is a correct answer and a useful one.

SOURCE PAGE: {title} ({url})
WHAT THIS PAGE IS WATCHED FOR: {watching}

LINES REMOVED (present in the previous version, absent now):
{removed}

LINES ADDED (absent from the previous version, present now):
{added}

Reply with a JSON object and nothing else:

{{
  "material": true or false,
  "headline": "under 90 characters, factual, names what moved",
  "summary": "2-4 sentences. What the page said before, what it says now. Past tense for the old state, present tense for the new. No advice, no second person, no 'you'.",
  "quotes": [
    {{"side": "added" or "removed", "text": "a VERBATIM line, copied character for character from the lists above"}}
  ]
}}

Rules that will cause your answer to be discarded if broken:
- Every "text" must be an EXACT, character-for-character copy of one whole line
  from the ADDED or REMOVED list above. Do not trim it, fix its punctuation,
  merge two lines, or paraphrase it. It is checked by string comparison.
- At least one quote. At most four.
- Never use the words "you" or "your". Never advise, recommend, or instruct.
- Never state a fee, date, form edition or deadline that does not appear
  verbatim in the lines above.
- If the difference is only reordering, punctuation, or a rotating banner, set
  "material" to false and return one quote showing it.
"""


FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)


def strip_fence(content: str) -> str:
    """OpenRouter's `response_format: json_object` is a request, not a guarantee.

    Observed 2026-09-01: the same model served through Amazon Bedrock returns a
    correct JSON object wrapped in a ```json fence, and the run then failed as
    MODEL_OUTPUT_UNPARSEABLE with a perfectly good entry inside it. Unwrapping a
    fence changes no content; it is not a repair of the model's answer.
    """
    m = FENCE_RE.match(content)
    return m.group(1) if m else content


def ask_model(source: dict, d: dict, model: str, key: str) -> tuple[dict | None, str]:
    def block(items: list[str]) -> str:
        if not items:
            return "(none)"
        return "\n".join(f"- {x}" for x in items[:120])

    messages = [{"role": "user", "content": PROMPT.format(
        title=source["title"], url=source["url"], watching=source["watching"],
        removed=block(d["removed"]), added=block(d["added"]))}]
    try:
        payload = call_openrouter(messages, model, key)
    except Exception as exc:  # noqa: BLE001 - an API outage must not take the lane down
        return None, f"OPENROUTER_UNAVAILABLE: {type(exc).__name__}"
    try:
        choice = payload["choices"][0]
        if choice.get("finish_reason") == "length":
            return None, "MODEL_OUTPUT_TRUNCATED"
        return json.loads(strip_fence(choice["message"]["content"])), ""
    except Exception as exc:  # noqa: BLE001
        return None, f"MODEL_OUTPUT_UNPARSEABLE: {type(exc).__name__}"


# ------------------------------------------------------------------- verify

def verify(entry: dict, d: dict, after: list[str], before: list[str]) -> list[str]:
    """The load-bearing guard. Returns the reasons this entry may not publish.

    Applied here before anything is written, and applied again -- against the
    stored diff, offline -- by scripts/validators/validate_uscis_changelog.py.
    Two independent applications on purpose: this one stops a hallucination,
    that one stops a hand edit.
    """
    problems: list[str] = []
    quotes = entry.get("quotes") or []
    if not isinstance(quotes, list) or not quotes:
        return ["entry carries no quotes; an entry with no quoted source text may not publish"]
    if len(quotes) > 4:
        problems.append(f"{len(quotes)} quotes; at most 4")

    added, removed = set(d["added"]), set(d["removed"])
    after_set, before_set = set(after), set(before)
    for q in quotes:
        if not isinstance(q, dict):
            problems.append(f"malformed quote: {q!r}")
            continue
        text, side = str(q.get("text", "")).strip(), q.get("side")
        if len(text) < MIN_QUOTE_CHARS:
            problems.append(f"quote is too short to evidence anything: {text!r}")
            continue
        if side == "added":
            if text not in added:
                problems.append(f"quote is not a line in the stored diff's added lines: {text[:90]!r}")
            elif text not in after_set:
                problems.append(f"quote is not present in the fetched page: {text[:90]!r}")
        elif side == "removed":
            if text not in removed:
                problems.append(f"quote is not a line in the stored diff's removed lines: {text[:90]!r}")
            elif text not in before_set:
                problems.append(f"quote is not present in the previous snapshot: {text[:90]!r}")
        else:
            problems.append(f"quote side must be 'added' or 'removed', got {side!r}")

    prose = f"{entry.get('headline', '')} {entry.get('summary', '')}"
    for pattern in ADVICE_PATTERNS:
        m = pattern.search(prose)
        if m:
            problems.append(f"crosses the publication's advice boundary: {m.group(0)!r}")

    if not str(entry.get("headline", "")).strip():
        problems.append("entry has no headline")
    if len(str(entry.get("summary", "")).split()) < 12:
        problems.append("summary is too short to describe a change")
    return problems


# --------------------------------------------------------------------- run

def load(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8", newline="\n")


def run(offline: bool, model: str) -> dict:
    tracked = json.loads(TRACKED.read_text(encoding="utf-8"))
    cfg = tracked["fetch"]
    entries_doc = load(ENTRIES, {"schema_version": 1, "entries": []})
    state = load(STATE, {"sources": {}})
    checked_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    today = date.today().isoformat()

    outcomes: list[dict] = []
    new_entries: list[dict] = []

    for source in tracked["sources"]:
        sid = source["id"]
        snap_path = SNAPSHOTS / f"{sid}.json"
        snap = load(snap_path, None)
        st = state["sources"].setdefault(sid, {
            "last_success": None, "last_attempt": None,
            "consecutive_failures": 0, "snapshot_sha": None})
        st["last_attempt"] = checked_at

        if offline:
            outcomes.append({"source": sid, "url": source["url"],
                             "status": "SKIPPED_OFFLINE",
                             "detail": "--offline: no network call was made, so nothing "
                                       "about this source was observed. This is NOT "
                                       "'no change'."})
            continue

        try:
            raw = fetch(source["url"], cfg)
        except NamedStop as stop:
            st["consecutive_failures"] += 1
            outcomes.append({
                "source": sid, "url": source["url"], "status": "NAMED_STOP_UNREACHABLE",
                "consecutive_failures": st["consecutive_failures"],
                "last_success": st["last_success"],
                "detail": f"{stop.message} -- the snapshot was NOT advanced and this "
                          f"source is NOT being reported as unchanged."})
            continue

        after = visible_text(raw)
        if len(after) < 20:
            st["consecutive_failures"] += 1
            outcomes.append({
                "source": sid, "url": source["url"], "status": "NAMED_STOP_UNREADABLE",
                "consecutive_failures": st["consecutive_failures"],
                "detail": f"fetched {len(raw)} bytes but only {len(after)} readable "
                          f"lines survived normalisation; treating as unreachable "
                          f"rather than as an emptied page."})
            continue

        st["consecutive_failures"] = 0
        st["last_success"] = checked_at

        if snap is None:
            write_json(snap_path, {"source": sid, "url": source["url"],
                                   "captured": checked_at, "sha256": sha(after),
                                   "lines": after})
            st["snapshot_sha"] = sha(after)
            outcomes.append({"source": sid, "url": source["url"],
                             "status": "BASELINE_CAPTURED",
                             "lines": len(after),
                             "detail": "first observation of this page; there is no "
                                       "previous version to diff against, so no entry "
                                       "was written."})
            continue

        before = snap["lines"]
        d = diff_lines(before, after)
        if not material(d):
            st["snapshot_sha"] = sha(after)
            write_json(snap_path, {"source": sid, "url": source["url"],
                                   "captured": checked_at, "sha256": sha(after),
                                   "lines": after})
            outcomes.append({"source": sid, "url": source["url"], "status": "NO_CHANGE",
                             "added_lines": len(d["added"]),
                             "removed_lines": len(d["removed"]),
                             "detail": "the page was fetched and compared; the "
                                       "difference is below the materiality floor."})
            continue

        key = api_key()
        if not key:
            outcomes.append({
                "source": sid, "url": source["url"], "status": "NAMED_STOP_NO_API_KEY",
                "added_lines": len(d["added"]), "removed_lines": len(d["removed"]),
                "detail": "this page changed and the change is being HELD, not lost: "
                          "the snapshot stays at the previous version so the next run "
                          "sees the same difference. Set the OPENROUTER_API_KEY "
                          "repository secret to describe it."})
            continue

        drafted, why = ask_model(source, d, model, key)
        if drafted is None:
            outcomes.append({
                "source": sid, "url": source["url"], "status": "HELD_MODEL_UNAVAILABLE",
                "detail": f"{why} -- the snapshot was NOT advanced, so this change is "
                          f"held for the next run rather than lost."})
            continue

        if not drafted.get("material", True):
            st["snapshot_sha"] = sha(after)
            write_json(snap_path, {"source": sid, "url": source["url"],
                                   "captured": checked_at, "sha256": sha(after),
                                   "lines": after})
            outcomes.append({"source": sid, "url": source["url"],
                             "status": "NO_MATERIAL_CHANGE",
                             "detail": "the page differs but the difference is "
                                       "presentational; no entry was written."})
            continue

        problems = verify(drafted, d, after, before)
        if problems:
            outcomes.append({
                "source": sid, "url": source["url"], "status": "REJECTED_UNSUPPORTED",
                "problems": problems,
                "detail": "the drafted entry made a claim the diff does not support, "
                          "so it was discarded rather than published. The snapshot was "
                          "NOT advanced; the change is retried next run."})
            continue

        entry = {
            "id": f"{today}-{sid}",
            "date_observed": today,
            "checked_at": checked_at,
            "source_id": sid,
            "source_url": source["url"],
            "source_title": source["title"],
            "publisher": source["publisher"],
            "headline": str(drafted["headline"]).strip(),
            "summary": str(drafted["summary"]).strip(),
            "quotes": [{"side": q["side"], "text": q["text"]} for q in drafted["quotes"]],
            "evidence": {
                "previous_snapshot_sha256": snap["sha256"],
                "current_snapshot_sha256": sha(after),
                "previous_captured": snap["captured"],
                "added": d["added"][:200],
                "removed": d["removed"][:200],
            },
            "model": model,
        }
        new_entries.append(entry)
        st["snapshot_sha"] = sha(after)
        write_json(snap_path, {"source": sid, "url": source["url"],
                               "captured": checked_at, "sha256": sha(after),
                               "lines": after})
        outcomes.append({"source": sid, "url": source["url"], "status": "ENTRY_PUBLISHED",
                         "entry_id": entry["id"], "headline": entry["headline"]})

    if new_entries:
        entries_doc["entries"] = new_entries + entries_doc.get("entries", [])
        entries_doc["entries"].sort(key=lambda e: (e["date_observed"], e["id"]), reverse=True)
        write_json(ENTRIES, entries_doc)

    state["last_run"] = checked_at
    write_json(STATE, state)

    blind = [o for o in outcomes if o["status"].startswith("NAMED_STOP")
             and o.get("consecutive_failures", 0) >= MAX_CONSECUTIVE_FAILURES]
    checked = [o for o in outcomes if o["status"] in
               ("NO_CHANGE", "NO_MATERIAL_CHANGE", "ENTRY_PUBLISHED", "BASELINE_CAPTURED")]

    receipt = {
        "schema": "uscis-changelog-run-v1",
        "checked_at": checked_at,
        "offline": offline,
        "sources_declared": len(tracked["sources"]),
        "sources_checked": len(checked),
        "entries_written": len(new_entries),
        "outcomes": outcomes,
        "blind_sources": [o["source"] for o in blind],
        # Rule 0. A run that observed nothing still has to say what it did, and
        # "no change this week" is a legitimate, named outcome. Silence is not.
        "named_outcome": (
            "BLIND" if blind else
            # Matched on the FETCH failures specifically. Matching every
            # NAMED_STOP_* status made a run that fetched all three pages fine
            # and merely lacked an API key report itself as
            # SOURCES_UNREACHABLE -- a named outcome that named the wrong thing,
            # which on a Rule 0 receipt is the whole of the value lost.
            "SOURCES_UNREACHABLE" if any(
                o["status"] in ("NAMED_STOP_UNREACHABLE", "NAMED_STOP_UNREADABLE")
                for o in outcomes) else
            "HELD: a change was detected and could not be described this run "
            "(no API key); the snapshot was not advanced, so it is retried next "
            "run rather than lost."
            if any(o["status"] == "NAMED_STOP_NO_API_KEY" for o in outcomes) else
            "OFFLINE_NO_OBSERVATION" if offline else
            f"{len(new_entries)} entr{'y' if len(new_entries) == 1 else 'ies'} published"
            if new_entries else
            "BASELINE_CAPTURED: a first snapshot was taken of "
            f"{sum(1 for o in outcomes if o['status'] == 'BASELINE_CAPTURED')} page(s). "
            "There was no previous version to compare against, so the absence of an "
            "entry is not a statement that nothing changed."
            if any(o["status"] == "BASELINE_CAPTURED" for o in outcomes) else
            "HELD: a change was detected but could not be described this run; the "
            "snapshot was not advanced, so it is retried rather than lost."
            if any(o["status"].startswith(("HELD_", "REJECTED_")) for o in outcomes) else
            "NO CHANGE: every tracked USCIS page was fetched and compared, and none "
            "changed materially this week."),
    }
    write_json(RECEIPT, receipt)
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true",
                    help="Make no network call. Reports no observation; never 'no change'.")
    ap.add_argument("--model", default=os.environ.get("USCIS_CHANGELOG_MODEL", DEFAULT_MODEL))
    args = ap.parse_args()

    receipt = run(args.offline, args.model)
    print("USCIS FORM AND FEE CHANGELOG")
    print(f"  named outcome: {receipt['named_outcome']}")
    for o in receipt["outcomes"]:
        print(f"  [{o['status']}] {o['source']}: {o.get('detail', o.get('headline', ''))}")
    print(f"  receipt: {RECEIPT.relative_to(ROOT)}")

    if receipt["blind_sources"]:
        print(f"  HARD_FAIL blind for {MAX_CONSECUTIVE_FAILURES}+ consecutive checks: "
              f"{', '.join(receipt['blind_sources'])}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
