#!/usr/bin/env python3
"""Ask Buffer what this token can actually do, and prove it before wiring it.

Read-only by default. `--schedule-test` is the ONE deliberate write, guarded by
an explicit flag and an explicit text argument, because a delivery route proved
only with stubs is a route that has never worked.

Nothing here prints the token: every response goes through the redactor in
scripts/lib/buffer_route.py.
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

TYPE_QUERY = """
query T($name: String!) {
  __type(name: $name) {
    name kind
    inputFields { name description type { kind name ofType { kind name ofType { kind name } } } }
    fields { name args { name type { kind name ofType { kind name } } }
             type { kind name ofType { kind name ofType { kind name } } } }
    enumValues { name }
  }
}
"""

ROOT_FIELDS = """
query R {
  __schema {
    queryType { fields { name args { name type { kind name ofType { kind name ofType { kind name } } } }
                        type { kind name ofType { kind name ofType { kind name } } } } }
    mutationType { fields { name args { name type { kind name ofType { kind name ofType { kind name } } } }
                            type { kind name ofType { kind name ofType { kind name } } } } }
  }
}
"""


def unwrap(t):
    """Render a GraphQL type reference as a readable string."""
    if not t:
        return "?"
    if t.get("kind") == "NON_NULL":
        return unwrap(t.get("ofType")) + "!"
    if t.get("kind") == "LIST":
        return "[" + unwrap(t.get("ofType")) + "]"
    return t.get("name") or unwrap(t.get("ofType"))


def field_line(f):
    args = ", ".join(f"{a['name']}: {unwrap(a['type'])}" for a in f.get("args") or [])
    if args:
        return f"{f['name']}({args}): {unwrap(f.get('type'))}"
    return f"{f['name']}: {unwrap(f.get('type'))}"


def describe_type(name, out):
    try:
        data = buffer_route.graphql(TYPE_QUERY, {"name": name})
    except buffer_route.BufferError as err:
        out[name] = {"error": str(err)}
        return
    t = data.get("__type")
    if not t:
        out[name] = {"error": "no such type"}
        return
    out[name] = {
        "kind": t.get("kind"),
        "inputFields": [f"{f['name']}: {unwrap(f['type'])}"
                        for f in (t.get("inputFields") or [])],
        "fields": [field_line(f) for f in (t.get("fields") or [])],
        "enumValues": [e["name"] for e in (t.get("enumValues") or [])],
    }


def try_query(label, query, variables, out):
    try:
        out[label] = {"ok": True, "data": buffer_route.graphql(query, variables)}
    except buffer_route.BufferError as err:
        out[label] = {"ok": False, "error": str(err)[:600]}
    return out[label]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--type", action="append", default=[],
                    help="Extra type name to introspect.")
    ap.add_argument("--channels-input", default=None,
                    help="JSON for the channels(input:) argument, to test a shape.")
    ap.add_argument("--schedule-test", metavar="TEXT", default=None,
                    help="THE one write: schedule this text to the X channel.")
    ap.add_argument("--channel-id", default=None, help="Channel id for --schedule-test.")
    args = ap.parse_args(argv)

    report = {"endpoint": buffer_route.ENDPOINT, "token_present": buffer_route.has_token()}
    if not buffer_route.has_token():
        report["stop"] = (f"{buffer_route.TOKEN_ENV} is absent from this environment, so "
                          f"nothing could be asked of Buffer.")
        print(json.dumps(report, indent=2))
        return 1

    live = {}
    report["live"] = live
    try_query("account", "query { account { id email } }", None, live)

    types = {}
    report["types"] = types
    try:
        data = buffer_route.graphql(ROOT_FIELDS)
        schema = data["__schema"]
        report["query_fields"] = sorted(field_line(f) for f in schema["queryType"]["fields"])
        report["mutation_fields"] = sorted(
            field_line(f) for f in schema["mutationType"]["fields"])
    except buffer_route.BufferError as err:
        report["schema_error"] = str(err)

    for name in ["ChannelsInput", "Channel", "DailyPostingLimitsInput",
                 "DailyPostingLimit", "CreatePostInput", "Account",
                 "Organization", *args.type]:
        describe_type(name, types)

    if args.channels_input is not None:
        try_query("channels",
                  "query C($input: ChannelsInput!) { channels(input: $input) "
                  "{ id name service serviceId type organizationId } }",
                  {"input": json.loads(args.channels_input)}, live)

    if args.schedule_test:
        if not args.channel_id:
            report["schedule_test"] = {"ok": False,
                                       "error": "--channel-id is required for a write"}
        else:
            try_query("schedule_test", """
                mutation S($input: CreatePostInput!) {
                  createPost(input: $input) {
                    __typename
                    ... on PostCreated { post { id status dueAt channelId text } }
                    ... on CreatePostError { message userFriendlyMessage }
                  }
                }
            """, {"input": {"channelIds": [args.channel_id], "text": args.schedule_test}},
                report)

    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
