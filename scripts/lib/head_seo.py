"""The <head> a search engine, a social card and an answer engine read.

Measured live on 10 Oct 2026 on all three publication homepages:
  * /favicon.ico answered 404 (only /favicon.svg existed), no apple-touch-icon,
    no web manifest;
  * no og:description, no og:image and no twitter:card on any page, so every
    shared link rendered as a bare URL;
  * the JSON-LD was Article + Organization only: no WebSite node naming the
    publication, no BreadcrumbList on the editorial pages, and nothing on the
    homepage saying in one paragraph what the publication IS.

There is no shared page shell in this repository (see the docstring of
scripts/install_editorial_chrome.py), so this is installed by that script's
last-pass installer on every page every run, the same way the footer is. This
module is the one place the rules live: the installer renders from it and the
validators under scripts/validators/ check the published tree against the same
constants, so the two cannot keep separate lists.

Everything rendered here is idempotent. The whole block sits between two
comment markers and is replaced wholesale, and any legacy icon / og / twitter
tag outside the markers is removed first, so a re-run changes nothing.

Identity: every schema node this adds names the publication's OWN editorial
company (byline.entity_for) as publisher, with no parent organisation. No node
names a person, and no node is shared between publications.
"""
from __future__ import annotations

import html
import json
import re

# ---------------------------------------------------------------- the assets
# Files scripts/build_brand_assets.py writes into every publication root.
FAVICON_ICO = "favicon.ico"
FAVICON_SVG = "favicon.svg"
APPLE_TOUCH_ICON = "apple-touch-icon.png"
MANIFEST = "site.webmanifest"
MANIFEST_ICONS = (("icon-192.png", 192), ("icon-512.png", 512))
OG_IMAGE = "og.png"
OG_WIDTH, OG_HEIGHT = 1200, 630
APPLE_TOUCH_SIZE = 180
ICO_SIZES = (16, 32, 48)

REQUIRED_ASSETS = (FAVICON_ICO, FAVICON_SVG, APPLE_TOUCH_ICON, MANIFEST, OG_IMAGE,
                   *(name for name, _ in MANIFEST_ICONS))

# ----------------------------------------------------------- the head block
BLOCK_START = "<!-- seo:head -->"
BLOCK_END = "<!-- /seo:head -->"
BLOCK_RE = re.compile(re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END) + r"\n?", re.S)
SITE_GRAPH_ID = "site-graph"

# Tags this module owns. Anything matching outside the block is a legacy copy
# (the old single favicon link, or a hand-added og tag) and is removed so the
# page carries exactly one of each.
LEGACY_TAG_RES = (
    re.compile(r'<link\s+rel="(?:icon|shortcut icon|apple-touch-icon|manifest)"[^>]*>\n?', re.I),
    re.compile(r'<meta\s+(?:property|name)="(?:og|twitter):[^"]*"[^>]*>\n?', re.I),
    re.compile(r'<meta\s+name="theme-color"[^>]*>\n?', re.I),
)

# Every page must carry these, each exactly once.
REQUIRED_OG = ("og:title", "og:description", "og:type", "og:url", "og:site_name",
               "og:image", "og:image:width", "og:image:height", "og:image:alt", "og:locale")
REQUIRED_TWITTER = ("twitter:card", "twitter:title", "twitter:description",
                    "twitter:image", "twitter:image:alt")
REQUIRED_ICON_LINKS = (
    ("icon", "/" + FAVICON_ICO),
    ("icon", "/" + FAVICON_SVG),
    ("apple-touch-icon", "/" + APPLE_TOUCH_ICON),
    ("manifest", "/" + MANIFEST),
)

# ------------------------------------------------------- the homepage answer
DEFINITION_ID = "publication-definition"
SPEAKABLE_SELECTOR = "#" + DEFINITION_ID
DEFINITION_MIN_WORDS, DEFINITION_MAX_WORDS = 40, 60
DEFINITION_RE = re.compile(
    r'<p id="' + DEFINITION_ID + r'" class="definition">.*?</p>\n?', re.S)
H1_END_RE = re.compile(r"</h1>\n?", re.I)

