#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
paths=[ROOT/'data/brands.json',ROOT/'data/publications.json',ROOT/'data/network-rules.json',ROOT/'data/social-brand-policy.json',ROOT/'data/city-publications.json',ROOT/'content-bank/yearly-pantry.json',ROOT/'content-bank/scaling-policy.json',ROOT/'validation/plan.json',ROOT/'data/brand-growth-profiles.json',ROOT/'data/product-repo-manifests.json',ROOT/'data/citation-topic-map.json',ROOT/'data/portfolio-backlink-campaigns.json',ROOT/'data/backlink-seed-articles.json',ROOT/'data/backlink-quality-audit.json',ROOT/'data/portfolio-campaign-health.json',ROOT/'data/distribution/provider-receipt.json',ROOT/'data/distribution/observation-feedback.json',ROOT/'data/distribution/distribution-contract.json',ROOT/'data/backlink-lifecycle-contract.json']
for path in paths:
    json.loads(path.read_text(encoding='utf-8'))
print(json.dumps({'status':'PASS','files':len(paths)}))
