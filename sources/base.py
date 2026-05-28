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

import re
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
    ("sports",  ["game", "match", "run", "race", "sport", "basketball", "soccer", "fitness", "tournament"]),
    ("family",  ["family"]),
]

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(raw: str) -> str:
    """Turn an HTML fragment into readable plain text."""
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
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