BYLINED_TYPES = frozenset({
    "Article", "BlogPosting", "NewsArticle", "TechArticle",
    "ScholarlyArticle", "Report", "AdvertiserContentArticle",
})

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
DESC_RE = re.compile(r'<meta\s+name="description"\s+content="([^"]*)"', re.I)
CANON_RE = re.compile(r'<link\s+rel="canonical"\s+href="([^"]*)"', re.I)
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S | re.I)
HEAD_END_RE = re.compile(r"</head>", re.I)
LDJSON_ANY_RE = re.compile(
    r'<script\s+type="application/ld\+json"[^>]*>(.*?)</script>', re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def plain(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub("", fragment or ""))).strip()


def word_count(text: str) -> int:
    return len(plain(text).split())


def jsonld_nodes(text: str) -> list:
    """Every schema.org node on the page, flattened through @graph and nesting."""
    out = []

    def walk(node):
        if isinstance(node, dict):
            if "@type" in node:
                out.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for raw in LDJSON_ANY_RE.findall(text):
        try:
            walk(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return out


def node_types(node: dict) -> set:
    t = node.get("@type")
    return set(t) if isinstance(t, list) else {t}


def types_on(text: str) -> set:
    found = set()
    for node in jsonld_nodes(text):
        found |= node_types(node)
    return found


def is_article(text: str) -> bool:
    return bool(types_on(text) & BYLINED_TYPES)


def site_url(domain: str) -> str:
    return f"https://{domain}/"


def og_image_url(domain: str) -> str:
    return f"https://{domain}/{OG_IMAGE}"


def publisher_id(domain: str) -> str:
    # The editorial company's node id, the one scripts/build_editorial_pages.py
    # already gives it on the masthead. NOT "/#publisher": the generators use
    # that id for the publication itself, and one id naming two different
    # organisations would merge them in any graph that reads both.
    return f"https://{domain}/masthead#publisher-entity"


# The editorial company's own pages: where it is identified, and the image that
# stands for it. Search Readiness checklist item c1 asks every Organization node
# for name, url, logo and sameAs; on 25 Oct 2026 every page on all three
# publications had name alone.
#
# sameAs is the one that cannot be invented. These publications have no social
# profiles, no Wikipedia entry and no company register page, and schema.org's
# sameAs is "a reference Web page that unambiguously indicates the item's
# identity" -- so it points at the two pages that do exactly that and no
# further: `url` is the masthead, which names the editorial company and its
# policies, and sameAs is contributors, which names who writes under it, and
# about, which says who owns and edits the publication. A LinkedIn URL invented
# to fill the field would be a false claim about an entity on a publication
# whose only asset is being believed.
ORG_URL_PATH = "/masthead"
ORG_SAMEAS_PATHS = ("/contributors", "/about")
ORG_LOGO = "icon-512.png"


def organization_identity(domain: str) -> dict:
    """url, logo and sameAs for the editorial company of `domain`."""
    return {
        "url": f"https://{domain}{ORG_URL_PATH}",
        "logo": f"https://{domain}/{ORG_LOGO}",
        "sameAs": [f"https://{domain}{path}" for path in ORG_SAMEAS_PATHS],
    }


def publisher_node(entity: str, domain: str, pub_title: str) -> dict:
    return {"@type": "Organization", "@id": publisher_id(domain), "name": entity,
            "description": f"The editorial company that writes, edits and publishes {pub_title}.",
            **organization_identity(domain)}


def definition_text(pub: dict, entity: str) -> str:
    """The homepage answer: '<Publication> is ...', 40-60 words.

    The description is data (data/publications.json `definition`); the closing
    ownership sentence is derived from the same byline helpers as the footer,
    so it names this publication's own editorial company and cannot drift.
    """
    body = (pub.get("definition") or "").strip()
    if not body:
        raise SystemExit(f"data/publications.json: publication '{pub.get('id')}' has no `definition`.")
    return f"{body} It is published by {entity}, its own editorial company."


def render_block(*, text: str, pub: dict, domain: str, entity: str,
                 theme_color: str, is_home: bool, is_404: bool,
                 rel: str) -> str:
    title_m, desc_m, canon_m = TITLE_RE.search(text), DESC_RE.search(text), CANON_RE.search(text)
    missing = [n for n, m in (("<title>", title_m), ("meta description", desc_m)) if not m]
    if missing:
        raise SystemExit(f"{rel}: cannot build social tags without {', '.join(missing)}")
    title = plain(title_m.group(1))
    description = html.unescape(desc_m.group(1))
    url = canon_m.group(1) if canon_m else (f"https://{domain}/404.html" if is_404 else None)
    if not url:
        raise SystemExit(f"{rel}: cannot build og:url without a canonical link")
    og_type = "article" if (not is_home and not is_404 and is_article(text)) else "website"
    image = og_image_url(domain)
    alt = f"{pub['title']} -- {domain}"

    lines = [BLOCK_START]
    lines += [
        f'<link rel="icon" href="/{FAVICON_ICO}" sizes="32x32">',
        f'<link rel="icon" href="/{FAVICON_SVG}" type="image/svg+xml">',
        f'<link rel="apple-touch-icon" href="/{APPLE_TOUCH_ICON}">',
        f'<link rel="manifest" href="/{MANIFEST}">',
        f'<meta name="theme-color" content="{esc(theme_color)}">',
    ]
    og = [
        ("og:title", title), ("og:description", description), ("og:type", og_type),
        ("og:url", url), ("og:site_name", pub["title"]), ("og:locale", "en_US"),
        ("og:image", image), ("og:image:width", str(OG_WIDTH)),
        ("og:image:height", str(OG_HEIGHT)), ("og:image:alt", alt),
    ]
    lines += [f'<meta property="{k}" content="{esc(v)}">' for k, v in og]
    tw = [
        ("twitter:card", "summary_large_image"), ("twitter:title", title),
        ("twitter:description", description), ("twitter:image", image),
        ("twitter:image:alt", alt),
    ]
    lines += [f'<meta name="{k}" content="{esc(v)}">' for k, v in tw]

    website_id = f"https://{domain}/#website"
    publisher = publisher_node(entity, domain, pub["title"])
    graph = [{
        "@type": "WebSite", "@id": website_id, "name": pub["title"],
        "url": site_url(domain), "inLanguage": "en-US",
        "publisher": {"@id": publisher["@id"]},
    }, publisher]
    existing = types_on(text)
    # A WebPage node on EVERY page, not only the homepage. Checklist item c2
    # ("WebPage on every page") failed on /about across all three publications,
    # which had the WebSite and the BreadcrumbList but nothing tying the page
    # itself to the site. The homepage's node additionally carries the
    # SpeakableSpecification over its definition paragraph.
    webpage = {
        "@type": "WebPage", "@id": f"{url}#webpage", "url": url, "name": title,
        "description": description, "inLanguage": "en-US",
        "isPartOf": {"@id": website_id}, "publisher": {"@id": publisher["@id"]},
    }
    if is_home:
        webpage["speakable"] = {"@type": "SpeakableSpecification",
                                "cssSelector": [SPEAKABLE_SELECTOR]}
    graph.append(webpage)
    if not is_home and not is_404 and "BreadcrumbList" not in existing:
        h1 = H1_RE.search(text)
        graph.append({"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": pub["title"], "item": site_url(domain)},
            {"@type": "ListItem", "position": 2, "name": plain(h1.group(1)) if h1 else title, "item": url},
        ]})
    ld = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)
    lines.append(f'<script type="application/ld+json" id="{SITE_GRAPH_ID}">{ld}</script>')
    lines.append(BLOCK_END)
    return "\n".join(lines) + "\n"


