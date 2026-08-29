#!/usr/bin/env python3
"""Buffer as a DELIVERY ROUTE for X. Not a new platform.

Why this exists
---------------
X's own API is pay-per-use: about $0.20 for a post carrying a URL, and every
post this network sends carries one. The owner has declined to fund it, so
`platforms.x.enabled` is false in data/social-brand-policy.json and the
publisher makes ZERO requests to X. Distribution continued by hand from
reports/social-drafts.md.

She already pays nothing for a Buffer account, and Buffer can put a post on the
same X profile at no per-post cost. So Buffer is wired in as another way for an
X post to LEAVE, alongside "she pastes it by hand". The queue, the priority
order, the brand rotation and the drafting fallback are all unchanged: this
module only answers "can this X post go out through Buffer instead of her
hands, and did Buffer take it".

The endpoint
------------
`https://api.buffer.com/graphql`, `Authorization: Bearer <token>`. Two other
plausible endpoints are dead ends and are recorded here so nobody re-discovers
them: the legacy REST API (`api.bufferapp.com/1/*`) answers 401 "Public API
tokens are not accepted for REST API access" and Buffer retires it on
2027-02-01; `graph.buffer.com` answers 401 "Please use api.buffer.com".

Limits are DISCOVERED, never hardcoded
--------------------------------------
Buffer's own per-channel daily posting limit is read at runtime from the
`dailyPostingLimits` query and used as a hard ceiling. A number typed into this
file would be a guess that stays wrong after Buffer changes it, and the cost of
being wrong here is the failure this repository already had once: on 2026-08-29
a run made 581 requests in 76 seconds because its caps counted successes rather
than attempts, so a refusal cost one request per queue entry.

Two rules follow, and both are enforced by the caller
(scripts/social_publisher.py) and guarded by
scripts/validators/validate_buffer_route.py:

  count attempts, not successes   the budget is spent before the call
  halt on the first refusal       a route that has said no is not asked again
                                  in the same run, ever

Queued is not published
-----------------------
`createPost` puts a post in the Buffer queue for the channel; Buffer publishes
it at the channel's next posting time. So an accepted post is `buffer_queued`,
not `posted`, and the two are recorded differently on the queue entry. Nothing
here claims a post is live on X.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

ENDPOINT = os.getenv("BUFFER_GRAPHQL_ENDPOINT", "https://api.buffer.com/graphql")
TOKEN_ENV = "BUFFER_ACCESS_TOKEN"
TIMEOUT = 30


class BufferError(RuntimeError):
    """A refusal from Buffer, carrying enough to decide whether to stop."""

    def __init__(self, message, status=None, kind="error"):
        super().__init__(message)
        self.status = status
        self.kind = kind


def token():
    return (os.getenv(TOKEN_ENV) or "").strip()


def has_token():
    return bool(token())


def _redact(text):
    """Never let the token reach a log, an artifact or a report.

    The publisher prints its whole report to the workflow log and commits it to
    reports/. A GraphQL error that echoed the Authorization header, or a token
    pasted into a query by mistake, would be committed with it.
    """
    secret = token()
    text = str(text)
    if secret and secret in text:
        text = text.replace(secret, "***REDACTED***")
    return text


def graphql(query, variables=None, timeout=TIMEOUT, opener=None):
    """One GraphQL request. Raises BufferError on anything that is not data."""
    secret = token()
    if not secret:
        raise BufferError(f"{TOKEN_ENV} is not set", kind="uncredentialled")
    body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT, data=body, method="POST",
        headers={"Authorization": f"Bearer {secret}",
                 "Content-Type": "application/json",
                 "Accept": "application/json"},
    )
    send = opener or urllib.request.urlopen
    try:
        with send(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", 200)
    except urllib.error.HTTPError as err:
        detail = _redact(err.read().decode("utf-8", errors="replace")[:400])
        raise BufferError(f"HTTP {err.code}: {detail}", status=err.code,
                          kind="http_error") from None
    except Exception as err:  # noqa: BLE001 - transport failures are refusals too
        raise BufferError(_redact(str(err))[:400], kind="transport") from None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise BufferError(f"non-JSON response: {_redact(raw)[:200]}",
                          status=status, kind="bad_response") from None
    if payload.get("errors"):
        messages = "; ".join(str(e.get("message"))[:200] for e in payload["errors"])
        raise BufferError(f"GraphQL error: {_redact(messages)}", status=status,
                          kind="graphql_error")
    data = payload.get("data")
    if data is None:
        raise BufferError("GraphQL response carried no data", status=status,
                          kind="bad_response")
    return data
