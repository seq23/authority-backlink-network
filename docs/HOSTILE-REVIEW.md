# Hostile Review Fix Loop

Every content change must survive hostile review.

## Review questions

1. Would this page still deserve to exist if Google did not exist?
2. Is every link useful to a human reader?
3. Is affiliation disclosed?
4. Does the page make legal, medical, mental-health, immigration, or financial claims?
5. Are anchors natural and varied?
6. Would this page embarrass the brand if reviewed by Google, LinkedIn, X, a client, or a regulator?

## Fix loop

If a page fails:

1. Remove unsupported claims.
2. Remove unnecessary links.
3. Add disclosure.
4. Add professional-topic disclaimer.
5. Replace exact-match anchor with branded or natural anchor.
6. Re-run `python3 scripts/hostile_review.py`.
7. Only deploy when errors are zero.
