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


# Buffer's name for X. The Service enum on this schema still says "twitter";
# there is no "x" member, so matching on "x" finds nothing and the route would
# report "no channel connected" forever with an X channel sitting right there.
SERVICE_FOR_PLATFORM = {"x": ("twitter",)}

CHANNELS_QUERY = """
query C($input: ChannelsInput!) {
  channels(input: $input) {
    id name service serviceId type isDisconnected isLocked isQueuePaused timezone
  }
}
"""

ACCOUNT_QUERY = """
query A {
  account {
    id
    organizations {
      id name channelCount
      limits { channels scheduledPosts }
    }
  }
}
"""

LIMITS_QUERY = """
query L($input: DailyPostingLimitsInput!) {
  dailyPostingLimits(input: $input) { channelId isAtLimit limit scheduled sent }
}
"""

CREATE_POST = """
mutation P($input: CreatePostInput!) {
  createPost(input: $input) {
    __typename
    ... on PostActionSuccess { post { id status dueAt channelId } }
    ... on NotFoundError { message }
    ... on UnauthorizedError { message }
    ... on InvalidInputError { message }
    ... on LimitReachedError { message }
    ... on RestProxyError { code message }
    ... on UnexpectedError { message }
  }
}
"""

# Buffer answers createPost with a union. Exactly one member is a success; every
# other member is a refusal, and a refusal ends the route for the run. Listing
# them by name rather than testing for the success case means a member Buffer
# adds later is treated as a refusal, which is the safe direction.
SUCCESS_TYPE = "PostActionSuccess"

# Buffer's queue, not an immediate publish. `addToQueue` puts the post in the
# channel's queue at its next free posting slot, and `automatic` means Buffer
# sends it itself rather than pinging a phone to post by hand. The alternatives
# are recorded because picking the wrong one silently changes what "posted"
# means: `shareNow` publishes on the spot, and `notification` publishes nothing
# at all -- it asks the owner to. Neither is what a scheduled lane wants.
DEFAULT_MODE = "addToQueue"
DEFAULT_SCHEDULING_TYPE = "automatic"


