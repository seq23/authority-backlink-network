"""
Independent internal-reachability measurement.

Two committed artifacts disagree about professionalresourcelibrary.com:
  authority-backlink-network/reports/click-depth.json : 419 pages, 0 orphans,
      max depth 2, depth histogram {0:1, 1:41, 2:377}
  local-guides-citation-velocity/data/signals/bing_webmaster_baseline.json :
      387 pages, 377 orphans

377 appears in both, once as "pages at depth 2" and once as "orphans". This
rebuilds the graph from the rendered HTML and decides which reading is right.

An orphan here means: no other page in the publication links to it. That is the
definition that matters for crawl discovery, and it is stricter than "not
reachable from the homepage in N hops".
"""
import argparse, os, re, html, json, collections

# Resolved from this file, never from an absolute path. The earlier hard-coded
# /Users/.../GitHub/authority-backlink-network/sites meant a run from a worktree
# silently measured the canonical checkout instead of the tree in hand, and the
# result was written into a scratch directory belonging to a session that no
# longer exists, so the script crashed after printing the numbers.
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_SITES = os.path.join(REPO, 'sites')
DEFAULT_OUT = os.path.join(REPO, 'reports/citation-measurement/internal-reachability.json')

# Publication folder -> the host it is served on. Read from data/publications.json
# so a fourth publication does not have to be remembered here.
def publications(repo):
    path = os.path.join(repo, 'data/publications.json')
    pubs = {}
    for entry in json.load(open(path, encoding='utf-8')):
        folder = entry['folder'].rstrip('/').split('/')[-1]
        raw = entry.get('working_domain') or entry.get('domain') or entry.get('base_url') or ''
        host = re.sub(r'^https?://(?:www\.)?', '', raw).strip('/')
        if host:
            pubs[folder] = host.lower()
    return pubs


ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--sites', default=DEFAULT_SITES)
ap.add_argument('--out', default=DEFAULT_OUT)
args = ap.parse_args()
ROOT = args.sites
PUBS = publications(REPO)
HREF = re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\']', re.I)


def canon(pub_dir, url, host):
    """Map any internal href to a repo-relative page key."""
    u = url.split('#')[0].split('?')[0]
    if u.startswith('http://') or u.startswith('https://'):
        m = re.match(r'https?://(?:www\.)?([^/]+)(/.*)?$', u)
        if not m or m.group(1).lower() != host:
            return None
        path = m.group(2) or '/'
    elif u.startswith('/'):
        path = u
    else:
        return None
    if path.endswith('/'):
        path += 'index.html'
    if not path.endswith('.html'):
        path += '.html'
    return os.path.normpath(path.lstrip('/'))


out = {}
for pub_dir, host in PUBS.items():
    base = os.path.join(ROOT, pub_dir)
    pages = set()
    for dp, _d, fs in os.walk(base):
        for f in fs:
            if f.endswith('.html'):
                pages.add(os.path.relpath(os.path.join(dp, f), base))

    inbound = collections.defaultdict(set)
    edges = collections.defaultdict(set)
    for p in pages:
        raw = open(os.path.join(base, p), encoding='utf-8', errors='replace').read()
        for href in HREF.findall(raw):
            t = canon(base, html.unescape(href), host)
            if t and t in pages and t != p:
                edges[p].add(t)
                inbound[t].add(p)

    # 404 is not a content page and is never linked; exclude from both counts.
    content = {p for p in pages if p != '404.html'}

    # BFS from the homepage.
    depth = {'index.html': 0}
    q = collections.deque(['index.html'])
    while q:
        cur = q.popleft()
        for nxt in edges[cur]:
            if nxt not in depth:
                depth[nxt] = depth[cur] + 1
                q.append(nxt)

    orphans = sorted(p for p in content if not inbound[p] and p != 'index.html')
    unreachable = sorted(p for p in content if p not in depth)
    hist = collections.Counter(depth[p] for p in content if p in depth)

    out[host] = {
        'pages': len(content),
        'orphans_no_inbound_link': len(orphans),
        'unreachable_from_homepage': len(unreachable),
        'depth_histogram': dict(sorted(hist.items())),
        'max_depth': max(hist) if hist else None,
        'median_inbound_links': sorted(len(inbound[p]) for p in content)[len(content)//2],
        'orphan_sample': orphans[:5],
        'unreachable_sample': unreachable[:5],
    }
    print(host)
    print('   pages                      %d' % len(content))
    print('   orphans (no inbound link)  %d' % len(orphans))
    print('   unreachable from homepage  %d' % len(unreachable))
    print('   depth histogram            %s' % dict(sorted(hist.items())))
    print('   median inbound links/page  %d' % out[host]['median_inbound_links'])

os.makedirs(os.path.dirname(args.out), exist_ok=True)
with open(args.out, 'w', encoding='utf-8') as fh:
    json.dump(out, fh, indent=2)
    fh.write('\n')
print('wrote %s' % os.path.relpath(args.out, REPO))
