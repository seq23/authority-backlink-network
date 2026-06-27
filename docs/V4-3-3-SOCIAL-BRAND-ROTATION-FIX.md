# V4.3.3 Social Brand Rotation Fix

Status: PASS

## Problem fixed

The prior dry run could keep selecting the earliest brands in `data/social-queue.json`, which risked starving smaller portfolio brands.

## Fix

The social publisher now uses:

- `data/social-brand-policy.json`
- weighted round-robin brand selection
- daily date-based rotation offset
- prior posted count divided by quota weight
- platform-specific duplicate checks
- unique dry-run IDs that include platform, brand, post type, source path, and body

## Result

Daily posting remains capped at:

- LinkedIn: 1/day
- X: 5/day

But eligible brands rotate over time instead of permanently favoring whichever brands appear first in the queue.

## Guardrail

This does not force every brand to post every day. With one LinkedIn account and five X posts/day, the system must rotate across days rather than flooding the feed.
