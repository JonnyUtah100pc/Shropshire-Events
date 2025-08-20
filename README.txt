# Shrewsbury & Shropshire ICS — Auto-build

This repo auto-scrapes official sites (via JSON-LD and optional RSS) and rebuilds an `.ics` at:

```
https://JonnyUtah100pc.github.io/shropshire-events/shrewsbury_events_JonnyUtah100pc.ics
```

## How it works
- `scripts/build_ics.py` fetches URLs in `data/sources.yaml`, extracts schema.org **Event** JSON-LD, plus any `data/manual.yaml` entries.
- It generates **stable UIDs** (`slug-of-name-YEAR@JonnyUtah100pc.github.io`) and bumps `SEQUENCE` if details change.
- A GitHub Action runs daily and on demand to publish updates.

## Customize
- Add/remove sources in `data/sources.yaml`. Prefer official sites.
- Put must-include events in `data/manual.yaml`.
- If a site has an RSS/Atom feed, set `type: rss` and the feed URL.

## Local dev
```
pip install -r requirements.txt
python scripts/build_ics.py
```

> Tip: Keep the ICS filename and path constant so subscribers always see updates.
