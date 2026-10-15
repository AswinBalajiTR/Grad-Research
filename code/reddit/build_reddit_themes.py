#!/usr/bin/env python3
"""Build an anonymous aggregate of concern themes from reviewed Reddit comments."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
from concern_themes import comment_themes


def aggregate(source: Path) -> tuple[Counter, int]:
    counts: Counter = Counter()
    seen: set[tuple[str, str]] = set()
    with source.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            key = (row["event_id"], row["comment_id"])
            if key in seen:
                continue
            seen.add(key)
            month = row["posted_utc"][:7]
            for theme in comment_themes(row.get("body", "")):
                counts[(month, row["event_id"], theme)] += 1
    return counts, len(seen)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=PROJECT_ROOT / "data/reddit/processed/policy_20261013/all_reviewed_comments.jsonl")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data/reddit/processed/reddit_theme_counts.csv")
    args = parser.parse_args()
    counts, records = aggregate(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["month", "event_id", "theme", "comments"])
        for key, count in sorted(counts.items()):
            writer.writerow([*key, count])
    print(f"Wrote {len(counts)} aggregate rows from {records} reviewed comment-event records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
