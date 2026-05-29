"""Myriad Botanical Gardens — WordPress REST + per-event JSON-LD.

Myriad also runs Modern Events Calendar, but (unlike Scissortail) its listing
page is Elementor-rendered and carries no Event JSON-LD. So we:

  1. List events from the WP REST `mec-events` custom post type (titles, links,
     categories) — one request, ~70 posts. The REST record has no event date,
     only the publish date.
  2. Fetch each event's detail page, which DOES embed an Event JSON-LD block
     with the next occurrence's real start/end datetime (proper TZ offset).

Each MEC event is a single post, so its detail page reports the soonest upcoming
occurrence — recurring classes collapse to one entry for free. We then keep only
events inside the horizon window. robots.txt allows everything but /wp-admin/.
"""

from __future__ import annotations

import re
import time
import datetime as dt
import requests

from .base import (
    strip_html,
    guess_category,
    truncate,
    parse_jsonld_events,
    schema_date_to_iso,
    offers_to_cost,
)

SOURCE_NAME = "Myriad Botanical Gardens"
BASE = "https://myriadgardens.org"
CPT = f"{BASE}/wp-json/wp/v2/mec-events"
CATEGORIES = f"{BASE}/wp-json/wp/v2/mec_category"
HORIZON_DAYS = 90          # only keep events within this window
MAX_EVENTS = 40            # cap on what we return
MAX_DETAIL = 70            # cap on detail-page fetches (≈ all listed events)
CRAWL_DELAY = 1.5          # seconds between detail-page requests (be polite)
HEADERS = {"User-Agent": "pop-events-scraper/1.0 (+family calendar; contact via repo)"}

_OG_IMAGE_RE = re.compile(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', re.I)


def fetch() -> list[dict]:
    posts = _list_posts()
    if not posts:
        return []
    cat_map = _category_map()

    today = dt.date.today().isoformat()
    end = (dt.date.today() + dt.timedelta(days=HORIZON_DAYS)).isoformat()

    out: list[dict] = []
    fetched = 0
    for post in posts:
        if fetched >= MAX_DETAIL:
            print(f"[{SOURCE_NAME}] hit MAX_DETAIL={MAX_DETAIL}; stopping detail fetches")
            break
        mapped = _fetch_detail(post, cat_map)
        fetched += 1
        time.sleep(CRAWL_DELAY)
        if not mapped:
            continue
        day = mapped["startDate"][:10]
        if day < today or day > end:  # past, or beyond horizon
            continue
        out.append(mapped)

    out.sort(key=lambda e: e["startDate"])
    out = out[:MAX_EVENTS]
    print(f"[{SOURCE_NAME}] collected {len(out)} events (from {fetched} detail pages)")
    return out


def _list_posts() -> list[dict]:
    try:
        resp = requests.get(CPT, params={"per_page": 100}, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        print(f"[{SOURCE_NAME}] CPT list failed: {exc}")
        return []


def _category_map() -> dict:
    """id → category name, for better classification. Best-effort."""
    try:
        resp = requests.get(CATEGORIES, params={"per_page": 100}, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return {c["id"]: c.get("name", "") for c in resp.json() if isinstance(c, dict)}
    except Exception as exc:  # noqa: BLE001
        print(f"[{SOURCE_NAME}] category map failed (continuing without): {exc}")
        return {}


def _fetch_detail(post: dict, cat_map: dict) -> dict | None:
    link = post.get("link") or ""
    title = strip_html((post.get("title") or {}).get("rendered", "")).strip()
    if not link or not title:
        return None

    try:
        resp = requests.get(link, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:  # noqa: BLE001
        print(f"[{SOURCE_NAME}] detail fetch failed for {link}: {exc}")
        return None

    events = parse_jsonld_events(html)
    if not events:
        return None
    ev = events[0]

    start_iso, all_day = schema_date_to_iso(ev.get("startDate"))
    if not start_iso:
        return None
    end_iso, _ = schema_date_to_iso(ev.get("endDate") or ev.get("startDate"))
    end_iso = end_iso or start_iso

    offers = ev.get("offers") or {}
    cat_names = " ".join(cat_map.get(cid, "") for cid in post.get("mec_category", []) if cid in cat_map)
    excerpt = strip_html((post.get("excerpt") or {}).get("rendered", ""))

    image = ""
    og = _OG_IMAGE_RE.search(html)
    if og:
        image = og.group(1)

    return {
        "id": f"mbg-{post.get('id')}",
        "source": SOURCE_NAME,
        "sourceURL": link,
        "title": title,
        "description": truncate(strip_html(ev.get("description", "")) or excerpt),
        "startDate": start_iso,
        "endDate": end_iso,
        "allDay": all_day,
        "venueName": SOURCE_NAME,
        "city": "Oklahoma City",
        "imageURL": image,
        "category": guess_category(title, cat_names, excerpt),
        "cost": offers_to_cost(offers),
    }
