"""Apply source-backed quality repairs without overwriting enriched page bodies.

Called by the existing meta synchronization stage after generation. The ledger
makes consolidation permanent even if an older generator recreates a route.
"""
from __future__ import annotations
import html
import json
import re
from pathlib import Path
from lib import page_composer as pc
from lib.text_io import write_lf

ROOT = Path(__file__).resolve().parents[2]
FILLER = ' A better response is to slow down, verify the missing fact, and record the decision boundary.'


def repair_text(text: str, answer: str | None = None, about: str | None = None) -> str:
    text = text.replace(FILLER, '')
    if answer:
        # Keep later citations, products, navigation and schema; only the
        # scope-only answer slots are owned by this repair.
        text = re.sub(r'(<p class="dek">).*?(</p>)',
                      lambda m: m[1] + html.escape(answer) + m[2], text, count=1, flags=re.S)
        text = re.sub(r'(<p class="recommendation-summary__answer">).*?(</p>)',
                      lambda m: m[1] + html.escape(answer.split('. ')[0] + '.') + m[2],
                      text, count=1, flags=re.S)
    if about:
        tail = text.find('</h1>')
        if tail >= 0:
            text = text[:tail] + re.sub(r'(<p[^>]*>).*?(</p>)',
                lambda m: m[1] + html.escape(about) + m[2], text[tail:], count=1, flags=re.S)
    return text


def apply() -> int:
    config = json.loads((ROOT / 'data/search-quality-repairs.json').read_text())
    ledger_path = ROOT / 'data/consolidation-ledger.json'
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else []
    routes = {(r['folder'], r['from']): r for r in ledger}
    changed = 0
    for pub in pc.publications():
        folder = pub['folder']
        root = ROOT / folder
        for path in sorted(root.rglob('*.html')):
            text = path.read_text()
            rel = path.relative_to(root).as_posix()
            # Read the topic the daily template records, not a slug resemblance.
            match = re.search(r'<tr><td>Topic</td><td>([^<]*)</td></tr>', text)
            cluster = html.unescape(match[1]).lower() if match else None
            guide = config['guides'].get(cluster)
            route = '/' + rel.removesuffix('.html')
            if guide and guide['folder'] == folder:
                routes[(folder, route)] = {'folder':folder, 'from':route,
                    'to':'/topics/' + guide['hub'], 'status':301, 'date':config['updated'],
                    'reason':'Same topic and selection task; useful planning guidance moved to the hub.'}
            if (folder, route) in routes:
                continue
            about = config.get('about', {}).get(folder) if rel == 'about.html' else None
            updated = repair_text(text, config['answers'].get(cluster), about)
            for full, short in config.get('category_summaries', {}).items():
                updated = updated.replace(full, short)
            if updated != text:
                write_lf(path, updated)
                changed += 1
        # Install every redirect before removing its generated file. Re-running
        # also removes routes recreated by another source generator.
        rows = [v for (f, _), v in sorted(routes.items()) if f == folder]
        redirects = root / '_redirects'
        original = redirects.read_text() if redirects.exists() else ''
        cleaned = re.sub(r'\n# BEGIN quality consolidation.*?# END quality consolidation\n?', '', original, flags=re.S)
        block = '\n# BEGIN quality consolidation\n' + ''.join(
            f"{r['from']} {r['to']} 301\n{r['from']}.html {r['to']} 301\n{r['from']}/ {r['to']} 301\n" for r in rows) + '# END quality consolidation\n'
        if rows:
            write_lf(redirects, cleaned.rstrip() + '\n' + block)
        for row in rows:
            path = root / (row['from'].lstrip('/') + '.html')
            if path.exists():
                path.unlink()
                changed += 1
    # Retired destinations in generated navigation must be rebuilt, not treated
    # as off-site citations by the navigation preservation guard.
    for pub in pc.publications():
        retired = {r['from'] for (folder, _), r in routes.items() if folder == pub['folder']}
        for path in (ROOT / pub['folder']).rglob('*.html'):
            text = path.read_text()
            def keep_or_rebuild(match):
                return '' if any(route in match[0] for route in retired) else match[0]
            updated = re.sub(r'<(nav|section|script)\b[^>]*\sdata-nav="[^"]*"[^>]*>[\s\S]*?</\1>',
                             keep_or_rebuild, text, flags=re.I)
            if updated != text:
                write_lf(path, updated)
    registry_path = ROOT / 'data/link-registry.json'
    if registry_path.exists():
        registry = json.loads(registry_path.read_text())
        old_sources = {r['folder'] + r['from'] + '.html': r for r in routes.values()}
        additions = []
        for placement in registry:
            old = placement.get('consolidated_from') or placement.get('source_path')
            if old in old_sources:
                row = old_sources[old]
                destination = row['folder'] + row['to'] + '.html'
                placement.setdefault('pre_consolidation_status', placement.get('status'))
                placement['source_path'] = old
                placement['consolidated_to'] = destination
                placement['status'] = 'consolidated'
                placement['lifecycle_stage'] = 'consolidated'
                placement['evidence'] = {k: False for k in placement.get('evidence', {})}
                if placement['pre_consolidation_status'] == 'published' and not any(x.get('source_path') == destination and x.get('target_url') == placement.get('target_url')
                           for x in registry + additions):
                    moved = dict(placement)
                    for key in ('scheduled_content_date', 'consolidated_from', 'consolidated_to'):
                        moved.pop(key, None)
                    moved.update(source_path=destination, status='published',
                                 lifecycle_stage='published_in_repository', date=config['updated'],
                                 evidence={'repository_rendered': True})
                    additions.append(moved)
        registry.extend(additions)
        write_lf(registry_path, json.dumps(registry, indent=2) + '\n')
    write_lf(ledger_path, json.dumps(list(routes.values()), indent=2) + '\n')
    return changed