UPDATED_RE = re.compile(r'<p class="updated"[^>]*>.*?</p>\n?', re.S | re.I)
MAIN_END_RE = re.compile(r"</main>", re.I)
SCRIPT_ANY_RE = re.compile(r"<script\b.*?</script>", re.S | re.I)
BODY_RE = re.compile(r"<body[^>]*>(.*)</body>", re.S | re.I)
ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def schema_dates(text: str) -> list:
    """Every datePublished / dateModified in the page's JSON-LD, as YYYY-MM-DD."""
    out = []
    for node in jsonld_nodes(text):
        for key in ("dateModified", "datePublished"):
            value = node.get(key)
            if isinstance(value, str) and ISO_DATE_RE.match(value):
                out.append(value[:10])
    return out


def visible_text(text: str) -> str:
    body = BODY_RE.search(text)
    return TAG_RE.sub(" ", SCRIPT_ANY_RE.sub(" ", body.group(1) if body else text))


def install_updated_line(text: str) -> str:
    """Show the page's schema date on the page, for pages that do not already.

    Checklist item d4 -- "Published and updated dates visible" -- failed on 32
    pages on 25 Oct 2026: the homepages, every /about and every hand-authored
    hub declared datePublished and dateModified in JSON-LD and showed neither
    anywhere a reader or an answer engine could see it. A date that exists only
    in markup is the freshness claim nobody can check.

    The date is the page's own dateModified (or datePublished), so this states
    what the page already asserts rather than inventing a fresher one -- the
    faked-freshness problem d4 exists to stop. Pages that already show one of
    their schema dates, the daily pages among them, are left byte-identical.
    Idempotent: its own line is replaced, not stacked.
    """
    dates = schema_dates(text)
    if not dates:
        return text
    text = UPDATED_RE.sub("", text)
    if any(d in visible_text(text) for d in dates):
        return text
    if not MAIN_END_RE.search(text):
        return text
    day = dates[0]
    line = (f'<p class="updated meta">Last updated: '
            f'<time datetime="{day}">{day}</time>.</p>\n')
    return MAIN_END_RE.sub(lambda _m: line + "</main>", text, count=1)


