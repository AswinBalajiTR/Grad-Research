#!/usr/bin/env python3
"""Collect YouTube comments without an API key by using yt-dlp."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime, time as dt_time, timezone
from pathlib import Path
from typing import Any

try:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError
except ModuleNotFoundError:  # Allows --help and schema tests before dependencies are installed.
    YoutubeDL = None

    class DownloadError(Exception):
        pass


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "data/youtube"

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries-file", default=str(PROJECT_ROOT / "code/youtube/search_queries.txt"))
    parser.add_argument("--start-date", default="2025-01-20")
    parser.add_argument("--end-date", help="Inclusive YYYY-MM-DD; default is today")
    parser.add_argument("--max-videos", type=int, default=60)
    parser.add_argument("--max-comments-per-video", type=int, default=100)
    parser.add_argument("--time-budget-seconds", type=int, default=180)
    parser.add_argument("--output", default=str(DATA_ROOT / "processed/youtube_comments.csv"))
    parser.add_argument("--videos-output", default=str(DATA_ROOT / "processed/youtube_videos.csv"))
    return parser.parse_args()


def utc_bound(value: str, end: bool = False) -> datetime:
    day = datetime.strptime(value, "%Y-%m-%d").date()
    return datetime.combine(day, dt_time.max if end else dt_time.min, tzinfo=timezone.utc)


def read_queries(path: Path) -> list[str]:
    queries = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not queries:
        raise ValueError(f"No search queries found in {path}")
    return queries


def discover_videos(queries: list[str], max_videos: int) -> list[dict[str, str]]:
    """Find up to max_videos unique videos using several targeted searches."""
    if YoutubeDL is None:
        raise RuntimeError("yt-dlp is not installed. Run: pip install -r requirements.txt")
    if max_videos < 1:
        raise ValueError("--max-videos must be positive")
    per_query = max(10, (max_videos * 2 + len(queries) - 1) // len(queries))
    options = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "ignoreerrors": True,
        "socket_timeout": 30,
    }
    found: dict[str, dict[str, str]] = {}
    with YoutubeDL(options) as ydl:
        for query in queries:
            try:
                result = ydl.extract_info(f"ytsearch{per_query}:{query}", download=False) or {}
            except DownloadError as exc:
                print(f"Search failed for {query!r}: {exc}", file=sys.stderr)
                continue
            for entry in result.get("entries") or []:
                if not entry:
                    continue
                video_id = str(entry.get("id") or "")
                if not video_id or video_id in found:
                    continue
                found[video_id] = {
                    "video_id": video_id,
                    "video_title": str(entry.get("title") or ""),
                    "channel_title": str(entry.get("channel") or entry.get("uploader") or ""),
                    "video_published_at": str(entry.get("upload_date") or ""),
                    "matched_query": query,
                    "video_url": f"https://www.youtube.com/watch?v={video_id}",
                }
                if len(found) >= max_videos:
                    return list(found.values())
    return list(found.values())


def comment_datetime(comment: dict[str, Any]) -> datetime | None:
    timestamp = comment.get("timestamp")
    if timestamp is not None:
        try:
            return datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            pass
    date_text = str(comment.get("time_text") or "")
    try:
        return datetime.fromisoformat(date_text.replace("Z", "+00:00"))
    except ValueError:
        return None


def extract_video(
    video: dict[str, str], max_comments: int
) -> tuple[dict[str, Any] | None, str | None]:
    """Retrieve metadata and a bounded sample of public comments."""
    if YoutubeDL is None:
        return None, "yt-dlp is not installed. Run: pip install -r requirements.txt"
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "getcomments": True,
        "ignoreerrors": False,
        "socket_timeout": 15,
        "retries": 1,
        "extractor_retries": 1,
        "sleep_interval_requests": 0.15,
        "extractor_args": {
            "youtube": {
                "comment_sort": ["new"],
                "max_comments": [
                    f"{max_comments},{max(1, max_comments * 3 // 4)},"
                    f"{max(0, max_comments // 4)},5"
                ],
            }
        },
    }
    try:
        with YoutubeDL(options) as ydl:
            return ydl.extract_info(video["video_url"], download=False), None
    except DownloadError as exc:
        return None, str(exc)


def main() -> int:
    args = parse_args()
    if args.max_comments_per_video < 1:
        raise ValueError("--max-comments-per-video must be positive")
    if args.time_budget_seconds < 30:
        raise ValueError("--time-budget-seconds must be at least 30")
    started_at = time.monotonic()
    start = utc_bound(args.start_date)
    end = utc_bound(args.end_date, end=True) if args.end_date else datetime.now(timezone.utc)
    if end < start:
        raise ValueError("--end-date must be on or after --start-date")

    queries = read_queries(Path(args.queries_file))
    videos = discover_videos(queries, args.max_videos)
    if not videos:
        print("No videos were discovered. YouTube may be blocking the current guest session.", file=sys.stderr)
        return 2

    output = Path(args.output)
    videos_output = Path(args.videos_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    videos_output.parent.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    rows: list[dict[str, str]] = []
    audit_rows: list[dict[str, str]] = []
    for index, video in enumerate(videos, start=1):
        if time.monotonic() - started_at >= args.time_budget_seconds:
            print(
                f"Stopped at the {args.time_budget_seconds}-second collection budget.",
                file=sys.stderr,
            )
            break
        info, error = extract_video(video, args.max_comments_per_video)
        audit = dict(video)
        audit["collection_status"] = "failed" if error else "collected"
        audit["collection_error"] = error or ""
        audit["comments_collected"] = "0"
        if info:
            upload_date = str(info.get("upload_date") or "")
            audit["video_published_at"] = upload_date
            if upload_date:
                try:
                    published = datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=timezone.utc)
                    if published < start or published > end:
                        audit["collection_status"] = "outside_date_range"
                        audit_rows.append(audit)
                        continue
                except ValueError:
                    pass
            collected_here = 0
            for comment in info.get("comments") or []:
                comment_id = str(comment.get("id") or "")
                published = comment_datetime(comment)
                comment_text = str(comment.get("text") or "").strip()
                if not comment_id or comment_id in seen or not published or not comment_text:
                    continue
                if start <= published <= end:
                    rows.append(
                        {
                            "date": published.isoformat().replace("+00:00", "Z"),
                            "youtube_comment": comment_text,
                        }
                    )
                    seen.add(comment_id)
                    collected_here += 1
            audit["comments_collected"] = str(collected_here)
        audit_rows.append(audit)
        print(
            f"Processed video {index}/{len(videos)}; total comments: {len(rows):,}",
            file=sys.stderr,
        )

    rows.sort(key=lambda row: row["date"])
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "youtube_comment"])
        writer.writeheader()
        writer.writerows(rows)

    video_fields = [
        "video_id", "video_title", "channel_title", "video_published_at",
        "matched_query", "video_url", "collection_status", "collection_error",
        "comments_collected",
    ]
    with videos_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=video_fields)
        writer.writeheader()
        writer.writerows(audit_rows)

    if not rows:
        print(
            "Videos were found, but no accessible comments matched the date range. "
            "See youtube_videos.csv for collection errors.",
            file=sys.stderr,
        )
        return 2
    print(f"Saved {len(rows):,} comments from {len(videos):,} videos to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
