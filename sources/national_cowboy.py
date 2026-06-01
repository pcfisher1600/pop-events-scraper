"""National Cowboy & Western Heritage Museum — Tribe sitemap + by-slug REST.

The museum runs The Events Calendar (Tribe), but its default `/events` REST
query only surfaces ~2 recurring drop-in activities — the marquee programming
(Prix de West, National Day of the Cowboy, HalloWest, etc.) is missing from it,
and Tribe's category/featured filters are broken on this install. Those events
ARE reachable compliantly via two robots-allowed paths:

  1. Discovery: `tribe_events-sitemap.xml` lists every event URL with a
     <lastmod>. Upcoming events are the most recently modified, so we take the
     freshest slugs as candidates. (robots.txt disallows /calendar/* — the
     human list view — but sitemaps and /event/<slug>/ detail are allowed.)
  2. Enrichment: `/wp-json/tribe/events/v1/events/by-slug/<slug>` returns clean
     JSON with title, start_date, end_date, all_day, description, image,
     categories. We keep only events starting within the horizon.

Yield is small (~10-12 distinct real events) but high-value: these are the
exact family/marquee OKC events the other sources miss. venue/cost come back
empty, so we default them.
"""

from __future__ import annotations

import re
import time
import datetime as dt
import requests

from .base import strip_html, guess_category, truncate

SOURCE_NAME = "National Cowboy & Western Heritage Museum"
SITEMAP = "https://nationalcowboymuseum.org/tribe_events-sitemap.xml"
BY_SLUG = "https://nationalcowboymuseum.org/wp-json/tribe/events/v1/events/by-slug/{}"
HORIZON_DAYS = 180         # marquee events are scheduled far out
MAX_CANDIDATES = 60        # most-recently-modified slugs to enrich
MAX_EVENTS = 25
CRAWL_DELAY = 0.5          # between by-slug calls (polite; REST is cheap)
HEADERS = {"User-Agent": "pop-events-scraper/1.0 (+family calendar; contact via repo)"}

_URL_RE = re.compile(
    r"<url>\s*<loc>https://nationalcowboymuseum\.org/event/([a-z0-9-]+)/</loc>"
    r"\s*(?:<lastmod>([^<]+)</lastmod>)?",
    re.I,
)


def fetch() -> list[dict]:
    slugs = _candidate_slugs()
    if not slugs:
        return []

    today = dt.date.today().isoformat()
    end = (dt.date.today() + dt.timedelta(days=HORIZON_DAYS)).isoformat()

    out: list[dict] = []
    seen_titles: set[str] = set()
    for slug in slugs:
        if len(out) >= MAX_EVENTS:
            break
        mapped = _enrich(slug)
        time.sleep(CRAWL_DELAY)
        if not mapped:
            continue
        day = mapped["startDate"][:10]
        if day < today or day > end:
            continue
        key = mapped["title"].lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        out.append(mapped)

    out.sort(key=lambda e: e["startDate"])
    print(f"[{SOURCE_NAME}] collected {len(out)} events")
    return out


def _candidate_slugs() -> list[str]:
    """Most-recently-modified event slugs from the Tribe sitemap (upcoming
    events get touched most recently, so this front-loads them)."""
    try:
        resp = requests.get(SITEMAP, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"[{SOURCE_NAME}] sitemap fetch failed: {exc}")
        return []
    entries = _URL_RE.findall(resp.text)
    entries.sort(key=lambda e: e[1] or "", reverse=True)  # by lastmod desc
    return [slug for slug, _ in entries[:MAX_CANDIDATES]]


def _enrich(slug: str) -> dict | None:
    try:
        resp = requests.get(BY_SLUG.format(slug), headers=HEADERS, timeout=20)
        resp.raise_for_status()
        ev = resp.json()
    except Exception as exc:  # noqa: BLE001
        print(f"[{SOURCE_NAME}] by-slug failed for {slug}: {exc}")
        return None

    title = strip_html(ev.get("title", "")).strip()
    start = ev.get("start_date")
    if not title or not start:
        return None

    cats = ev.get("categories") or []
    cat_names = " ".join(c.get("name", "") for c in cats if isinstance(c, dict))

    image = ""
    img = ev.get("image")
    if isinstance(img, dict):
        image = img.get("url", "") or ""

    return {
        "id": f"ncm-{ev.get('id', slug)}",
        "source": SOURCE_NAME,
        "sourceURL": ev.get("url", f"https://nationalcowboymuseum.org/event/{slug}/"),
        "title": title,
        "description": truncate(strip_html(ev.get("description", ""))),
        "startDate": _to_iso(ev.get("start_date"), ev.get("utc_start_date")),
        "endDate": _to_iso(ev.get("end_date"), ev.get("utc_end_date"))
        or _to_iso(ev.get("start_date"), ev.get("utc_start_date")),
        "allDay": bool(ev.get("all_day", False)),
        "venueName": SOURCE_NAME,
        "city": "Oklahoma City",
        "imageURL": image,
        "category": guess_category(title, cat_names),
        "cost": (ev.get("cost") or "").strip(),
    }


def _to_iso(local: str | None, utc: str | None) -> str | None:
    """Build ISO-8601 from Tribe's 'YYYY-MM-DD HH:MM:SS' local time, attaching
    the offset implied by the local-vs-utc delta (America/Chicago)."""
    if not local:
        return None
    try:
        local_dt = dt.datetime.strptime(local, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    if utc:
        try:
            utc_dt = dt.datetime.strptime(utc, "%Y-%m-%d %H:%M:%S")
            total_min = int((local_dt - utc_dt).total_seconds() // 60)
            sign = "+" if total_min >= 0 else "-"
            total_min = abs(total_min)
            hh, mm = divmod(total_min, 60)
            return local_dt.strftime("%Y-%m-%dT%H:%M:%S") + f"{sign}{hh:02d}:{mm:02d}"
        except ValueError:
            pass
    return local_dt.strftime("%Y-%m-%dT%H:%M:%S") + "-05:00"