def install_organization_identity(text: str, entity: str, pub_title: str, domain: str) -> str:
    """Give url, logo and sameAs to the publication's own Organization nodes.

    Checklist item c1 reads the FIRST Organization node on the page, and on an
    Article page that is the publisher node inside the article's own JSON-LD --
    written by scripts/lib/page_composer.py and four other generators, each
    inlining `{"@type": "Organization", "name": <entity>}` and nothing else. So
    completing publisher_node() in the managed head block was not enough: this
    completes the nodes in the page's own JSON-LD too, wherever they came from,
    which also means a new generator cannot reintroduce a thin one.

    Only nodes naming THIS publication or its editorial company are touched. An
    Organization node for a cited third party is left exactly as it is: filling
    in its url and logo would be this repository asserting identity facts about
    someone else's company.

    Idempotent, and it rewrites a JSON-LD block only when a field is actually
    missing, so pages that are already complete keep their bytes.
    """
    identity = organization_identity(domain)
    ours = {entity.casefold(), pub_title.casefold()}

    def complete(node):
        """True if anything changed in `node` or below it."""
        changed = False
        if isinstance(node, dict):
            if ("Organization" in node_types(node)
                    and str(node.get("name", "")).casefold() in ours):
                for key, value in identity.items():
                    if not node.get(key):
                        node[key] = value
                        changed = True
            for value in node.values():
                changed = complete(value) or changed
        elif isinstance(node, list):
            for value in node:
                changed = complete(value) or changed
        return changed

    out = []
    last = 0
    for m in LDJSON_ANY_RE.finditer(text):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if not complete(data):
            continue
        out.append(text[last:m.start(1)])
        out.append(json.dumps(data, ensure_ascii=False))
        last = m.end(1)
    out.append(text[last:])
    return "".join(out)


def install_head(text: str, **kw) -> str:
    """Replace the managed head block (and any legacy copy of its tags)."""
    if not HEAD_END_RE.search(text):
        return text
    text = BLOCK_RE.sub("", text)
    for rx in LEGACY_TAG_RES:
        text = rx.sub("", text)
    if kw.get("is_home"):
        text = install_definition(text, kw["definition"])
        text = install_home_title(text, kw["pub"])
    kw.pop("definition", None)
    text = install_organization_identity(text, kw["entity"], kw["pub"]["title"], kw["domain"])
    text = install_updated_line(text)
    block = render_block(text=text, **kw)
    return HEAD_END_RE.sub(lambda _m: block + "</head>", text, count=1)


