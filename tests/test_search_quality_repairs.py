"""Repairs survive generation; consolidation never removes a URL without a 301."""
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from lib import search_quality as q
from lib import page_composer as pc

config = json.loads((ROOT / 'data/search-quality-repairs.json').read_text())
assert config['answers'] and config['guides']
for topic, answer in config['answers'].items():
    source = '<h1>Task</h1><p class="dek">Scope only</p><p class="recommendation-summary__answer">Scope</p><a href="https://example.org/source">Source</a>'
    actual = q.repair_text(source, answer)
    assert 'Scope only' not in actual and 'https://example.org/source' in actual
    assert q.repair_text(actual, answer) == actual
assert q.FILLER not in q.repair_text('<li>Specific error.' + q.FILLER + '</li>')

real_root, real_pubs = q.ROOT, pc.publications
with tempfile.TemporaryDirectory() as tmp:
    q.ROOT = Path(tmp)
    (q.ROOT / 'data').mkdir()
    (q.ROOT / 'data/search-quality-repairs.json').write_text(json.dumps(config))
    pubs = [{'folder': g['folder']} for g in config['guides'].values()]
    pc.publications = lambda: pubs
    for topic, guide in config['guides'].items():
        folder = q.ROOT / guide['folder']
        (folder / 'daily').mkdir(parents=True)
        (folder / 'daily/old.html').write_text('<tr><td>Topic</td><td>' + topic + '</td></tr>')
    try:
        q.apply()
        for guide in config['guides'].values():
            folder = q.ROOT / guide['folder']
            assert not (folder / 'daily/old.html').exists()
            rules = (folder / '_redirects').read_text()
            assert '/daily/old /topics/' + guide['hub'] + ' 301' in rules
            # An old generator recreates the retired URL: the same stage
            # removes it again with its redirect and ledger intact.
            (folder / 'daily/old.html').write_text('recreated')
        q.apply()
        for guide in config['guides'].values():
            assert not (q.ROOT / guide['folder'] / 'daily/old.html').exists()
        assert len(json.loads((q.ROOT / 'data/consolidation-ledger.json').read_text())) == 2
    finally:
        q.ROOT, pc.publications = real_root, real_pubs
print('PASS: topic answers preserve citations; consolidated URLs retain 301s after regeneration')
