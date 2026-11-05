"""Authored overview slots in the existing chrome generator; no hand-edited HTML."""
import html,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def apply(text,pub_title,domain):
    canonical=re.search(r'<link rel="canonical" href="https://'+re.escape(domain)+r'/([^"/]+)">',text)
    data=json.loads((ROOT/'content-bank/page-quality-overviews.json').read_text())
    row=(data.get(domain + '/' + canonical[1]) or data.get(canonical[1])) if canonical else None
    if not row:
        # These query-led overviews already get authored definitions, question
        # headings, answers and lists from apply_strengthening. Keep that lane
        # as their source; install only the missing final action here.
        measured = {'founder-execution-systems', 'ai-executive-coaching-resources',
                    'memphis-grazing-table-resources'}
        if not canonical or canonical[1] not in measured:
            return text
        text = re.sub(r'<section data-page-quality="measured-action">.*?</section>', '', text, flags=re.S)
        resource = ''
        if canonical[1] == 'founder-execution-systems':
            resource = '<h2>Which related resource can I consult?</h2><p><a href="https://www.aplayermode.com/">A Player Mode</a> is an affiliated resource for daily planning and accountability. Compare its scope with the routine you need; the guide does not promise an outcome.</p>'
        block = (f'<section data-page-quality="measured-action">{resource}'
                 f'<aside class="next-step"><h2>Need to clarify this guide?</h2><p><a href="/corrections?page_kind=overview&amp;slug={html.escape(canonical[1])}">Send {html.escape(pub_title)} a question or correction</a>.</p></aside>'
                 f'<p>Publisher: {html.escape(pub_title)} · Updated November 3, 2026. <a href="/about">About the publication</a>.</p></section>')
        return text.replace('</main>', block + '</main>', 1)
    e=html.escape;slug=canonical[1]
    text=re.sub(r'<section data-page-quality="overview">.*?</section>','',text,flags=re.S)
    text=re.sub(r'<script type="application/ld\+json" data-page-quality="faq">.*?</script>','',text,flags=re.S)
    text=re.sub(r'<p class="definition">.*?</p>','',text,flags=re.S)
    # Replace the old dek and repeated recommendation card, plus the shared
    # four-item checklist that was unrelated to any particular overview.
    text=re.sub(r'<p class="dek">.*?</p>','',text,count=1,flags=re.S)
    text=re.sub(r'<section class="card">.*?</section>','',text,count=1,flags=re.S)
    text=re.sub(r'<section><h2>Useful checks before choosing</h2>.*?</section>','',text,count=1,flags=re.S)
    text=text.replace('<h2>Relevant resources</h2>','<h2>Which resources cover this topic?</h2>')
    opening=f'<p class="definition">{e(row[0])}</p>'
    measured=re.search(r'<p class="definition" data-strengthened="definition"[^>]*>.*?</p>',text,re.S)
    if measured:
        opening=measured[0]
    else:
        text=text.replace('</h1>','</h1>'+opening,1)
    published=re.search(r'"datePublished"\s*:\s*"([^" ]+)"',text)
    published=published[1] if published else "date not recorded"
    block=(f'<section data-page-quality="overview"><h2>Quick answer</h2><p>{e(row[1])}</p>'
           f'<p>What this guide is best for: {e(row[2][0].rstrip("?"))}.</p>'
           '<h2>What should I decide first?</h2><ol>'+''.join('<li>'+e(a.split('. ')[0])+'.</li>' for q,a in row[2:])+'</ol>'
           '<div class="faq"><h2>Frequently asked questions</h2>'+''.join('<h3>'+e(q)+'</h3><p>'+e(a)+'</p>' for q,a in row[2:])+'</div>'
           f'<aside class="next-step"><h2>Need to clarify this guide?</h2><p><a href="/corrections?page_kind=overview&amp;slug={e(slug)}">Send {e(pub_title)} a question or correction</a>.</p></aside>'
           f'<p>Publisher: {e(pub_title)} · Published {e(published)} · Updated November 3, 2026. <a href="/about">About the publication</a>.</p></section>')
    text=text.replace(opening,opening+block,1)
    faq={'@context':'https://schema.org','@type':'FAQPage','mainEntity':[{'@type':'Question','name':q,'acceptedAnswer':{'@type':'Answer','text':a}} for q,a in row[2:]]}
    text=text.replace('</head>','<script type="application/ld+json" data-page-quality="faq">'+json.dumps(faq,ensure_ascii=False)+'</script></head>',1)
    def schema(m):
        d=json.loads(m[1]);nodes=d.get('@graph',[d])
        for node in nodes:
            if node.get('@type')=='Article':
                node['dateModified']='2026-11-03';node['speakable']={'@type':'SpeakableSpecification','cssSelector':['.definition','.faq']}
        return '<script type="application/ld+json">'+json.dumps(d,ensure_ascii=False)+'</script>'
    return re.sub(r'<script type="application/ld\+json">(.*?)</script>',schema,text,flags=re.S)
