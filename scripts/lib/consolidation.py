"""Reviewed content retirements. Read by generators, sitemap discovery and edge code."""
from __future__ import annotations
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / 'data/page-quality-consolidation.json'

def publications():
    return json.loads(LEDGER.read_text())['publications'] if LEDGER.exists() else {}

def publication(key):
    pubs = publications()
    return pubs.get(key) or next((p for p in pubs.values() if p['folder'].split('/')[-1] == key), {})

def retired(folder, rel):
    return any(p['folder'] == folder and rel in p['retired'] for p in publications().values())

def apply():
    """Remove only reviewed generated daily assets and rewrite references directly."""
    from urllib.parse import urljoin, urlsplit
    import re
    removed = 0
    for pub in publications().values():
        root = ROOT / pub['folder']
        for rel in pub['retired']:
            if not rel.startswith('daily/') or not rel.endswith('.html'):
                raise ValueError('retirement outside generated daily content: ' + rel)
            path = root / rel
            if path.exists():
                path.unlink(); removed += 1
        for path in root.rglob('*.html'):
            source = path.read_text()
            base = 'https://' + pub['domain'] + '/' + path.relative_to(root).as_posix()
            def replace(m):
                url = urlsplit(urljoin(base, m[2]))
                target = pub['redirects'].get(url.path) if url.hostname == pub['domain'] else None
                return m[1] + target + (('?' + url.query) if url.query else '') + (('#' + url.fragment) if url.fragment else '') + m[3] if target else m[0]
            result = re.sub(r'(<a\b[^>]*href=")([^"]+)(")', replace, source)
            if source != result:
                path.write_text(result)
        path = root / '_redirects'
        source = path.read_text() if path.exists() else ''
        source = source.split('# BEGIN page-quality consolidation')[0].rstrip()
        rules = '\n'.join(f'{a} {b} 301' for a,b in sorted(pub['redirects'].items()))
        path.write_text(source + '\n\n# BEGIN page-quality consolidation\n' + rules + '\n')
    registry = ROOT / 'data/link-registry.json'
    rows = json.loads(registry.read_text())
    changed = False
    for row in rows:
        source = row.get('source_path', '')
        pub = next((p for p in publications().values() if source.startswith(p['folder'] + '/')), None)
        if pub and source.removeprefix(pub['folder'] + '/') in pub['retired']:
            row.update(status='consolidated', lifecycle_stage='consolidated', consolidated_on='2026-11-03',
                       consolidated_to=pub['redirects']['/' + source.removeprefix(pub['folder'] + '/').removesuffix('.html')])
            for field in row.get('evidence', {}):
                row['evidence'][field] = False
            changed = True
    if changed:
        registry.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + '\n')
    return removed

def problems(pub, existing):
    """Route invariants; the reviewed kept set is the count floor, with no empty pass."""
    from lib.site_urls import url_path
    errors = []
    kept = set(pub['kept'])
    if not kept or not pub['retired'] or not pub['redirects']:
        errors.append('empty consolidation ledger')
    if not kept <= existing:
        errors.append('missing kept pages')
    if set(pub['retired']) & existing:
        errors.append('retired page recreated')
    final_paths = {'/' + url_path(p) for p in existing}
    for source, destination in pub['redirects'].items():
        if destination in pub['redirects']:
            errors.append('redirect chain: ' + source)
        if destination not in final_paths:
            errors.append('missing redirect destination: ' + destination)
    return errors
