#!/usr/bin/env python3
"""Ask Buffer what this token can actually do, and prove it before wiring it.

Read-only by default: it introspects the schema, lists the connected channels,
and reads the channel's own daily posting limit. `--schedule-test` is the ONE
deliberate write, behind an explicit flag and an explicit channel id, because a
delivery route proved only with stubs is a route that has never worked.

Nothing here prints the token: every response passes through the redactor in
scripts/lib/buffer_route.py, and the schedule test prints only the ids Buffer
returns.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from lib import buffer_route  # noqa: E402

# Seven levels of ofType. GraphQL introspection cannot recurse, and a shallower
# chain renders `[DailyPostingLimit!]!` as `[?!]!` -- which is how a type this
# route depends on stays anonymous through a whole probe run.
TYPE_REF = "kind name " + " ".join(["ofType {"] * 6) + " kind name " + "}" * 6

TYPE_QUERY = """
query T($name: String!) {
  __type(name: $name) {
    name kind
    inputFields { name type { %(ref)s } defaultValue }
    fields { name args { name type { %(ref)s } } type { %(ref)s } }
    enumValues { name }
    possibleTypes { name }
  }
}
""" % {"ref": TYPE_REF}

ROOT_FIELDS = """
query R {
  __schema {
    queryType { fields { name args { name type { %(ref)s } } type { %(ref)s } } }
    mutationType { fields { name args { name type { %(ref)s } } type { %(ref)s } } }
  }
}
""" % {"ref": TYPE_REF}


def unwrap(t):
    if not t:
        return "?"
    if t.get("kind") == "NON_NULL":
        return unwrap(t.get("ofType")) + "!"
    if t.get("kind") == "LIST":
        return "[" + unwrap(t.get("ofType")) + "]"
    return t.get("name") or unwrap(t.get("ofType"))


def base_name(t):
    """The named type at the bottom of any list/non-null wrapping."""
    while t and not t.get("name"):
        t = t.get("ofType")
    return (t or {}).get("name")


def field_line(f):
    args = ", ".join(f"{a['name']}: {unwrap(a['type'])}" for a in f.get("args") or [])
    if args:
        return f"{f['name']}({args}): {unwrap(f.get('type'))}"
    return f"{f['name']}: {unwrap(f.get('type'))}"


def describe_type(name, out):
    if not name or name in out:
        return out.get(name)
    try:
        data = buffer_route.graphql(TYPE_QUERY, {"name": name})
    except buffer_route.BufferError as err:
        out[name] = {"error": str(err)[:300]}
        return out[name]
    t = data.get("__type")
    if not t:
        out[name] = {"error": "no such type"}
        return out[name]
    out[name] = {
        "kind": t.get("kind"),
        "inputFields": [f"{f['name']}: {unwrap(f['type'])}"
                        + (f" = {f['defaultValue']}" if f.get("defaultValue") else "")
                        for f in (t.get("inputFields") or [])],
        "fields": [field_line(f) for f in (t.get("fields") or [])],
        "enumValues": [e["name"] for e in (t.get("enumValues") or [])],
        "possibleTypes": [p["name"] for p in (t.get("possibleTypes") or [])],
    }
    return out[name]


def try_query(label, query, variables, out):
    try:
        out[label] = {"ok": True, "data": buffer_route.graphql(query, variables)}
    except buffer_route.BufferError as err:
        out[label] = {"ok": False, "error": str(err)[:800]}
    return out[label]


def main(argv=None):  # noqa: C901 - a probe is a list of questions
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--type", action="append", default=[])
    ap.add_argument("--schedule-test", metavar="TEXT", default=None,
                    help="THE one write: schedule this text into the channel's queue.")
    ap.add_argument("--channel-id", default=None)
    ap.add_argument("--scheduling-type", default="automatic")
    ap.add_argument("--auth-check", action="store_true",
                    help="Call createPost against a channel id that does not exist. "
                         "Creates nothing; separates 'the token may not post' from "
                         "'there is no channel to post to'.")
    ap.add_argument("--share-mode", default="addToQueue")
    ap.add_argument("--queue-depth", action="store_true",
                    help="Count the posts already occupying a scheduled slot. The free "
                         "plan caps that standing depth, not just a daily rate.")
    args = ap.parse_args(argv)

    report = {"endpoint": buffer_route.ENDPOINT, "token_present": buffer_route.has_token()}
    if not buffer_route.has_token():
        report["stop"] = f"{buffer_route.TOKEN_ENV} is absent; nothing could be asked."
        print(json.dumps(report, indent=2))
        return 1

    live, types = {}, {}
    report["live"], report["types"] = live, types

    # ---- schema shape, and the named types this route actually depends on
    wanted = set(args.type)
    try:
        schema = buffer_route.graphql(ROOT_FIELDS)["__schema"]
        report["query_fields"] = sorted(field_line(f) for f in schema["queryType"]["fields"])
        report["mutation_fields"] = sorted(field_line(f) for f in schema["mutationType"]["fields"])
        for f in schema["queryType"]["fields"] + schema["mutationType"]["fields"]:
            if f["name"] in ("channels", "dailyPostingLimits", "createPost", "posts"):
                wanted.add(base_name(f["type"]))
                wanted.update(base_name(a["type"]) for a in f.get("args") or [])
    except buffer_route.BufferError as err:
        report["schema_error"] = str(err)

    for name in ["PostsInput", "PostsFilter", "PostsFiltersInput", "PostConnection",
                 "PostEdge", "ChannelsInput", "ChannelsFiltersInput", "DailyPostingLimitsInput",
                 "CreatePostInput", "ShareMode", "SchedulingType", "Service",
                 "ChannelType", "PostActionPayload", "DailyPostingLimitStatus",
                 "OrganizationLimits", "Post", "PostStatus",
                 *sorted(n for n in wanted if n)]:
        described = describe_type(name, types)
        # Union payloads hide the real shapes behind possibleTypes; a route that
        # cannot read the error branch cannot tell a refusal from a success.
        for member in (described or {}).get("possibleTypes") or []:
            describe_type(member, types)

    # ---- what is actually connected
    acct = try_query("account",
                     "query { account { id email organizations { id name } } }", None, live)
    org_ids = []
    if acct.get("ok"):
        org_ids = [o["id"] for o in acct["data"]["account"].get("organizations") or []]
    report["organization_ids"] = org_ids

    channels = []
    for org in org_ids:
        res = try_query(f"channels[{org}]", """
            query C($input: ChannelsInput!) {
              channels(input: $input) {
                id name service serviceId type organizationId timezone
                isDisconnected isLocked isQueuePaused scopes
              }
            }""", {"input": {"organizationId": org}}, live)
        if res.get("ok"):
            channels.extend(res["data"]["channels"])
    report["channels"] = [{k: c.get(k) for k in
                           ("id", "name", "service", "type", "isDisconnected",
                            "isLocked", "isQueuePaused", "timezone")} for c in channels]
    x_channels = [c for c in channels
                  if str(c.get("service", "")).lower() in ("twitter", "x")]
    report["x_channel_ids"] = [c["id"] for c in x_channels]

    # ---- what the plan itself allows
    for org in org_ids:
        try_query(f"organization_limits[{org}]", """
            query O { account { organizations { id name channelCount
              limits { %s } } } }""" % " ".join(
                  f.split(":")[0] for f in
                  (types.get("OrganizationLimits") or {}).get("fields") or []) or "__typename",
            None, live)
        break

    # ---- the real ceiling, read from Buffer rather than guessed
    if channels:
        limit_fields = " ".join(f.split(":")[0] for f in
                                (types.get("DailyPostingLimitStatus") or {}).get("fields") or [])
        try_query("dailyPostingLimits", """
            query L($input: DailyPostingLimitsInput!) {
              dailyPostingLimits(input: $input) { %s }
            }""" % (limit_fields or "__typename"),
            {"input": {"channelIds": [c["id"] for c in channels]}}, live)

    # ---- the STANDING queue depth: how many posts already occupy a slot.
    # The free plan's OrganizationLimits.scheduledPosts is not a daily rate, it
    # is a cap on how many posts may sit queued AT ONCE -- note the siblings
    # scheduledStoriesPerChannel and scheduledThreadsPerChannel name their scope
    # and this one does not. Counting what is already queued is the only way to
    # respect it, so the shape of the `posts` query has to be known exactly.
    if args.queue_depth:
        for org in org_ids:
            for status in ("scheduled", "draft", "needs_approval", "sending", "sent"):
                try_query(f"posts[{status}]", """
                    query P($input: PostsInput!, $first: Int) {
                      posts(input: $input, first: $first) {
                        edges { node { id status channelId dueAt createdAt } }
                        pageInfo { hasNextPage endCursor }
                        totalCount
                      }
                    }""",
                    {"input": {"organizationId": org, "status": [status]}, "first": 50},
                    live)
            break

    if args.auth_check:
        # A channel id that cannot exist. If the token were unable to post at
        # all this answers UnauthorizedError; if it may post it answers
        # NotFoundError. Either way nothing is created.
        try_query("mutation_authorization", """
            mutation A($input: CreatePostInput!) {
              createPost(input: $input) {
                __typename
                ... on PostActionSuccess { post { id } }
                ... on NotFoundError { message }
                ... on UnauthorizedError { message }
                ... on InvalidInputError { message }
                ... on LimitReachedError { message }
                ... on RestProxyError { code message }
                ... on UnexpectedError { message }
              }
            }""",
            {"input": {"channelId": "000000000000000000000000",
                       "text": "authorization probe, never created",
                       "assets": [], "needsApproval": False,
                       "mode": "addToQueue", "schedulingType": "automatic"}},
            live)

    if args.schedule_test:
        channel_id = args.channel_id or (x_channels[0]["id"] if x_channels else None)
        if not channel_id:
            report["schedule_test"] = {"ok": False, "error": "no X channel to post to"}
        else:
            report["schedule_test_channel"] = channel_id
            try_query("schedule_test", """
                mutation S($input: CreatePostInput!) {
                  createPost(input: $input) {
                    __typename
                    ... on PostActionSuccess { post { id status dueAt channelId text } }
                    ... on NotFoundError { message }
                    ... on UnauthorizedError { message }
                    ... on InvalidInputError { message }
                    ... on LimitReachedError { message }
                    ... on RestProxyError { code message }
                    ... on UnexpectedError { message }
                  }
                }""",
                {"input": {"channelId": channel_id, "text": args.schedule_test,
                           "assets": [], "needsApproval": False,
                           "mode": args.share_mode,
                           "schedulingType": args.scheduling_type}},
                report)

    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
