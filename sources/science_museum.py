"""Science Museum Oklahoma — The Events Calendar (Tribe) REST API.

Endpoint: https://www.sciencemuseumok.org/wp-json/tribe/events/v1/events
Returns clean paginated JSON with venue, categories, images, and TZ-aware
dates. robots.txt allows it with a 10s crawl-delay, which we honor.
"""

from __future__ import annotations

import time
import datetime as dt
import requests

from .base import strip_html, guess_category, truncate

SOURCE_NAME = "Science Museum Oklahoma"
API = "https://www.sciencemuseumok.org/wp-json/tribe/events/v1/events"
HORIZON_DAYS = 90          # only pull events within this window
MAX_EVENTS = 80            # cap so events.json stays small
PER_PAGE = 40
CRAWL_DELAY = 10           # seconds between page requests (robots.txt)
HEADERS = {"User-Agent": "pop-events-scraper/1.0 (+family calendar; contact via repo)"}


def fetch() -> list[dict]:
    today = dt.date.today()
    end = today + dt.timedelta(days=HORIZON_DAYS)
    out: list[dict] = []
    # The museum runs daily recurring programming (Tinkering, Planetarium,
    # etc.). The API returns one row per day, which would flood the feed with
    # the same title 30+ times. Collapse to the soonest occurrence per title.
    # The API returns ascending by date, so the first time we see a title is
    # its next occurrence.
    seen_titles: set[str] = set()
    page = 1

    while len(out) < MAX_EVENTS:
        params = {
            "per_page": PER_PAGE,
            "page": page,
            "start_date": today.strftime("%Y-%m-%d 00:00:00"),
            "end_date": end.strftime("%Y-%m-%d 23:59:59"),
            "status": "publish",
        }
        try:
            resp = requests.get(API, params=params, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001 — source failure must not kill the run
            print(f"[{SOURCE_NAME}] page {page} failed: {exc}")
            break

        events = data.get("events", [])
        if not events:
            break

        for ev in events:
            mapped = _map(ev)
            if not mapped:
                continue
            key = mapped["title"].lower()
            if key in seen_titles:
                continue  # already have this title's soonest occurrence
            seen_titles.add(key)
            out.append(mapped)
            if len(out) >= MAX_EVENTS:
                break

        total_pages = data.get("total_pages", 1)
        if page >= total_pages:
            break
        page += 1
        time.sleep(CRAWL_DELAY)

    print(f"[{SOURCE_NAME}] collected {len(out)} events")
    return out


def _map(ev: dict) -> dict | None:
    title = strip_html(ev.get("title", "")).strip()
    start = ev.get("start_date")  # "2026-04-28 09:00:00" local
    if not title or not start:
        return None

    tz = ev.get("timezone_abbr") or ""
    # Tribe gives separate utc_start_date; prefer the explicit offset form.
    start_iso = _to_iso(ev.get("start_date"), ev.get("utc_start_date"))
    end_iso = _to_iso(ev.get("end_date"), ev.get("utc_end_date")) or start_iso

    venue = ev.get("venue") or {}
    venue_name = strip_html(venue.get("venue", "")) if isinstance(venue, dict) else ""
    city = venue.get("city", "") if isinstance(venue, dict) else ""

    cats = ev.get("categories") or []
    cat_names = " ".join(c.get("name", "") for c in cats if isinstance(c, dict))

    image = ""
    img = ev.get("image")
    if isinstance(img, dict):
        image = img.get("url", "") or ""

    return {
        "id": f"smo-{ev.get('id')}",
        "source": SOURCE_NAME,
        "sourceURL": ev.get("url", ""),
        "title": title,
        "description": truncate(strip_html(ev.get("description", ""))),
        "startDate": start_iso,
        "endDate": end_iso,
        "allDay": bool(ev.get("all_day", False)),
        "venueName": venue_name or SOURCE_NAME,
        "city": city or "Oklahoma City",
        "imageURL": image,
        "category": guess_category(title, cat_names, venue_name),
        "cost": (ev.get("cost") or "").strip(),
    }


def _to_iso(local: str | None, utc: str | None) -> str | None:
    """Build an ISO-8601 string. Tribe's local time is America/Chicago;
    we attach the right offset by comparing local vs utc fields.
    """
    if not local:
        return None
    try:
        local_dt = dt.datetime.strptime(local, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

    if utc:
        try:
            utc_dt = dt.datetime.strptime(utc, "%Y-%m-%d %H:%M:%S")
            offset = local_dt - utc_dt  # local = utc + offset
            total_min = int(offset.total_seconds() // 60)
            sign = "+" if total_min >= 0 else "-"
            total_min = abs(total_min)
            hh, mm = divmod(total_min, 60)
            return local_dt.strftime("%Y-%m-%dT%H:%M:%S") + f"{sign}{hh:02d}:{mm:02d}"
        except ValueError:
            pass
    # Fallback: assume Central Daylight (-05:00). Good enough; app re-parses.
    return local_dt.strftime("%Y-%m-%dT%H:%M:%S") + "-05:00"
