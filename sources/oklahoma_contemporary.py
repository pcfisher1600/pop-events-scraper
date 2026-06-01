"""Oklahoma Contemporary Arts Center — WordPress `event` CPT (Meta Box dates).

The events page is JS-rendered and the detail pages carry no Event JSON-LD, but
the standard WP REST `event` post type returns each event's dates inline under a
**`meta_box`** object (Meta Box plugin), no key required:

    GET /wp-json/wp/v2/event?per_page=100&acf_format=standard

Relevant `meta_box` fields:
  _global_start_date  "2026-08-01"          (always present)
  _global_start_time  "1:00 pm"  | ""       ("" => all-day)
  _global_end_date    "2026-08-29"
  _global_end_time    "5:00 pm"  | ""
  use_custom_schedule "1" | "0"             (multi-session events)
  custom_schedule[]   [{event_date, start_time, end_time, event_time_desc}]
  event_description   HTML
  event_type_select[] ["Performance", ...]  (category hint)

One paginated call, clean ISO dates — lower-maintenance than our HTML/JSON-LD
scrapers. robots.txt allows `/wp-json/` (Crawl-delay 10, trivial here: 1 call).
"""

from __future__ import annotations

import re
import datetime as dt
import requests

from .base import strip_html, guess_category, truncate

SOURCE_NAME = "Oklahoma Contemporary"
API = "https://oklahomacontemporary.org/wp-json/wp/v2/event"
HORIZON_DAYS = 120         # arts events are scheduled further out; widen the window
MAX_EVENTS = 40
DEFAULT_OFFSET = "-05:00"  # America/Chicago (CDT); the data carries no tz
HEADERS = {"User-Agent": "pop-events-scraper/1.0 (+family calendar; contact via repo)"}

_TIME_RE = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?\s*$", re.I)


def fetch() -> list[dict]:
    try:
        resp = requests.get(
            API,
            params={"per_page": 100, "acf_format": "standard", "status": "publish"},
            headers=HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
        posts = resp.json()
    except Exception as exc:  # noqa: BLE001 — source failure must not kill the run
        print(f"[{SOURCE_NAME}] fetch failed: {exc}")
        return []

    today = dt.date.today().isoformat()
    end = (dt.date.today() + dt.timedelta(days=HORIZON_DAYS)).isoformat()

    out: list[dict] = []
    for post in posts:
        mapped = _map(post)
        if not mapped:
            continue
        # keep events active within the window (multi-month runs are common)
        if mapped["endDate"][:10] < today or mapped["startDate"][:10] > end:
            continue
        out.append(mapped)

    out.sort(key=lambda e: e["startDate"])
    out = out[:MAX_EVENTS]
    print(f"[{SOURCE_NAME}] collected {len(out)} events")
    return out


def _map(post: dict) -> dict | None:
    mb = post.get("meta_box") or {}
    title = strip_html((post.get("title") or {}).get("rendered", "")).strip()
    start_date = (mb.get("_global_start_date") or "").strip()
    if not title or not start_date:
        return None

    # A custom multi-session schedule overrides the global start time with its
    # first row; otherwise use the global start/end times.
    start_time = (mb.get("_global_start_time") or "").strip()
    end_date = (mb.get("_global_end_date") or "").strip() or start_date
    end_time = (mb.get("_global_end_time") or "").strip()

    if str(mb.get("use_custom_schedule")) == "1":
        rows = mb.get("custom_schedule") or []
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            first = rows[0]
            start_date = (first.get("event_date") or start_date).strip()
            start_time = (first.get("start_time") or "").strip()
            end_time = (first.get("end_time") or "").strip()
            end_date = start_date  # a session is same-day

    start_iso, all_day = _iso(start_date, start_time)
    if not start_iso:
        return None
    end_iso, _ = _iso(end_date, end_time)
    end_iso = end_iso or start_iso

    types = mb.get("event_type_select") or []
    type_str = " ".join(t for t in types if isinstance(t, str))
    desc = truncate(strip_html(mb.get("event_description", "")) or
                    strip_html((post.get("excerpt") or {}).get("rendered", "")))

    cost = ""
    if (mb.get("ticket_registration_text") or "").strip().lower() in ("free", "free admission"):
        cost = "Free"

    return {
        "id": f"oca-{post.get('id')}",
        "source": SOURCE_NAME,
        "sourceURL": post.get("link", ""),
        "title": title,
        "description": desc,
        "startDate": start_iso,
        "endDate": end_iso,
        "allDay": all_day,
        "venueName": _venue(mb.get("event_location")),
        "city": "Oklahoma City",
        "imageURL": "",  # featured media isn't exposed inline; left blank
        "category": guess_category(title, type_str),
        "cost": cost,
    }


def _venue(loc) -> str:
    """`event_location` is either [] or a taxonomy dict carrying a room name
    (e.g. a specific gallery). Prefer the name, fall back to the center."""
    if isinstance(loc, dict):
        name = strip_html(loc.get("name", "")).strip()
        if name:
            return f"{SOURCE_NAME} — {name}"
    return SOURCE_NAME


def _iso(date_str: str, time_str: str) -> tuple[str | None, bool]:
    """Combine a 'YYYY-MM-DD' date with an optional '1:00 pm' time into an
    ISO-8601 stamp with the Central offset. Empty/garbled time => all-day.
    """
    if not date_str:
        return None, False
    try:
        dt.date.fromisoformat(date_str)
    except ValueError:
        return None, False

    m = _TIME_RE.match(time_str or "")
    if not m:
        return f"{date_str}T00:00:00{DEFAULT_OFFSET}", True
    hour = int(m.group(1)) % 12
    if m.group(3).lower() == "p":
        hour += 12
    minute = int(m.group(2) or 0)
    return f"{date_str}T{hour:02d}:{minute:02d}:00{DEFAULT_OFFSET}", False
