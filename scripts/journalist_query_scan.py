#!/usr/bin/env python3
"""Scan the day's journalist queries, draft the two or three worth answering, send none.

What this automates, and the one thing it deliberately does not
--------------------------------------------------------------
docs/EXTERNAL-AUTHORITY-PLAN.md ranks journalist source platforms first, by a
wide margin, and prices the whole play at "20 minutes each morning to scan".
That twenty minutes is the entire cost and it is also the entire risk: a daily
habit with no external forcing function dies in week three, and when it dies the
best-ratio play in the plan dies with it. So the scan and the draft are
automated.

**The send is not, and never will be.** Pitches go out in Sequoia's name as a
genuine expert. If an auto-sent pitch carries one wrong fact, a reporter prints
it under her name; that is a correction in a real publication and a source
relationship burned permanently, silently, and without anyone finding out for
months. Against that, the upside of auto-sending is about thirty seconds. There
is no send path in this file, no mail transport is imported, and
`scripts/validators/validate_journalist_query_lane.py` fails the build if one
ever appears.

What a run does
---------------
    ingest today's digest emails
      no credential      -> NAMED STOP, said once, not nagged daily
      unparseable digest -> NAMED STOP naming the provider. NEVER "no queries".
    prefilter to the declared beats               (data/journalist-queries/beats.json)
    judge each survivor strictly against the ledger
                                       (data/journalist-queries/expertise-ledger.json)
      not groundable     -> dropped, and the drop is counted and named
    0 relevant           -> SEND NOTHING AT ALL. Silence on a quiet day.
    1-3 relevant         -> one GitHub issue: the query, the deadline, the draft

The digest is a GitHub issue rather than an email because GitHub already mails
her on issues in this repository (the autopilot's failure issue uses the same
channel) and it needs no new credential. A lane that requires a mail-sending
secret before it can tell her anything is a lane that never tells her anything.

    python3 scripts/journalist_query_scan.py
    python3 scripts/journalist_query_scan.py --inbox-dir <dir> --no-issue

Secrets: SOS_IMAP_HOST / SOS_IMAP_USER / SOS_IMAP_PASSWORD for ingestion, and
OPENROUTER_API_KEY for drafting. Neither is ever printed.
"""
from __future__ import annotations

import argparse
import email
import hashlib
import imaplib
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from email import policy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANE = ROOT / "data/journalist-queries"
BEATS = LANE / "beats.json"
LEDGER = LANE / "expertise-ledger.json"
FORMATS = LANE / "query-formats.json"
DIGESTS = LANE / "digests"
STATE = LANE / "state.json"
RECEIPT = ROOT / "reports/journalist-query-scan-latest.json"
KEY_FILE = Path.home() / "GitHub/how-we-know/.secrets/openrouter_key.txt"

API = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"

FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)
# An ISO date is ONE number, not three. Without the first alternative, the date
# a dataset was collected on splits into 2026 / 09 / 01 and the guard rejects a
# draft for quoting a fact's own observation date. A trailing comma is likewise
# punctuation, not part of the figure.
NUMBER_RE = re.compile(r"\d{4}-\d{2}-\d{2}|\d(?:[\d,]*\d)?(?:\.\d+)?")


class NamedStop(Exception):
    def __init__(self, code: str, message: str, unblock: str = ""):
        super().__init__(f"{code}: {message}")
        self.code, self.message, self.unblock = code, message, unblock


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8", newline="\n")


# ------------------------------------------------------------------ ingest

