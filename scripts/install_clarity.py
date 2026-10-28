#!/usr/bin/env python3
"""Install conversion-scoped analytics on the three publication source trees."""
from lib import analytics_scope, head_seo


def main():
    changed = eligible = pages = 0
    for pub, _, path, _, text in head_seo.published_pages(analytics_scope.ROOT):
        pages += 1
        domain = pub["working_domain"]
        eligible += analytics_scope.form_or_buy(text, "https://" + domain + "/")
        out = analytics_scope.install(text, domain)
        if out != text:
            path.write_text(out, encoding="utf-8")
            changed += 1
    print(f"Clarity: {pages} pages; {eligible} form/buy pages; {changed} changed")


if __name__ == "__main__":
    main()