def install_home_title(text: str, pub: dict) -> str:
    """The homepage <title> is rendered from data, never hand-kept.

    11 Oct 2026: the three homepages published "<Publication> | <Publication>".
    og:title, twitter:title and the WebPage `name` are read from this <title>
    by render_block(), so they follow it. The WebSite node keeps the bare
    publication name: that is the site name search engines show.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from meta_description import home_title
    title = esc(home_title(pub))
    if not TITLE_RE.search(text):
        raise SystemExit(f"{pub.get('id')}: homepage has no <title> to replace")
    return TITLE_RE.sub(lambda _m: f"<title>{title}</title>", text, count=1)


def install_definition(text: str, definition: str) -> str:
    text = DEFINITION_RE.sub("", text)
    para = f'<p id="{DEFINITION_ID}" class="definition">{esc(definition)}</p>\n'
    m = H1_END_RE.search(text)
    if not m:
        raise SystemExit("homepage has no <h1> to put the definition under")
    end = m.end()
    sep = "" if m.group(0).endswith("\n") else "\n"
    return text[:end] + sep + para + text[end:]


TOKEN_RE = re.compile(r"(--[a-z-]+):\s*(#[0-9a-fA-F]{6})\b")


def palette(styles_css: str) -> dict:
    """The light-mode design tokens: the FIRST value each token is given.

    Read from the publication's own styles.css so the icons, the social card
    and the theme-color are painted from the same palette the pages use, and
    no second copy of a colour lives in a script.
    """
    out: dict = {}
    for name, value in TOKEN_RE.findall(styles_css):
        out.setdefault(name, value.lower())
    for need in ("--bg", "--ink", "--ink-strong", "--ink-muted", "--accent"):
        if need not in out:
            raise SystemExit(f"styles.css has no {need} token")
    return out


def published_pages(root):
    """(publication, folder, path, rel, text) for every published HTML page.

    The same walk scripts/install_editorial_chrome.py makes, so a validator
    examines exactly the pages the installer writes.
    """
    pubs = json.loads((root / "data/publications.json").read_text(encoding="utf-8"))
    for pub in pubs:
        folder = root / pub["folder"]
        for path in sorted(folder.rglob("*.html")):
            rel = str(path.relative_to(root))
            if "/agency/" in "/" + rel:
                continue
            yield pub, folder, path, rel, path.read_text(encoding="utf-8")


def meta_values(text: str, attr: str, key: str) -> list:
    rx = re.compile(r'<meta\s+' + attr + r'="' + re.escape(key) + r'"\s+content="([^"]*)"', re.I)
    return [html.unescape(v) for v in rx.findall(text)]


def png_size(path) -> tuple:
    """(width, height) from a PNG's IHDR, stdlib only (CI has no Pillow)."""
    with open(path, "rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return (0, 0)
    import struct
    return struct.unpack(">II", head[16:24])


def ico_sizes(path) -> set:
    """{(w, h), ...} from an ICO directory, stdlib only. 0 in an entry means 256."""
    import struct
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < 6:
        return set()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    if reserved != 0 or kind != 1:
        return set()
    out = set()
    for i in range(count):
        entry = data[6 + 16 * i: 22 + 16 * i]
        if len(entry) < 16:
            break
        out.add((entry[0] or 256, entry[1] or 256))
    return out


def head_context(pub: dict, folder, rel: str, path) -> dict:
    """Everything install_head() needs for one page of one publication.

    Shared by scripts/install_editorial_chrome.py (every page) and
    scripts/deterministic_build.py (404.html, which it rebuilds from scratch),
    so the two writers of 404.html render the same head and never fight.
    """
    from byline import entity_for
    entity = entity_for(pub["title"])
    return {
        "pub": pub, "domain": pub["working_domain"], "entity": entity,
        "theme_color": palette((folder / "styles.css").read_text(encoding="utf-8"))["--accent"],
        "rel": rel, "is_home": path == folder / "index.html",
        "is_404": path == folder / "404.html",
        "definition": definition_text(pub, entity),
    }


def install_head_for_path(path, text: str, root=None) -> str:
    """install_head() for a page about to be written to `path`, publication resolved from the path.

    Every script that writes a whole published page calls this immediately before
    the write (scripts/build_site_navigation.py, scripts/build_editorial_pages.py,
    scripts/build_uscis_changelog_page.py, scripts/deterministic_build.py), so no
    ordering of workflow steps can leave a page without the icon / manifest /
    social block. On 13 Oct 2026 the weekly USCIS changelog run went red because
    build_site_navigation.py ran after install_editorial_chrome.py and rewrote 28
    pages with a head that lacked it; the chrome pass was the only installer.

    Returns `text` unchanged for a path outside every publication folder, for an
    /agency/ page (never chromed), and for a fragment with no </head>.
    """
    from pathlib import Path
    path = Path(path).resolve()
    root = Path(root).resolve() if root else Path(__file__).resolve().parents[2]
    pubs = json.loads((root / "data/publications.json").read_text(encoding="utf-8"))
    for pub in pubs:
        folder = (root / pub["folder"]).resolve()
        try:
            path.relative_to(folder)
        except ValueError:
            continue
        rel = str(path.relative_to(root))
        if "/agency/" in "/" + rel or not HEAD_END_RE.search(text):
            return text
        return install_head(text, **head_context(pub, folder, rel, path))
    return text