def imap_messages(cfg: dict) -> list[tuple[str, str]]:
    """Read recent digests over IMAP. Read-only: nothing is marked, moved or deleted."""
    env = cfg["env"]
    host = os.environ.get(env["host"], "").strip()
    user = os.environ.get(env["user"], "").strip()
    password = os.environ.get(env["password"], "").strip()
    if not (host and user and password):
        raise NamedStop(
            "NO_MAILBOX_CREDENTIAL",
            "no journalist-query mailbox is configured, so no queries were ingested "
            "and none could have been missed.",
            f"Subscribe to Source of Sources at sourceofsources.com (free, name and "
            f"email only), then set the repository secrets {env['host']}, "
            f"{env['user']} and {env['password']} to a mailbox that receives it.")

    port = int(os.environ.get(env["port"], "993") or 993)
    folder = os.environ.get(env["folder"], "") or cfg.get("default_folder", "INBOX")
    since = (date.today() - timedelta(days=int(cfg.get("lookback_days", 2)))).strftime("%d-%b-%Y")

    out: list[tuple[str, str]] = []
    conn = imaplib.IMAP4_SSL(host, port)
    try:
        conn.login(user, password)
        conn.select(f'"{folder}"', readonly=True)
        seen: set[bytes] = set()
        for sender in cfg["senders"]:
            typ, data = conn.search(None, "SINCE", since, "FROM", f'"{sender}"')
            if typ != "OK":
                continue
            for uid in data[0].split():
                if uid in seen:
                    continue
                seen.add(uid)
                typ, raw = conn.fetch(uid, "(RFC822)")
                if typ != "OK" or not raw or not raw[0]:
                    continue
                msg = email.message_from_bytes(raw[0][1], policy=policy.default)
                out.append((str(msg.get("From", sender)),
                            str(msg.get("Subject", "")), message_text(msg)))
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001 - a failed logout is not a run failure
            pass
    return out


