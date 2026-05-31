"""VisitOKC — metro-wide events aggregator (RSS list + per-event JSON-LD).

VisitOKC's public events page is a client-side Simpleview app with no static
data, BUT it also publishes a server-rendered RSS feed at `/event/rss/` and
every event detail page embeds a clean schema.org Event JSON-LD block (real
start/end dates, venue name, street address, geo coords). So we:

  1. Read the RSS feed for the list (title, link, category labels). The feed's
     <pubDate> is NOT the event date — it's a publish stamp — so we ignore it.
  2. Fetch each event's detail page and pull its Event JSON-LD for the real
     dates + venue.

This is the same list-then-detail shape as Myriad Gardens. As a destination-
marketing aggregator, VisitOKC surfaces events from many venues at once
(including some we can't scrape directly, e.g. Oklahoma Contemporary), which is
exactly the "what's happening this weekend" coverage the family wants.

robots.txt: `Allow: /` with a 2s crawl-delay (only /plugins/crm/count/ is
disallowed) — we honor the delay. No API key needed.
"""

from __future__ import annotations

import re
import time
import datetime as dt
import xml.etree.ElementTree as ET
import requests

from .base import (
    strip_html,
    guess_category,
    truncate,
    parse_jsonld_events,
    schema_date_to_iso,
    offers_to_cost,
)

SOURCE_NAME = "VisitOKC"
RSS = "https://www.visitokc.com/event/rss/"
HORIZON_DAYS = 90          # only keep events within this window
MAX_EVENTS = 40            # cap on what we return
CRAWL_DELAY = 2            # seconds between detail fetches (robots.txt)
HEADERS = {"User-Agent": "pop-events-scraper/1.0 (+family calendar; contact via repo)"}

_IMG_SRC_RE = re.compile(r"<img[^>]+src=['\"]([^'\"]+)['\"]", re.I)

# RSS <category> labels map to our taxonomy more reliably than keyword-guessing
# the title. First match wins; checked before the generic title guesser.
_RSS_CATEGORY_MAP = [
    ("kids", {"family & kids", "family and kids", "kids"}),
    ("music", {"music", "concerts", "performing arts"}),
    ("food", {"food", "food & drink", "culinary", "nightlife"}),
    ("art", {"visual arts", "arts", "museums", "galleries", "theater", "film"}),
    ("sports", {"sports", "recreation"}),
    ("outdoor", {"tours", "outdoors", "festivals", "markets"}),
]


def fetch() -> list[dict]:
    try:
        resp = requests.get(RSS, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        items = ET.fromstring(resp.content).findall(".//item")
    except Exception as exc:  # noqa: BLE001 — source failure must not kill the run
        print(f"[{SOURCE_NAME}] RSS fetch/parse failed: {exc}")
        return []

    today = dt.date.today().isoformat()
    end = (dt.date.today() + dt.timedelta(days=HORIZON_DAYS)).isoformat()

    out: list[dict] = []
    seen_ids: set[str] = set()
    for item in items:
        if len(out) >= MAX_EVENTS:
            break
        mapped = _from_item(item)
        time.sleep(CRAWL_DELAY)
        if not mapped:
            continue
        if mapped["id"] in seen_ids:
            continue
        # Keep events that are active within our window: they must not have
        # already ended, and must start before the horizon. (Many aggregator
        # events are multi-month runs, so test the range, not just the start.)
        if mapped["endDate"][:10] < today or mapped["startDate"][:10] > end:
            continue
        seen_ids.add(mapped["id"])
        out.append(mapped)

    out.sort(key=lambda e: e["startDate"])
    print(f"[{SOURCE_NAME}] collected {len(out)} events")
    return out


def _from_item(item: "ET.Element") -> dict | None:
    link = (item.findtext("link") or "").strip()
    rss_title = strip_html(item.findtext("title") or "").strip()
    if not link or not rss_title:
        return None

    cats = [c.text.strip().lower() for c in item.findall("category") if c.text]

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

    title = strip_html(ev.get("name", "")).strip() or rss_title
    start_iso, all_day = schema_date_to_iso(ev.get("startDate"))
    if not start_iso:
        return None
    end_iso, _ = schema_date_to_iso(ev.get("endDate") or ev.get("startDate"))
    end_iso = end_iso or start_iso

    loc = ev.get("location") or {}
    venue = strip_html(loc.get("name", "")) if isinstance(loc, dict) else ""
    city = ""
    if isinstance(loc, dict):
        addr = loc.get("address")
        if isinstance(addr, dict):
            city = (addr.get("addressLocality") or "").strip()

    offers = ev.get("offers") or {}
    desc = truncate(strip_html(ev.get("description", "")))

    return {
        "id": f"vokc-{_event_id(link)}",
        "source": SOURCE_NAME,
        "sourceURL": link,
        "title": title,
        "description": desc,
        "startDate": start_iso,
        "endDate": end_iso,
        "allDay": all_day,
        "venueName": venue or SOURCE_NAME,
        "city": city or "Oklahoma City",
        "imageURL": _image(ev, item),
        "category": _category(cats, title, venue),
        "cost": offers_to_cost(offers) or ("Free" if "free event" in cats else ""),
    }


def _event_id(link: str) -> str:
    """VisitOKC detail URLs end in a numeric id segment: .../slug/30833/."""
    parts = [p for p in link.split("/") if p]
    for p in reversed(parts):
        if p.isdigit():
            return p
    return parts[-1] if parts else link


def _category(rss_cats: list, title: str, venue: str) -> str:
    for key, labels in _RSS_CATEGORY_MAP:
        if any(c in labels for c in rss_cats):
            return key
    return guess_category(title, " ".join(rss_cats), venue)


def _image(ev: dict, item: "ET.Element") -> str:
    img = ev.get("image")
    if isinstance(img, str) and img:
        return img
    if isinstance(img, dict):
        return img.get("url", "") or ""
    if isinstance(img, list) and img:
        first = img[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return first.get("url", "") or ""
    # Fall back to the thumbnail embedded in the RSS description.
    m = _IMG_SRC_RE.search(item.findtext("description") or "")
    return m.group(1) if m else ""
