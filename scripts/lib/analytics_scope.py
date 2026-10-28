"""Clarity belongs only on pages where a reader fills a form or buys (e9)."""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[2]
# The existing AI referrer classifier, emitted only alongside a scoped loader.
AI_REFERRER = '(function(w,d,m){try{var r=d.referrer||"";var host="";try{host=r?new URL(r).hostname.toLowerCase():"";}catch(e){host="";}var self=(w.location.hostname||"").toLowerCase().replace(/^www\\./,"");var cls="direct";var engine="";if(host){var bare=host.replace(/^www\\./,"");if(bare===self){cls="internal";}else if(m[host]||m[bare]){engine=m[host]||m[bare];cls=(engine==="bing-or-copilot")?"search-or-ai":"ai";}else if(/(^|\\.)(google|yahoo|baidu|yandex|ecosia|startpage)\\./.test(host)){cls="search";}else if(/(^|\\.)(facebook|instagram|linkedin|reddit|twitter|x)\\./.test(host)){cls="social";}else{cls="referral";}}w.clarity=w.clarity||function(){(w.clarity.q=w.clarity.q||[]).push(arguments)};w.clarity("set","referrer_class",cls);if(engine){w.clarity("set","ai_engine",engine);}if(cls==="ai"){w.clarity("set","ai_landing_path",(w.location.pathname||"/").slice(0,120));w.clarity("upgrade","ai_referral");}if(host){w.clarity("set","referrer_host",host.slice(0,80));}}catch(e){}})(window,document,{"chatgpt.com":"chatgpt","chat.openai.com":"chatgpt","openai.com":"chatgpt","perplexity.ai":"perplexity","www.perplexity.ai":"perplexity","copilot.microsoft.com":"copilot","www.bing.com":"bing-or-copilot","bing.com":"bing-or-copilot","gemini.google.com":"gemini","bard.google.com":"gemini","claude.ai":"claude","you.com":"you","www.you.com":"you","search.brave.com":"brave-ai","duckduckgo.com":"duckduckgo","phind.com":"phind","poe.com":"poe"});'
MANAGED = re.compile(r'<script\s+data-(?:clarity-loader|ai-referrer-tag)\b[^>]*>.*?</script>', re.S | re.I)
CHECKOUT_HOSTS = ("gumroad.com", "stripe.com", "paypal.com", "lemonsqueezy.com",
                  "square.link", "checkout.shopify.com")


class ConversionParser(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base, self.converts = base, False

    def handle_starttag(self, tag, attrs):
        if tag == "form":
            self.converts = True
        if tag != "a":
            return
        href = dict(attrs).get("href") or ""
        target = urlsplit(urljoin(self.base, href))
        if target.scheme not in ("http", "https"):
            return
        host = (target.hostname or "").lower()
        if any(host == h or host.endswith("." + h) for h in CHECKOUT_HOSTS) or re.search(
                r"/(checkout|cart|buy|order|book(ing)?)(/|$)", target.path, re.I):
            self.converts = True


def form_or_buy(text: str, base: str) -> bool:
    parser = ConversionParser(base)
    parser.feed(text)
    return parser.converts


def install(text: str, domain: str) -> str:
    """Replace both managed tags, or remove them when there is no conversion."""
    text = MANAGED.sub("", text)
    if not form_or_buy(text, "https://" + domain + "/"):
        return text
    project = json.loads((ROOT / "data/clarity_projects.json").read_text())["projects"].get(domain)
    if not project:
        return text
    mapping = json.dumps({domain: project}, separators=(",", ":"))
    loader = ('<script data-clarity-loader>(function(w,d,m){var h=(w.location.hostname||"")'
              '.toLowerCase().replace(/^www\\./,"");var id=m[h];if(!id)return;w.clarity=w.clarity||'
              'function(){(w.clarity.q=w.clarity.q||[]).push(arguments)};var s=d.createElement("script");'
              's.async=1;s.src="https://www.clarity.ms/tag/"+id;var f=d.getElementsByTagName("script")[0];'
              'f.parentNode.insertBefore(s,f)})(window,document,' + mapping + ')</script>')
    referrer = '<script data-ai-referrer-tag>' + AI_REFERRER + '</script>'
    return re.sub(r"</head>", lambda _: loader + referrer + "</head>", text, count=1, flags=re.I)
