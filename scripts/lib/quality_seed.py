"""Page shape for seed articles, using their recorded decisions rather than filler."""
import html
import json
import re
from byline import entity_for

def upgrade(page, article, pub):
    if pub['id'] not in ('founder', 'memphis'):
        return page
    e = html.escape
    factors = article['decision_factors']
    questions = article['questions']
    mistakes = article['mistakes']
    from urllib.parse import urlsplit
    from pathlib import Path
    registry=json.loads((Path(__file__).resolve().parents[2]/'data/link-registry.json').read_text())
    source=f"{pub['folder']}/daily/{article['date']}-{article['slug']}.html"
    recorded=[r for r in registry if r.get('source_path')==source and r.get('target_brand_id')==article['target_brand_id']]
    host=lambda u:(urlsplit(u).hostname or '').removeprefix('www.')
    anchors=re.findall(r'<a\b[^>]*href="[^"]+"[^>]*>.*?</a>',page,re.S)
    reference=next((a for a in anchors if host(re.search(r'href="([^"]+)"',a)[1])==host(article['target_url'])), '')
    if recorded and not any(r.get('status')=='published' for r in recorded):
        reference=''
    resource=(f'<h2>Which related resource can I consult?</h2><p>{reference}.</p>' if reference else '')
    # FAQ answers contain the actual recorded content, never invented replies to
    # the provider-facing questions (which remain a list for the reader to ask).
    faq = [(article['title'].rstrip('?') + '?', article['direct_answer']),
           ('What should I establish before deciding?', ' '.join(factors)),
           ('Which mistakes should I avoid?', ' '.join(mistakes))]
    comparison = article.get('comparison')
    table = ''
    if comparison:
        table = '<h2>How do the options compare?</h2><table><thead><tr>' + ''.join('<th>'+e(x)+'</th>' for x in comparison['headers']) + '</tr></thead><tbody>' + ''.join('<tr>'+''.join('<td>'+e(x)+'</td>' for x in row)+'</tr>' for row in comparison['rows']) + '</tbody></table>'
    # Existing direct answers are authored individually. They stand as the
    # definition; the quick answer is the concrete first recorded action.
    body = (f'<h1>{e(article["title"])}</h1><p class="dek">{e(article["direct_answer"])}</p><p class="definition">{e(article.get("definition", article["direct_answer"]))}</p>'
            f'<p>What this guide is best for: {e(article["title"])}</p>'
            f'<p class="topic-context"><strong>Topic context:</strong> {e(article["quality_topic"])}.</p>'
            '<h2>What should I compare?</h2><ul>'+''.join(f'<li>{e(x)}</li>' for x in factors)+'</ul>'
            '<h2>What questions should I ask?</h2><ul>'+''.join(f'<li>{e(x)}</li>' for x in questions)+'</ul>'
            '<section class="faq"><h2>Frequently asked questions</h2>'+''.join(f'<h3>{e(q)}</h3><p>{e(a)}</p>' for q,a in faq)+'</section>'
            + resource +
            f'<aside class="next-step"><h2>Need to clarify this guide?</h2><p><a href="/corrections?page_kind=guide&amp;slug={e(article["slug"])}">Send {e(pub["title"])} a question or correction</a>.</p></aside>'
            f'<p>By {e(entity_for(pub["title"]))} · Publisher: {e(pub["title"])} · Published {article["date"]} · Updated 2026-11-03. <a href="/about">About this publication</a>.</p>'
            f'<h2>Editorial and affiliation note</h2><p>{e(pub["disclosure"])} {e(article["disclaimer"])} Affiliation disclosed: This page is not legal, medical, mental-health, immigration, financial, or professional advice.</p>')
    # Carry every enrichment that contains citations into the new article body.
    enrichment = re.findall(r'<section\b[^>]*data-block="(?:external-sources|external-citations)"[^>]*>.*?</section>',page,re.S)
    sources = {s['id']: s for s in json.loads((Path(__file__).resolve().parents[2]/'data/external-sources.json').read_text())['sources']}
    if article.get('source_ids'):
        refs = []
        for sid in article['source_ids']:
            source = sources[sid]
            if pub['id'] not in source['lanes']:
                raise ValueError('source outside publication lane: ' + sid)
            refs.append(f'<li><a href="{e(source["url"])}">{e(source["publisher"])}: {e(source["title"])}</a> — {e(source["supports"])}</li>')
        enrichment = ['<section data-block="external-sources"><h2>Where can I check the underlying guidance?</h2><ul>' + ''.join(refs) + '</ul></section>']
    body += table + ''.join(enrichment)
    page = re.sub(r'<article>.*?</article>',lambda m:'<article>'+body+'</article>',page,count=1,flags=re.S)
    def schema(m):
        d=json.loads(m[1]); nodes=d.get('@graph',[d])
        for node in nodes:
            if node.get('@type')=='FAQPage':
                node['mainEntity']=[{'@type':'Question','name':q,'acceptedAnswer':{'@type':'Answer','text':a}} for q,a in faq]
            if node.get('@type')=='Article':
                node['dateModified']='2026-11-03';node['speakable']={'@type':'SpeakableSpecification','cssSelector':['.definition','.faq']}
        return '<script type="application/ld+json">'+json.dumps(d,ensure_ascii=False)+'</script>'
    page=re.sub(r'<script type="application/ld\+json">(.*?)</script>',schema,page,flags=re.S)
    return page
