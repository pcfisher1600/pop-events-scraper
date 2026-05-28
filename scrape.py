#!/usr/bin/env python3
"""Pop events scraper — orchestrator.

Runs every registered source, merges + de-dupes + sorts the results, and
writes `events.json`. Designed to be safe under partial failure: a source
that throws is logged and skipped, never crashes the run.

Usage:
    python3 scrape.py            # writes events.json
    python3 scrape.py --dry-run  # prints summary, writes nothing
"""

from __future__ import annotations

import sys
import json
import datetime as dt

from sources import science_museum
# Future sources get appended here as they're built (Phase A step 5+).
SOURCES = [
    science_museum,
]

OUTPUT = "events.json"


def main() -> int:
    dry = "--dry-run" in sys.argv
    all_events: list[dict] = []

    for src in SOURCES:
        name = getattr(src, "SOURCE_NAME", src.__name__)
        try:
            events = src.fetch()
            all_events.extend(events)
        except Exception as exc:  # noqa: BLE001
            print(f"[orchestrator] source '{name}' failed entirely: {exc}")

    # De-dupe by id (sources should already be unique, but be safe).
    seen, deduped = set(), []
    for ev in all_events:
        if ev["id"] in seen:
            continue
        seen.add(ev["id"])
        deduped.append(ev)

    # Sort chronologically by start date.
    deduped.sort(key=lambda e: e.get("startDate", ""))

    payload = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sourceCount": len(SOURCES),
        "eventCount": len(deduped),
        "events": deduped,
    }

    print(f"[orchestrator] {len(deduped)} events from {len(SOURCES)} source(s)")

    if dry:
        for ev in deduped[:10]:
            print(f"  {ev['startDate'][:16]}  {ev['category']:8}  {ev['title'][:50]}")
        print("[orchestrator] --dry-run: not writing file")
        return 0

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[orchestrator] wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
