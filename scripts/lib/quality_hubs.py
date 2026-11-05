"""Render consolidated topic collections from reviewed, topic-specific copy."""
import html
import json
from pathlib import Path
from urllib.parse import urlencode
from byline import entity_for
from lib import meta_description
ROOT = Path(__file__).resolve().parents[2]

def render(*, hub, pub, domain, url, home, members, siblings, overviews=None):
    data = json.loads((ROOT/'content-bank/page-quality-hubs.json').read_text())
    row = data.get(hub['slug'])
    if not row:
        return None
    e = html.escape
    questions = row[2:5]
    sources = {s['id']:s for s in json.loads((ROOT/'data/external-sources.json').read_text())['sources']}
    listing = ''.join(f'<li><a href="{e(m["url"])}">{e(m["title"])}</a></li>' for m in members)
    tasks = ''.join(f'<tr><th>{e(q)}</th><td>{e(a.split(". ")[0])}.</td></tr>' for q,a in questions)
    faq = ''.join(f'<h3>{e(q)}</h3><p>{e(a)}</p>' for q,a in questions)
    refs = ''.join(f'<li><a href="{e(sources[k]["url"])}">{e(sources[k]["publisher"])}: {e(sources[k]["title"])}</a> — {e(sources[k]["supports"])}</li>' for k in row[5:])
    # CollectionPage does not claim that the linked articles were authored today.
    graph = [
        {'@type':'CollectionPage','@id':url,'name':hub['title'],'url':url,
         'datePublished':'2026-11-03','dateModified':'2026-11-03','publisher':{'@type':'Organization','name':pub['title'],'url':home},
         'speakable':{'@type':'SpeakableSpecification','cssSelector':['.definition','.faq']},
         'mainEntity':{'@type':'ItemList','numberOfItems':len(members),'itemListElement':[
             {'@type':'ListItem','position':i+1,'url':m['url'],'name':m['title']} for i,m in enumerate(members)]}},
        {'@type':'FAQPage','mainEntity':[{'@type':'Question','name':q,'acceptedAnswer':{'@type':'Answer','text':a}} for q,a in questions]},
        {'@type':'BreadcrumbList','itemListElement':[
            {'@type':'ListItem','position':1,'name':pub['title'],'item':home},
            {'@type':'ListItem','position':2,'name':hub['title'],'item':url}]}
    ]
    title = meta_description.site_title(hub['title'],pub['title'],hub['slug'])
    more = ''.join(f'<li><a href="{e(u)}">{e(t)}</a></li>' for t,u in siblings)
    next_url = '/corrections?' + urlencode({'page_kind':'topic','slug':hub['slug']})
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{e(title)}</title><meta name="description" content="{e(hub["summary"])}"><link rel="canonical" href="{e(url)}"><link rel="stylesheet" href="/styles.css">'
        '<script type="application/ld+json">'+json.dumps({'@context':'https://schema.org','@graph':graph},ensure_ascii=False)+'</script></head><body>'
        f'<main class="page"><nav><a href="/">{e(pub["title"])}</a></nav><article><h1>{e(hub["title"])}</h1>'
        f'<p class="definition">{e(row[0])}</p><h2>Quick answer</h2><p>{e(row[1])}</p>'
        f'<p>What this guide is best for: {e(hub["summary"])}</p>'
        '<h2>What should I decide before choosing a resource?</h2><table><thead><tr><th>Question</th><th>Starting action</th></tr></thead>'
        f'<tbody>{tasks}</tbody></table><h2>Which guides cover the details?</h2><ul>{listing}</ul>'
        f'<section class="faq"><h2>Frequently asked questions</h2>{faq}</section>'
        + (f'<h2>Where can I check the underlying requirements?</h2><ul>{refs}</ul>' if refs else '')
        + f'<aside class="next-step"><h2>Need to clarify this guide?</h2><p><a href="{e(next_url)}">Send {e(pub["title"])} a question or correction</a>.</p></aside>'
        f'<p>By <a rel="author" href="/masthead">{e(entity_for(pub["title"]))}</a> · Publisher: {e(pub["title"])} · Guide edition published November 3, 2026 · Updated <time datetime="2026-11-03">November 3, 2026</time>. <a href="/about">About this publication</a>.</p>'
        f'<p>{e(pub["disclosure"])} Affiliation disclosed: This page is not legal, medical, mental-health, immigration, financial, or professional advice.</p>'
        f'</article><nav><h2>Related topics</h2><ul>{more}</ul></nav></main></body></html>\n')
