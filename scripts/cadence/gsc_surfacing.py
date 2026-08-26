#!/usr/bin/env python3
"""Emit pages-surfacing-per-month for each property, as JSON.

Reads the last three 30-day windows from Search Console. Used by
publish_headroom.mjs to decide whether more volume is being absorbed.
"""
import json, os, sys, datetime as dt
from google.oauth2 import service_account
from googleapiclient.discovery import build

raw = os.environ.get("GSC_SERVICE_ACCOUNT_JSON", "")
info = json.load(open(raw)) if os.path.exists(raw) else json.loads(raw)
creds = service_account.Credentials.from_service_account_info(
    info, scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)

end = dt.date.today()
out = {}
for site in sys.argv[1:]:
    months = []
    for m in range(3, 0, -1):
        s = end - dt.timedelta(days=30 * m)
        e = end - dt.timedelta(days=30 * (m - 1))
        rows = svc.searchanalytics().query(siteUrl=site, body={
            "startDate": s.isoformat(), "endDate": e.isoformat(),
            "dimensions": ["page"], "rowLimit": 25000}).execute().get("rows", [])
        months.append(len(rows))
    out[site] = months
print(json.dumps(out))
