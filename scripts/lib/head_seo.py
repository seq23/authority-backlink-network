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
company (byline.entity_for) as publisher, with Spry Labs as its parent. No node
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


def publisher_node(entity: str, parent: str, domain: str, pub_title: str) -> dict:
    node = {"@type": "Organization", "@id": publisher_id(domain), "name": entity,
            "description": f"The editorial company that writes, edits and publishes {pub_title}."}
    if parent:
        node["parentOrganization"] = {"@type": "Organization", "name": parent}
    return node


def definition_text(pub: dict, entity: str, subsidiary: str) -> str:
    """The homepage answer: '<Publication> is ...', 40-60 words.

    The description is data (data/publications.json `definition`); the closing
    ownership sentence is derived from the same byline helpers as the footer,
    so it names this publication's own editorial company and cannot drift.
    """
    body = (pub.get("definition") or "").strip()
    if not body:
        raise SystemExit(f"data/publications.json: publication '{pub.get('id')}' has no `definition`.")
    return f"{body} It is published by {entity}, its own editorial company{subsidiary}."


def render_block(*, text: str, pub: dict, domain: str, entity: str, parent: str,
                 subsidiary: str, theme_color: str, is_home: bool, is_404: bool,
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
    publisher = publisher_node(entity, parent, domain, pub["title"])
    graph = [{
        "@type": "WebSite", "@id": website_id, "name": pub["title"],
        "url": site_url(domain), "inLanguage": "en-US",
        "publisher": {"@id": publisher["@id"]},
    }, publisher]
    existing = types_on(text)
    if is_home:
        graph.append({
            "@type": "WebPage", "@id": f"{url}#webpage", "url": url, "name": title,
            "description": description, "inLanguage": "en-US",
            "isPartOf": {"@id": website_id}, "publisher": {"@id": publisher["@id"]},
            "speakable": {"@type": "SpeakableSpecification",
                          "cssSelector": [SPEAKABLE_SELECTOR]},
        })
    elif not is_404 and "BreadcrumbList" not in existing:
        h1 = H1_RE.search(text)
        graph.append({"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": pub["title"], "item": site_url(domain)},
            {"@type": "ListItem", "position": 2, "name": plain(h1.group(1)) if h1 else title, "item": url},
        ]})
    ld = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)
    lines.append(f'<script type="application/ld+json" id="{SITE_GRAPH_ID}">{ld}</script>')
    lines.append(BLOCK_END)
    return "\n".join(lines) + "\n"


def install_head(text: str, **kw) -> str:
    """Replace the managed head block (and any legacy copy of its tags)."""
    if not HEAD_END_RE.search(text):
        return text
    text = BLOCK_RE.sub("", text)
    for rx in LEGACY_TAG_RES:
        text = rx.sub("", text)
    if kw.get("is_home"):
        text = install_definition(text, kw["definition"])
    kw.pop("definition", None)
    block = render_block(text=text, **kw)
    return HEAD_END_RE.sub(lambda _m: block + "</head>", text, count=1)


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
    from byline import entity_for, parent_company, subsidiary_clause
    entity = entity_for(pub["title"])
    return {
        "pub": pub, "domain": pub["working_domain"], "entity": entity,
        "parent": parent_company(), "subsidiary": subsidiary_clause(),
        "theme_color": palette((folder / "styles.css").read_text(encoding="utf-8"))["--accent"],
        "rel": rel, "is_home": path == folder / "index.html",
        "is_404": path == folder / "404.html",
        "definition": definition_text(pub, entity, subsidiary_clause()),
    }
