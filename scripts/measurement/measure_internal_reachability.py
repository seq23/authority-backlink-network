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
import os, re, html, json, collections

ROOT = '/Users/sequoiataylor/GitHub/authority-backlink-network/sites'
PUBS = {
    'founder-operator': 'founderoperatorlibrary.com',
    'memphis-local': 'memphisvendorlibrary.com',
    'professional-resources': 'professionalresourcelibrary.com',
}
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

json.dump(out, open('/private/tmp/claude-501/-Users-sequoiataylor/f3ec99dc-fe58-442f-9c3f-73876fa39d72/scratchpad/linkgraph.json', 'w'), indent=2)