def message_text(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return part.get_content()
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                return re.sub(r"<[^>]+>", " ", part.get_content())
        return ""
    content = msg.get_content()
    if msg.get_content_type() == "text/html":
        content = re.sub(r"<[^>]+>", " ", content)
    return content


def dir_messages(inbox: Path) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for path in sorted(inbox.iterdir()):
        if path.suffix.lower() not in (".eml", ".txt"):
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() == ".eml":
            msg = email.message_from_string(raw, policy=policy.default)
            out.append((str(msg.get("From", path.name)),
                        str(msg.get("Subject", "")), message_text(msg)))
        else:
            first = raw.lstrip().splitlines()[0] if raw.strip() else ""
            subject = first[8:].strip() if first.lower().startswith("subject:") else ""
            out.append((path.name, subject, raw))
    return out


# ------------------------------------------------------------------- parse

def compile_formats(formats: dict) -> dict:
    labels = {}
    for field, names in formats["field_labels"].items():
        alternation = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
        labels[field] = re.compile(rf"^\s*(?:{alternation})\s*[:\-]\s*(.*)$", re.I)
    return {
        "delimiters": [re.compile(p, re.M) for p in formats["block_delimiters"]],
        "labels": labels,
        "numbered": re.compile(formats["numbered_summary"], re.I),
        "strip": [re.compile(p, re.I) for p in formats["strip_trailing_from_body"]],
        "required": formats["minimum_fields_for_a_query"],
        "one_of": formats["must_also_have_one_of"],
    }


def split_blocks(body: str, compiled: dict) -> list[str]:
    text = body
    for pattern in compiled["delimiters"]:
        text = pattern.sub("\n@@BLOCK@@\n", text)
    blocks = [b.strip() for b in text.split("@@BLOCK@@")]
    return [b for b in blocks if b]


def parse_block(block: str, compiled: dict) -> dict | None:
    fields: dict[str, str] = {}
    current: str | None = None
    for line in block.splitlines():
        if any(p.search(line) for p in compiled["strip"]):
            current = None
            continue
        matched = False
        for field, pattern in compiled["labels"].items():
            m = pattern.match(line)
            if m:
                fields[field] = m.group(1).strip()
                current = field
                matched = True
                break
        if matched:
            continue
        if "summary" not in fields:
            m = compiled["numbered"].match(line)
            if m and len(m.group(1).strip()) > 10:
                fields["summary"] = m.group(1).strip()
                current = "summary"
                continue
        if current and line.strip():
            fields[current] = (fields[current] + " " + line.strip()).strip()

    if not all(fields.get(f) for f in compiled["required"]):
        return None
    if not any(fields.get(f) for f in compiled["one_of"]):
        return None
    return fields


def parse_digest(sender: str, body: str, compiled: dict) -> list[dict]:
    queries: list[dict] = []
    for block in split_blocks(body, compiled):
        parsed = parse_block(block, compiled)
        if parsed:
            parsed["provider"] = sender
            queries.append(parsed)
    return queries



def non_digest_signature(subject: str, body: str, formats: dict) -> str | None:
    """Positively identify a message that is not a query digest at all.

    Recognition is by DECLARED signature only. "It had no query markers" is not
    grounds for excusing a message, because that is also exactly what a changed
    format looks like, and excusing it is how this lane would go silently dead.
    A signature needs its subject pattern AND every one of its body markers, so
    a real digest carrying a stray phrase is never dismissed.
    """
    for sig in formats.get("non_digest_messages", {}).get("signatures", []):
        if not re.search(sig["subject"], subject or "", re.I):
            continue
        if all(re.search(re.escape(m), body, re.I) for m in sig["body_requires_all"]):
            return sig["id"]
    return None


def partial_parse_floor(formats: dict) -> int:
    return int(formats.get("expected_queries_per_digest", {})
               .get("partial_parse_floor", 0) or 0)


def query_identity(query: dict) -> str:
    """Stable id for one query, so the same one is never surfaced twice.

    The mailbox is read with a lookback window, so consecutive runs see the same
    digest. Without this the same query would be drafted and surfaced every
    morning until it aged out -- the lane would look busy while repeating itself,
    and she would learn to skim it.
    """
    basis = "|".join(str(query.get(f, "")).strip().lower()
                     for f in ("summary", "email", "deadline", "outlet"))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- prefilter

def beat_for(query: dict, beats: dict) -> tuple[str | None, list[str]]:
    haystack = " ".join(str(v) for k, v in query.items() if k != "provider").lower()
    for phrase in beats["hard_exclusions"]["phrases"]:
        if phrase in haystack:
            return None, [f"excluded: {phrase!r}"]
    for beat in beats["beats"]:
        hits = [k for k in beat["keywords"] if k in haystack]
        if hits:
            return beat["id"], hits
    return None, []


# ------------------------------------------------------------------- draft

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
    body = json.dumps({"model": model, "messages": messages, "max_tokens": 1500,
                       "temperature": 0.2, "usage": {"include": True}}).encode()
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://memphisvendorlibrary.com/",
        "X-Title": "Authority Network - journalist query drafting",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def strip_fence(content: str) -> str:
    m = FENCE_RE.match(content)
    return m.group(1) if m else content


PROMPT = """A reporter has posted the query below. Decide whether Sequoia Taylor can
answer it from FIRST-HAND knowledge, and if she can, draft her reply.

Your default answer is NO. Dropping a query costs nothing. Sending a reporter a
generic or invented answer costs a source relationship permanently. A 2-in-10 hit
rate on five real answers beats 0-in-50 on generic ones, so reject freely.

THE QUERY
{query}

THE ONLY THINGS SHE MAY CLAIM
You may use these facts and NOTHING else. You may not add context you happen to
know, you may not generalise beyond a fact, and you may not soften a fact into a
vaguer claim that sounds more broadly applicable.

{facts}

REQUIRED DISCLOSURE, to appear in the draft in substance:
{disclosure}

Reply with a JSON object and nothing else:

{{
  "answerable": true or false,
  "why": "one sentence. If false, what she would have had to invent to answer.",
  "facts_used": ["the exact id of each fact the draft relies on"],
  "draft": "the reply, or an empty string if answerable is false"
}}

Rules for the draft, each of which will cause it to be discarded if broken:
- Under {max_words} words. Count them.
- Lead with the specific claim, not with an introduction.
- Every factual statement must be traceable to a listed fact. Every NUMBER in
  the draft must appear in a fact you listed in facts_used. Do not compute a new
  number, do not round one, and do not add a year that is not in a fact.
- Say plainly who she is and what she owns. Disclosure is an advantage here:
  reporters are wary of undisclosed commercial sources.
- No superlatives, no "leading expert", no invented credential, no claim about
  how long she has done anything.
- Write it as her, in first person, plainly. Not a press release.
- If the honest answer is that the facts do not cover this query, set
  "answerable" to false. That is a good outcome, not a failure.
"""


def draft_for(query: dict, ledger: dict, beats: dict, model: str, key: str) -> tuple[dict | None, str]:
    facts = "\n".join(
        f'- id: {f["id"]}\n  claim: {f["claim"]}\n  checkable at: {f["public_url"]}'
        for f in ledger["facts"])
    rendered = "\n".join(f"{k}: {v}" for k, v in query.items() if k != "provider")
    messages = [{"role": "user", "content": PROMPT.format(
        query=rendered, facts=facts,
        disclosure=ledger["attribution"]["disclosure_sentence"],
        max_words=beats["max_draft_words"])}]
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


# ------------------------------------------------------------------ verify

def verify_draft(drafted: dict, ledger: dict, beats: dict) -> list[str]:
    """The grounding guard. Returns the reasons this draft may not be surfaced.

    Applied here, and applied again by
    scripts/validators/validate_journalist_query_lane.py against every draft that
    was recorded, so a draft edited in the digest file fails the same way an
    invented one does.
    """
    problems: list[str] = []
    by_id = {f["id"]: f for f in ledger["facts"]}

    used = drafted.get("facts_used") or []
    if not isinstance(used, list) or not used:
        return ["draft cites no ledger fact; an ungrounded pitch may not be surfaced"]
    unknown = [fid for fid in used if fid not in by_id]
    if unknown:
        problems.append(f"draft cites ledger facts that do not exist: {unknown}")

    text = str(drafted.get("draft", "")).strip()
    if not text:
        return problems + ["draft is empty"]

    words = len(text.split())
    if words > int(beats["max_draft_words"]):
        problems.append(f"draft is {words} words; the limit is {beats['max_draft_words']}")

    # Numbers are the highest-risk fabrication and the only claim class that can
    # be checked mechanically, so they are checked mechanically. Every number in
    # the draft has to appear in a fact the draft says it used.
    allowed: set[str] = set()
    for fid in used:
        fact = by_id.get(fid)
        if not fact:
            continue
        allowed |= set(NUMBER_RE.findall(fact["claim"]))
        allowed |= set(fact.get("numbers", []))
        allowed |= set(NUMBER_RE.findall(fact["public_url"]))
    allowed |= set(NUMBER_RE.findall(ledger["attribution"]["disclosure_sentence"]))
    for number in NUMBER_RE.findall(text):
        if number.replace(",", "") not in {a.replace(",", "") for a in allowed}:
            problems.append(f"draft states a number that is in none of the facts it "
                            f"cites: {number!r}")

    lowered = text.lower()
    for banned in ("leading expert", "world-class", "renowned", "award-winning",
                   "years of experience", "decades of experience", "industry leader"):
        if banned in lowered:
            problems.append(f"draft contains an unevidenced credential claim: {banned!r}")

    # The disclosure has to survive into the draft, not just into the prompt.
    if not any(token in lowered for token in
               ("i own", "i run", "my publication", "publications i own", "i publish")):
        problems.append("draft does not state plainly who she is and what she owns")
    return problems


# ----------------------------------------------------------------- surface

def open_issue(title: str, body: str) -> tuple[bool, str]:
    """Hand the digest to GitHub, which already mails her about this repository.

    Not a send path: this reaches the owner, never a journalist. The pitch itself
    leaves this system only when she copies it and sends it herself.
    """
    try:
        proc = subprocess.run(
            ["gh", "issue", "create", "--title", title, "--body", body],
            cwd=ROOT, text=True, capture_output=True, timeout=90)
        if proc.returncode != 0:
            return False, proc.stderr.strip()[:300]
        return True, proc.stdout.strip()
    except Exception as exc:  # noqa: BLE001 - failing to notify must not lose the digest
        return False, f"{type(exc).__name__}: {exc}"


def render_digest(rows: list[dict], ledger: dict) -> str:
    parts = [
        f"{len(rows)} journalist quer{'y' if len(rows) == 1 else 'ies'} today that can be "
        "answered from first-hand, published work.",
        "",
        "**Nothing has been sent.** Each draft below is ready to copy, edit and send "
        "yourself, from your own address, in your own name. This lane never sends.",
        "",
    ]
    for i, row in enumerate(rows, 1):
        q = row["query"]
        parts += [
            f"---",
            "",
            f"### {i}. {q.get('summary', '(no summary)')}",
            "",
            f"- **Outlet:** {q.get('outlet', 'not stated')}",
            f"- **Deadline:** {q.get('deadline', 'not stated')}",
            f"- **Send to:** {q.get('email', 'not stated')}",
            f"- **Beat:** {row['beat']}",
            f"- **Grounded in:** {', '.join(row['facts_used'])}",
            "",
            "**The reporter asked:**",
            "",
            "> " + (q.get("query") or q.get("summary", "")).replace("\n", "\n> "),
            "",
            "**Draft reply:**",
            "",
            "```",
            row["draft"],
            "```",
            "",
        ]
    parts += [
        "---",
        "",
        "Every claim above traces to a fact in `data/journalist-queries/expertise-ledger.json`, "
        "and every number in a draft was checked against the fact it came from. If a draft "
        "says something you would not say, the fix is to edit the ledger, not the draft: "
        "the ledger is what the next draft is built from.",
        "",
        f"Disclosure line these drafts are built to carry: _{ledger['attribution']['disclosure_sentence']}_",
    ]
    return "\n".join(parts)


# --------------------------------------------------------------------- run


def announce_stops(receipt: dict, state: dict, args) -> None:
    """Tell the owner, once, about a stop only she can clear.

    Said ONCE. A daily issue reading "still not subscribed" is a standing
    instruction nobody follows, which this repository has already paid for
    (scripts/validators/validate_no_manual_lane.py records what that cost).

    This lives in its own function because it did not used to. It sat at the
    tail of run(), and the NO_MAILBOX_CREDENTIAL path returns from the middle of
    run() -- so the code that announces the credential stop was unreachable from
    the credential stop. Two CI runs printed a perfect named stop into a log
    nobody reads and opened nothing. A guard that cannot reach what it governs
    is the defect class this repository names explicitly, and this was one.
    """
    if args.no_issue:
        return
    unresolved = [s for s in receipt["stops"]
                  if s["code"] in ("NO_MAILBOX_CREDENTIAL", "NO_API_KEY")]
    announced = set(state.get("stops_announced", []))
    fresh = [s for s in unresolved if s["code"] not in announced]
    if fresh:
        body = "\n\n".join(
            f"**{s['code']}**\n\n{s['message']}\n\n**To unblock:** {s.get('unblock', '')}"
            for s in fresh)
        ok, detail = open_issue(
            "Journalist-query lane is built and waiting on one credential",
            body + "\n\nThis is said once. The daily scan will keep running and will "
                   "stay silent until it is unblocked, rather than opening this issue "
                   "again every morning.")
        # Whether the owner was actually told is itself a fact the receipt carries.
        # A notification lane that fails silently is indistinguishable from one
        # that had nothing to say.
        receipt["announced"] = {"ok": ok, "codes": [s["code"] for s in fresh],
                                "detail": "" if ok else str(detail)[:300]}
        if ok:
            state["stops_announced"] = sorted(announced | {s["code"] for s in fresh})
        else:
            receipt["stops"].append({
                "code": "ANNOUNCE_FAILED",
                "message": f"could not open the issue that tells the owner what to set: "
                           f"{detail}. The stop was NOT marked announced, so the next "
                           f"run tries again.",
                "unblock": "Read the named stop in this run's log; it says exactly what "
                           "to set."})
    for code in list(state.get("stops_announced", [])):
        if code not in {s["code"] for s in unresolved}:
            state["stops_announced"].remove(code)


def run(args) -> dict:
    beats = load(BEATS)
    ledger = load(LEDGER)
    compiled = compile_formats(load(FORMATS))
    state = load(STATE) if STATE.exists() else {}
    today = date.today().isoformat()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    receipt = {
        "schema": "journalist-query-scan-v1",
        "run_at": now,
        "digests_read": 0,
        "queries_ingested": 0,
        "non_digest_messages": [],
        "already_surfaced": 0,
        "dropped_by_beat_filter": 0,
        "dropped_as_ungroundable": 0,
        "dropped_by_grounding_guard": 0,
        "surfaced": 0,
        "notified": False,
        "stops": [],
        "drops": [],
        "named_outcome": "",
    }

    # ------------------------------------------------------------- ingest
    try:
        if args.inbox_dir:
            inbox = Path(args.inbox_dir)
            if not inbox.is_dir():
                raise NamedStop("NO_INBOX_DIR", f"{inbox} is not a directory")
            messages = dir_messages(inbox)
        else:
            messages = imap_messages(beats["ingestion"]["adapters"]["imap"])
    except NamedStop as stop:
        receipt["stops"].append({"code": stop.code, "message": stop.message,
                                 "unblock": stop.unblock})
        receipt["named_outcome"] = (
            f"NAMED STOP {stop.code}: {stop.message} This is not 'no relevant queries'; "
            f"it is 'no queries were looked at'.")
        announce_stops(receipt, state, args)
        state["last_run"] = now
        write_json(STATE, state)
        write_json(RECEIPT, receipt)
        return receipt

    receipt["digests_read"] = len(messages)

    formats = load(FORMATS)
    floor = partial_parse_floor(formats)
    queries: list[dict] = []
    for sender, subject, body in messages:
        signature = non_digest_signature(subject, body, formats)
        if signature:
            # Positively recognised as not a digest. Counted and named, never a
            # stop: the welcome email is not a broken parser.
            receipt["non_digest_messages"].append(
                {"from": sender, "subject": subject[:120], "signature": signature})
            continue

        parsed = parse_digest(sender, body, compiled)
        if not parsed and len(body.strip()) > 200:
            # The failure that must never look like a quiet day.
            head = " / ".join(body.strip().splitlines()[:4])[:300]
            receipt["stops"].append({
                "code": "UNPARSEABLE_DIGEST",
                "message": f"a {len(body)}-character message from {sender} "
                           f"(subject {subject[:80]!r}) produced zero parseable "
                           f"queries and matches no declared non-digest signature. "
                           f"It is being reported as UNREAD, NOT as 'nothing "
                           f"relevant'.",
                "unblock": "If it is a digest, correct the field labels in "
                           "data/journalist-queries/query-formats.json. If it is not "
                           "a digest, declare its signature in the same file under "
                           "non_digest_messages.",
                "first_lines": head})
            continue

        if parsed and floor and len(parsed) < floor:
            # A short read is the quiet version of the same failure. The
            # publisher states 10-15 queries per digest, so a digest yielding two
            # has dropped eight that nobody knows were there.
            receipt["stops"].append({
                "code": "PARTIAL_DIGEST_PARSE",
                "message": f"a {len(body)}-character digest from {sender} parsed to "
                           f"only {len(parsed)} quer"
                           f"{'y' if len(parsed) == 1 else 'ies'}, below the floor of "
                           f"{floor}. The publisher states these carry 10-15. The "
                           f"{len(parsed)} that parsed ARE being processed below; this "
                           f"stop exists because the ones that did not are invisible.",
                "unblock": "Compare the digest against the field labels in "
                           "data/journalist-queries/query-formats.json.",
                "parsed": len(parsed)})
        queries.extend(parsed)

    receipt["queries_ingested"] = len(queries)

    # Never surface the same query twice. The mailbox is read with a lookback
    # window, so consecutive runs see the same digest.
    already = set(state.get("surfaced_ids", []))
    fresh_queries = []
    for query in queries:
        qid = query_identity(query)
        if qid in already:
            receipt["already_surfaced"] += 1
            continue
        query["_id"] = qid
        fresh_queries.append(query)
    queries = fresh_queries

    # ---------------------------------------------------------- prefilter
    candidates: list[tuple[dict, str]] = []
    for query in queries:
        beat, hits = beat_for(query, beats)
        if not beat:
            receipt["dropped_by_beat_filter"] += 1
            receipt["drops"].append({
                "summary": query.get("summary", "")[:120],
                "why": hits[0] if hits else "matches no declared beat"})
            continue
        candidates.append((query, beat))

    # -------------------------------------------------------------- draft
    surfaced: list[dict] = []
    if candidates:
        key = api_key()
        if not key:
            receipt["stops"].append({
                "code": "NO_API_KEY",
                "message": f"{len(candidates)} quer{'y' if len(candidates) == 1 else 'ies'} "
                           f"matched a beat but no draft could be written.",
                "unblock": "Set the OPENROUTER_API_KEY repository secret."})
        else:
            for query, beat in candidates:
                if len(surfaced) >= int(beats["max_per_digest"]):
                    break
                drafted, why = draft_for(query, ledger, beats, args.model, key)
                if drafted is None:
                    receipt["stops"].append({
                        "code": "DRAFT_UNAVAILABLE", "message": why,
                        "summary": query.get("summary", "")[:120]})
                    continue
                if not drafted.get("answerable"):
                    receipt["dropped_as_ungroundable"] += 1
                    receipt["drops"].append({
                        "summary": query.get("summary", "")[:120],
                        "why": str(drafted.get("why", "not answerable from the ledger"))[:200]})
                    continue
                problems = verify_draft(drafted, ledger, beats)
                if problems:
                    receipt["dropped_by_grounding_guard"] += 1
                    receipt["drops"].append({
                        "summary": query.get("summary", "")[:120],
                        "why": "; ".join(problems)[:300]})
                    continue
                surfaced.append({
                    "id": query.get("_id"), "query": query, "beat": beat,
                    "draft": drafted["draft"].strip(),
                    "facts_used": drafted["facts_used"],
                    "why": drafted.get("why", "")})

    receipt["surfaced"] = len(surfaced)

    # ------------------------------------------------------------ surface
    if surfaced:
        state["surfaced_ids"] = sorted(
            set(state.get("surfaced_ids", [])) | {r["id"] for r in surfaced if r.get("id")}
        )[-500:]
        write_json(DIGESTS / f"{today}.json",
                   {"date": today, "generated_at": now, "sent": False,
                    "note": "Nothing here was sent to anyone. Drafts are for the owner "
                            "to review, edit and send herself.",
                    "items": surfaced})
        body = render_digest(surfaced, ledger)
        if args.no_issue:
            print(body)
            receipt["notified"] = False
        else:
            ok, detail = open_issue(
                f"{len(surfaced)} journalist quer"
                f"{'y' if len(surfaced) == 1 else 'ies'} worth answering "
                f"({today}) - drafts ready, nothing sent", body)
            receipt["notified"] = ok
            if not ok:
                receipt["stops"].append({
                    "code": "NOTIFY_FAILED",
                    "message": f"the digest was written to "
                               f"data/journalist-queries/digests/{today}.json but the "
                               f"issue could not be opened: {detail}"})
        receipt["named_outcome"] = (
            f"{len(surfaced)} quer{'y' if len(surfaced) == 1 else 'ies'} surfaced with "
            f"drafts. NOTHING WAS SENT.")
    elif receipt["stops"]:
        receipt["named_outcome"] = (
            "NAMED STOP: " + "; ".join(s["code"] for s in receipt["stops"]))
    elif receipt["already_surfaced"] and not receipt["surfaced"] and not receipt["stops"]:
        receipt["named_outcome"] = (
            f"ALREADY HANDLED: {receipt['queries_ingested']} quer"
            f"{'y' if receipt['queries_ingested'] == 1 else 'ies'} were read and nothing "
            f"new was surfaced -- {receipt['already_surfaced']} had already been "
            f"surfaced on an earlier run and "
            f"{receipt['dropped_by_beat_filter']} matched no beat. The mailbox is read "
            f"with a lookback window on purpose, so a missed run never loses a digest; "
            f"nothing is ever surfaced twice.")
    elif (receipt["non_digest_messages"] and not receipt["queries_ingested"]
          and not receipt["stops"]):
        receipt["named_outcome"] = (
            f"NO QUERY DIGEST YET: {len(receipt['non_digest_messages'])} message(s) "
            f"were read and every one is a recognised non-digest "
            f"({', '.join(m['signature'] for m in receipt['non_digest_messages'])}). "
            f"No digest has arrived, so no query was looked at. This is NOT "
            f"'no relevant queries'.")
    else:
        receipt["named_outcome"] = (
            f"NO RELEVANT QUERIES: {receipt['queries_ingested']} quer"
            f"{'y' if receipt['queries_ingested'] == 1 else 'ies'} were read from "
            f"{receipt['digests_read']} digest(s) and every one was dropped "
            f"({receipt['dropped_by_beat_filter']} off-beat, "
            f"{receipt['dropped_as_ungroundable']} not answerable from first-hand work, "
            f"{receipt['dropped_by_grounding_guard']} drafted but ungrounded"
            + (f", {receipt['already_surfaced']} already surfaced on an earlier run"
               if receipt["already_surfaced"] else "")
            + "). Nothing was sent, and nothing should have been.")

    announce_stops(receipt, state, args)
    state["last_run"] = now
    write_json(STATE, state)
    write_json(RECEIPT, receipt)
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--inbox-dir", help="Read .eml/.txt digests from a directory "
                                        "instead of IMAP.")
    ap.add_argument("--no-issue", action="store_true",
                    help="Print the digest instead of opening a GitHub issue.")
    ap.add_argument("--model", default=os.environ.get("JOURNALIST_QUERY_MODEL", DEFAULT_MODEL))
    args = ap.parse_args()

    receipt = run(args)
    print("JOURNALIST QUERY SCAN")
    print(f"  named outcome: {receipt['named_outcome']}")
    print(f"  messages read: {receipt['digests_read']}; "
          f"non-digest: {len(receipt['non_digest_messages'])}; "
          f"queries ingested: {receipt['queries_ingested']}; "
          f"already surfaced: {receipt['already_surfaced']}; "
          f"surfaced: {receipt['surfaced']}")
    for drop in receipt["drops"][:10]:
        print(f"  [dropped] {drop['summary']!r}: {drop['why']}")
    for stop in receipt["stops"]:
        print(f"  [{stop['code']}] {stop['message']}")
        if stop.get("unblock"):
            print(f"      unblock: {stop['unblock']}")
    print(f"  receipt: {RECEIPT.relative_to(ROOT)}")
    print("  nothing was sent to any journalist; this lane has no send path.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
