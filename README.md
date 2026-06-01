# pop-events-scraper

Collects family-friendly OKC events from a few public venue sites and publishes
them as a single `events.json` the **Pop** iOS app fetches.

## How it works

1. GitHub Actions runs `scrape.py` on a **bi-weekly** cron (1st & 15th, ~3–4 AM CT).
2. Each source in `sources/` returns events matching the schema in
   [`sources/base.py`](sources/base.py).
3. The orchestrator merges, de-dupes, sorts, and commits `events.json`.
4. The Pop app fetches the raw file URL and caches it locally for 1 hour.

The app only ever reads one URL:
```
https://raw.githubusercontent.com/<owner>/pop-events-scraper/main/events.json
```
Point the app's `AroundTownService` at that once this repo is pushed to GitHub.

## Sources

| Source | Method | Status |
|--------|--------|--------|
| Science Museum Oklahoma | The Events Calendar REST API | ✅ live |
| Scissortail Park | MEC JSON-LD on the listing page (1 request, date-level) | ✅ live |
| Myriad Botanical Gardens | WP REST `mec-events` list → per-event detail-page JSON-LD (real times) | ✅ live |
| VisitOKC (metro aggregator) | RSS feed (`/event/rss/`) → per-event detail-page JSON-LD (dates + venue + geo) | ✅ live |
| Oklahoma Contemporary | WP REST `event` CPT; dates from inline `meta_box._global_start_date` | ✅ live |
| National Cowboy Museum | Tribe `tribe_events-sitemap.xml` (discovery) → `/events/v1/events/by-slug/` (enrich) | ✅ live |

## Run locally

```bash
pip install -r requirements.txt
python3 scrape.py --dry-run   # preview, writes nothing
python3 scrape.py             # writes events.json
```

## Add a source

1. Create `sources/<name>.py` exposing `SOURCE_NAME` and `fetch() -> list[dict]`.
2. Map each event to the schema documented in `sources/base.py`.
3. Append the module to `SOURCES` in `scrape.py`.
4. Run `python3 scrape.py --dry-run` to verify.

Sources must **fail soft** — wrap network/parse in try/except and return what you
have. A broken source should never empty the whole feed.

## Maintenance

Web sites change. When a source stops returning events, the GH Actions log shows
which one. Fix that source's module; the others keep working in the meantime.
