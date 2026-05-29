"""Scissortail Park — Modern Events Calendar JSON-LD.

The /events/ listing page embeds one `application/ld+json` Event object per
upcoming event (MEC's structured-data output). We read them straight off the
listing — no per-event detail fetch — which keeps this to a single request.

robots.txt allows /events/ (it blocks /wp-json/ and /*? query URLs, neither of
which we touch). MEC only emits date-level granularity here, so events are
all-day. Daily/weekly recurring programming (Farmers Market, Zumba, Walking
Club) repeats across the listing; we collapse each title to its soonest date.
"""

from __future__ import annotations

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

SOURCE_NAME = "Scissortail Park"
LISTING = "https://www.scissortailpark.org/events/"
HORIZON_DAYS = 90          # only keep events within this window
MAX_EVENTS = 40            # cap so events.json stays small
HEADERS = {"User-Agent": "pop-events-scraper/1.0 (+family calendar; contact via repo)"}


def fetch() -> list[dict]:
    try:
        resp = requests.get(LISTING, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 — source failure must not kill the run
        print(f"[{SOURCE_NAME}] listing fetch failed: {exc}")
        return []

    today = dt.date.today().isoformat()
    end = (dt.date.today() + dt.timedelta(days=HORIZON_DAYS)).isoformat()

    # JSON-LD blocks appear in DOM order, which MEC renders ascending by date,
    # so the first time we see a title is its soonest occurrence.
    seen_titles: set[str] = set()
    out: list[dict] = []

    for raw in parse_jsonld_events(resp.text):
        mapped = _map(raw)
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
        if len(out) >= MAX_EVENTS:
            break

    print(f"[{SOURCE_NAME}] collected {len(out)} events")
    return out


def _map(ev: dict) -> dict | None:
    title = strip_html(ev.get("name", "")).strip()
    start = ev.get("startDate")
    if not title or not start:
        return None

    start_iso, all_day = schema_date_to_iso(start)
    if not start_iso:
        return None
    end_iso, _ = schema_date_to_iso(ev.get("endDate") or start)
    end_iso = end_iso or start_iso

    loc = ev.get("location") or {}
    venue = strip_html(loc.get("name", "")) if isinstance(loc, dict) else ""

    offers = ev.get("offers") or {}
    url = offers.get("url", "") if isinstance(offers, dict) else ""

    return {
        "id": f"stp-{_slug(url, title)}-{start_iso[:10]}",
        "source": SOURCE_NAME,
        "sourceURL": url,
        "title": title,
        "description": truncate(strip_html(ev.get("description", ""))),
        "startDate": start_iso,
        "endDate": end_iso,
        "allDay": all_day,
        "venueName": venue or SOURCE_NAME,
        "city": "Oklahoma City",
        "imageURL": _image(ev),
        "category": guess_category(title, venue),
        "cost": offers_to_cost(offers),
    }


def _slug(url: str, title: str) -> str:
    """Stable id stem from the event's URL slug, falling back to the title."""
    if url:
        parts = [p for p in url.split("/") if p]
        if parts:
            return parts[-1]
    return "".join(c if c.isalnum() else "-" for c in title.lower()).strip("-")


def _image(ev: dict) -> str:
    img = ev.get("image")
    if isinstance(img, str):
        return img
    if isinstance(img, dict):
        return img.get("url", "") or ""
    if isinstance(img, list) and img:
        first = img[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return first.get("url", "") or ""
    return ""
