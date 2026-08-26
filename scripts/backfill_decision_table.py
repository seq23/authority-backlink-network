#!/usr/bin/env python3
"""Convert the four-part decision framework from prose into a table.

Why: research on AI answer citation is consistent that tables are extracted far
more reliably than prose, and comparison-table coverage across this network was
0% of 507 published pages. The four filters - fit, evidence, risk, next step -
and the question each one asks were already present in the copy. This restates
the same content as a table; nothing is invented, and no statistic is added
(there is no sourced figure to add, and fabricating one would be worse than the
gap it fills).

Idempotent: pages already carrying the table are left alone.
"""
import pathlib, re, sys

PROSE = ("<p>Use a four-part filter: fit, evidence, risk, and next step. Fit asks whether the "
         "resource matches your situation. Evidence asks what the claim is based on. Risk asks "
         "what could go wrong if you misunderstand the topic. Next step asks whether you need a "
         "checklist, a consult, a quote, or a qualified professional.</p>")
TABLE = ("<p>Use a four-part filter: fit, evidence, risk, and next step.</p>"
         "<table><thead><tr><th>Filter</th><th>The question it asks</th></tr></thead><tbody>"
         "<tr><td>Fit</td><td>Does the resource match your situation?</td></tr>"
         "<tr><td>Evidence</td><td>What is the claim based on?</td></tr>"
         "<tr><td>Risk</td><td>What could go wrong if you misunderstand the topic?</td></tr>"
         "<tr><td>Next step</td><td>Do you need a checklist, a consult, a quote, or a qualified professional?</td></tr>"
         "</tbody></table>")

changed = skipped = already = 0
for path in sorted(pathlib.Path("sites").rglob("*.html")):
    if "/agency/" in str(path):
        continue
    html = path.read_text(encoding="utf-8", errors="ignore")
    if "<th>Filter</th>" in html:
        already += 1
        continue
    if PROSE not in html:
        skipped += 1
        continue
    path.write_text(html.replace(PROSE, TABLE), encoding="utf-8")
    changed += 1

print(f"decision-table backfill: {changed} converted, {already} already had it, {skipped} without the prose block")
