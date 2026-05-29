"""Shared types and helpers for Pop event sources.

Every source produces a list of dicts matching the `events.json` schema the
Pop iOS app expects. Keep the schema stable — the app decodes it directly into
`AroundTownEvent`.

Schema (one event):
    {
      "id":          str,   # globally unique, source-prefixed (e.g. "smo-10004703")
      "source":      str,   # human label, e.g. "Science Museum Oklahoma"
      "sourceURL":   str,   # link back to the event page
      "title":       str,
      "description": str,   # plain text, HTML stripped, may be ""
      "startDate":   str,   # ISO 8601 with offset, e.g. "2026-04-28T09:00:00-05:00"
      "endDate":     str,   # ISO 8601 with offset (== startDate if unknown)
      "allDay":      bool,
      "venueName":   str,   # may be ""
      "city":        str,   # may be ""
      "imageURL":    str,   # may be ""
      "category":    str,   # one of CATEGORY_KEYS below
      "cost":        str    # freeform ("", "Free", "$12", etc.)
    }
"""

from __future__ import annotations

import re
import json
from html import unescape

# Must match the EventCategory enum case names in the Pop app (Brand.swift).
CATEGORY_KEYS = {"family", "kids", "music", "food", "outdoor", "art", "sports", "other"}

# Keyword → category. First match wins; order matters (specific before generic).
_CATEGORY_RULES = [
    ("kids",    ["kid", "child", "family-friendly", "story time", "storytime", "toddler", "youth", "tinker", "camp"]),
    ("music",   ["concert", "music", "band", "symphony", "jazz", "choir", "recital", "dj"]),
    ("food",    ["food", "dining", "brunch", "dinner", "tasting", "wine", "beer", "culinary", "cook"]),
    ("outdoor", ["park", "garden", "hike", "walk", "trail", "outdoor", "festival", "market", "yoga"]),
    ("art",     ["art", "gallery", "exhibit", "museum", "paint", "craft", "theatre", "theater", "film", "culture"]),
    ("sports",  ["game", "match", "run", "race", "sport", "basketball", "soccer", "fitness", "tournament", "zumba", "pilates", "bootcamp", "tai chi"]),
    ("family",  ["family"]),
]

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(raw: str) -> str:
    """Turn an HTML fragment into readable plain text.

    Unescape first so entity-encoded markup (e.g. MEC's double-escaped
    `&lt;!-- wp:heading --&gt;` Gutenberg blocks) becomes real tags we can
    strip, then unescape again for any remaining entities in the text.
    """
    if not raw:
        return ""
    text = unescape(raw)
    text = _TAG_RE.sub(" ", text)
    text = unescape(text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def guess_category(*texts: str) -> str:
    """Best-effort map of free text to one of our 8 categories.

    Searches title + venue + source categories. Defaults to 'family' since
    every source we scrape is a family-friendly OKC venue.
    """
    haystack = " ".join(t for t in texts if t).lower()
    for key, words in _CATEGORY_RULES:
        if any(w in haystack for w in words):
            return key
    return "family"


def truncate(text: str, limit: int = 500) -> str:
    """Cap description length so events.json stays small."""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"  # ellipsis


# ---------------------------------------------------------------------------
# schema.org JSON-LD helpers — shared by the WordPress/MEC sources.
# Both Scissortail Park and Myriad Gardens run Modern Events Calendar (MEC),
# which emits a `<script type="application/ld+json">` Event object per event.
# ---------------------------------------------------------------------------

_LD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.S | re.I,
)
_OFFSET_RE = re.compile(r"(Z|[+-]\d{2}:?\d{2})$")
_DATETIME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})(:\d{2})?$")

# Central time. The venues are all in OKC; MEC sometimes omits the offset.
CENTRAL_OFFSET = "-05:00"


def parse_jsonld_events(html: str) -> list[dict]:
    """Return every schema.org Event object embedded in a page's JSON-LD.

    Handles bare objects, arrays, and `@graph` containers, and ignores the
    site-level blocks (WebSite/Organization/etc.) MEC pages also emit.
    """
    out: list[dict] = []
    for block in _LD_RE.findall(html or ""):
        try:
            data = json.loads(block.strip())
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and "@graph" in data:
            items = data["@graph"]
        elif isinstance(data, list):
            items = data
        else:
            items = [data]
        for it in items:
            if isinstance(it, dict) and "Event" in str(it.get("@type", "")):
                out.append(it)
    return out


def schema_date_to_iso(value: str, default_offset: str = CENTRAL_OFFSET) -> tuple[str | None, bool]:
    """Normalize a schema.org date/datetime to ISO-8601 with an offset.

    Returns (iso, all_day). Date-only values ("2026-05-30") become an
    all-day midnight stamp; datetimes missing an offset get the Central one.
    """
    if not value:
        return None, False
    v = value.strip()
    if "T" not in v:  # date only → all-day
        return f"{v}T00:00:00{default_offset}", True
    if _OFFSET_RE.search(v):  # already carries a timezone
        return v, False
    m = _DATETIME_RE.match(v)  # has time, missing offset
    if m:
        seconds = m.group(2) or ":00"
        return f"{m.group(1)}{seconds}{default_offset}", False
    return f"{v}{default_offset}", False


def offers_to_cost(offers: dict) -> str:
    """Turn a schema.org `offers` block into a freeform cost string.

    "" / missing → "", a 0 price → "Free", otherwise a currency-prefixed
    amount. Non-numeric prices pass through unchanged.
    """
    if not isinstance(offers, dict):
        return ""
    raw = offers.get("price")
    price = "" if raw is None else str(raw).strip()
    if price == "":
        return ""
    try:
        val = float(price)
    except ValueError:
        return price  # already human-readable, e.g. "Donations welcome"
    if val == 0:
        return "Free"
    currency = (offers.get("priceCurrency") or "$").strip()
    symbol = "$" if currency in ("$", "USD") else f"{currency} "
    return f"{symbol}{int(val)}" if val == int(val) else f"{symbol}{val:.2f}"