class Route:
    """One run's worth of Buffer delivery for one platform.

    Holds the two rules that matter and cannot be bypassed by a caller:

      count attempts   `remaining()` falls on every attempt, before the request
                       is made, never on success. A run whose calls all fail
                       spends its budget exactly as fast as one that works.
      halt on refusal  the first refusal sets `halted` and every later call
                       raises without touching the network. There is no retry
                       path in this class at all.

    The 2026-08-29 failure this prevents: 581 requests in 76 seconds against an
    API that had already refused, because the caps counted successes.
    """

    def __init__(self, platform="x", opener=None, policy_daily_limit=None):
        self.platform = platform
        self.opener = opener
        self.policy_daily_limit = policy_daily_limit
        self.available = False
        self.reason = f"{TOKEN_ENV} has not been read yet"
        self.organization_id = None
        self.channel = None
        self.channel_id = None
        self.buffer_daily_limit = None
        self.buffer_used_today = None
        self.headroom = 0
        self.attempts = 0
        self.accepted = 0
        self.halted = None
        self.plan_limits = {}
        self.channels_seen = []

    # -- discovery ---------------------------------------------------------
    def open(self):
        """Find the channel and read the real ceiling. Never guesses a number."""
        if not has_token():
            self.reason = (f"{TOKEN_ENV} is absent from this environment, so Buffer "
                           f"cannot be asked to carry anything")
            return self
        try:
            account = graphql(ACCOUNT_QUERY, opener=self.opener)["account"]
        except BufferError as err:
            self.reason = f"Buffer refused the account lookup: {err}"
            self.halted = self.reason
            return self
        orgs = account.get("organizations") or []
        if not orgs:
            self.reason = "the Buffer account carries no organization to post from"
            return self
        wanted = SERVICE_FOR_PLATFORM.get(self.platform, ())
        for org in orgs:
            self.organization_id = org["id"]
            self.plan_limits = org.get("limits") or {}
            try:
                channels = graphql(CHANNELS_QUERY,
                                   {"input": {"organizationId": org["id"]}},
                                   opener=self.opener)["channels"]
            except BufferError as err:
                self.reason = f"Buffer refused the channel list: {err}"
                self.halted = self.reason
                return self
            self.channels_seen.extend(
                {k: c.get(k) for k in ("id", "name", "service", "isLocked",
                                       "isDisconnected", "isQueuePaused")}
                for c in channels)
            for channel in channels:
                if str(channel.get("service", "")).lower() in wanted:
                    self.channel = channel
                    self.channel_id = channel["id"]
                    break
            if self.channel:
                break
        if not self.channel:
            services = sorted({str(c.get("service")) for c in self.channels_seen})
            self.reason = (
                f"no {self.platform} channel is connected to this Buffer account. "
                f"Buffer calls it {'/'.join(wanted)}; the channels connected are "
                f"{services or ['none']}. Connect the X profile at "
                f"buffer.com -> Channels -> New Channel and this route starts "
                f"carrying posts on the next run with no code change."
            )
            return self
        if self.channel.get("isDisconnected"):
            self.reason = (f"the Buffer {self.platform} channel "
                           f"{self.channel.get('name')!r} is disconnected; "
                           f"reconnect it in Buffer")
            return self
        if self.channel.get("isLocked"):
            self.reason = (f"the Buffer {self.platform} channel "
                           f"{self.channel.get('name')!r} is locked by the plan's "
                           f"channel allowance, so Buffer will not accept posts for it")
            return self
        try:
            limits = graphql(LIMITS_QUERY,
                             {"input": {"channelIds": [self.channel_id]}},
                             opener=self.opener)["dailyPostingLimits"]
        except BufferError as err:
            # No discovered ceiling means no ceiling this module is willing to
            # act on. It refuses to post rather than fall back to a guess.
            self.reason = f"Buffer would not report its daily posting limit: {err}"
            self.halted = self.reason
            return self
        status = next((s for s in limits if s.get("channelId") == self.channel_id),
                      limits[0] if limits else {})
        self.buffer_daily_limit = status.get("limit")
        self.buffer_used_today = int(status.get("scheduled") or 0) + int(status.get("sent") or 0)
        if status.get("isAtLimit"):
            self.reason = (f"Buffer reports the channel is already at its daily limit "
                           f"({self.buffer_used_today}/{self.buffer_daily_limit})")
            return self
        if self.buffer_daily_limit is None:
            self.reason = ("Buffer reported no daily limit number for this channel, so "
                           "there is no discovered ceiling to respect and nothing is sent")
            return self
        self.headroom = max(0, int(self.buffer_daily_limit) - self.buffer_used_today)
        if self.policy_daily_limit is not None:
            # Two ceilings, and the lower one governs. Buffer's is the account's
            # hard cap; the policy's is what this network has decided to send.
            self.headroom = min(self.headroom, int(self.policy_daily_limit))
        if self.headroom <= 0:
            self.reason = (f"no headroom left today: Buffer allows "
                           f"{self.buffer_daily_limit} and "
                           f"{self.buffer_used_today} are already used")
            return self
        self.available = True
        self.reason = (f"ready: Buffer channel {self.channel.get('name')!r} "
                       f"({self.channel_id}), {self.headroom} post(s) of headroom")
        return self

    # -- the two rules -----------------------------------------------------
    def remaining(self):
        """Headroom minus ATTEMPTS. Never minus successes."""
        if self.halted or not self.available:
            return 0
        return max(0, self.headroom - self.attempts)

    def create_post(self, text, due_at=None, mode=DEFAULT_MODE,
                    scheduling_type=DEFAULT_SCHEDULING_TYPE):
        """Put one post in the Buffer queue. Raises BufferError on any refusal.

        Queued, not published: Buffer sends it at the channel's next posting
        slot. The caller records that distinction rather than calling it posted.
        """
        if self.halted:
            raise BufferError(f"route already halted this run: {self.halted}",
                              kind="halted")
        if not self.available:
            raise BufferError(f"route not available: {self.reason}",
                              kind="unavailable")
        if self.remaining() <= 0:
            raise BufferError(
                f"the discovered Buffer allowance for today is spent "
                f"({self.attempts} attempt(s) against {self.headroom})",
                kind="limit_spent")
        payload = {"channelId": self.channel_id, "text": text, "assets": [],
                   "needsApproval": False, "mode": mode,
                   "schedulingType": scheduling_type,
                   "source": "authority-backlink-network"}
        if due_at:
            payload["dueAt"] = due_at
        # Spent BEFORE the call. This is the whole fix for the 581-request run.
        self.attempts += 1
        try:
            payload_out = graphql(CREATE_POST, {"input": payload}, opener=self.opener)
        except BufferError as err:
            self.halted = f"buffer_transport_refusal: {err}"
            raise
        result = payload_out.get("createPost") or {}
        kind = result.get("__typename")
        if kind != SUCCESS_TYPE:
            message = _redact(result.get("message") or kind or "unknown refusal")
            self.halted = f"buffer_refused ({kind}): {message}"
            raise BufferError(self.halted, kind=str(kind))
        post = result.get("post") or {}
        self.accepted += 1
        return {
            "ok": True,
            "id": post.get("id", ""),
            "buffer_status": post.get("status"),
            "due_at": post.get("dueAt"),
            "channel_id": post.get("channelId") or self.channel_id,
        }

    def receipt(self):
        return {
            "available": self.available,
            "reason": self.reason,
            "halted": self.halted,
            "organization_id": self.organization_id,
            "channel_id": self.channel_id,
            "channel_name": (self.channel or {}).get("name"),
            "channel_service": (self.channel or {}).get("service"),
            "buffer_daily_limit_discovered": self.buffer_daily_limit,
            "buffer_used_today": self.buffer_used_today,
            "policy_daily_limit": self.policy_daily_limit,
            "headroom_at_open": self.headroom,
            "attempts": self.attempts,
            "accepted": self.accepted,
            "remaining": self.remaining(),
            "plan_limits": self.plan_limits,
            "channels_connected": self.channels_seen,
        }
