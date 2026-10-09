"""Command-line entry point for the research workflow scaffold."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from reddit_pipeline import collect, load_policies

CODE_ROOT = Path(__file__).resolve().parent.parent
REQUIRED_DIRS = (
    "config",
    "src",
    "data/raw",
    "data/interim",
    "data/processed",
    "outputs/figures",
    "outputs/tables",
)


def show_status() -> int:
    """Report which planned folders currently exist."""
    missing = []
    for relative in REQUIRED_DIRS:
        exists = (CODE_ROOT / relative).is_dir()
        print(f"{'OK     ' if exists else 'MISSING'} {relative}")
        if not exists:
            missing.append(relative)
    if missing:
        return 1
    print("\nProject folders ready. Use reddit-collect --dry-run to inspect a collection plan.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("status", help="Check the project folder structure")
    reddit = subcommands.add_parser("reddit-collect", help="Discover and collect Reddit posts and comments")
    reddit.add_argument("--policies", type=Path, required=True, help="JSON or CSV policy table")
    reddit.add_argument("--out", type=Path, help="New output directory; defaults to a timestamped run folder")
    reddit.add_argument("--candidate-file", type=Path, help="Optional TXT, CSV, or JSON of discovered post URLs")
    reddit.add_argument("--max-search-queries", type=int, default=20)
    reddit.add_argument("--max-posts", type=int, default=100)
    reddit.add_argument("--max-reddit-requests", type=int, default=100)
    reddit.add_argument("--delay", type=float, default=2.0, help="Seconds between Reddit requests")
    reddit.add_argument("--dry-run", action="store_true", help="Show plan without network calls or files")
    args = parser.parse_args()

    if args.command == "status":
        return show_status()
    if args.command == "reddit-collect":
        if min(args.max_search_queries, args.max_posts, args.max_reddit_requests) < 0 or args.delay < 0:
            parser.error("limits and delay must be nonnegative")
        try:
            output_dir = args.out or CODE_ROOT / "data/raw/reddit/runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            result = collect(load_policies(args.policies), output_dir, args.max_search_queries,
                             args.max_posts, args.max_reddit_requests, args.candidate_file,
                             args.dry_run, args.delay)
        except (ValueError, OSError, json.JSONDecodeError) as error:
            parser.error(str(error))
        print(json.dumps(result, indent=2))
        return 0
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
