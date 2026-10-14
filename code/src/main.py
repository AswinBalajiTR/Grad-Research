

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from reddit_scrapper import analyze_sentiment, collect, load_policies, plan_policy_batch, rebuild_policy_dataset

CODE_ROOT = Path(__file__).resolve().parent.parent
REQUIRED_DIRS = (
    "config",
    "src",
    "data/raw",
    "data/interim",
    "data/processed",
    "outputs",
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
    print("\nProject folders ready. Use policy-plan to inspect the policy batch.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("status", help="Check the project folder structure")
    plan = subcommands.add_parser("policy-plan", help="Build the dated policy manifest and search jobs without network calls")
    plan.add_argument("--policies", type=Path, default=CODE_ROOT / "config/policy_events_to_verify.csv")
    plan.add_argument("--manifest", type=Path, default=CODE_ROOT / "config/policy_batch_scope.json")
    plan.add_argument("--jobs", type=Path, default=CODE_ROOT / "config/policy_search_jobs.jsonl")
    rebuild = subcommands.add_parser("policy-rebuild", help="Rebuild reviewed records from saved raw files; no network calls")
    rebuild.add_argument("--policies", type=Path, default=CODE_ROOT / "config/policy_events_to_verify.csv")
    rebuild.add_argument("--raw", type=Path, default=CODE_ROOT / "data/raw/reddit/policy_20261013")
    rebuild.add_argument("--interim", type=Path, default=CODE_ROOT / "data/interim/reddit_policy_20261013")
    rebuild.add_argument("--processed", type=Path, default=CODE_ROOT / "data/processed/reddit_policy_20261013")
    rebuild.add_argument("--live-review", type=Path, default=CODE_ROOT / "config/reviewed_policy_posts.csv")
    rebuild.add_argument("--archive-review", type=Path, default=CODE_ROOT / "config/reviewed_archive_policy_posts.csv")
    rebuild.add_argument("--manifest", type=Path, default=CODE_ROOT / "config/policy_batch_scope.json")
    rebuild.add_argument("--jobs", type=Path, default=CODE_ROOT / "config/policy_search_jobs.jsonl")
    rebuild.add_argument("--coverage", type=Path, default=CODE_ROOT / "outputs/reddit_policy_coverage.csv")
    sentiment = subcommands.add_parser("sentiment-analyze", help="Label reviewed comments with a local Ollama model")
    sentiment.add_argument("--manifest", type=Path, default=CODE_ROOT / "config/policy_batch_scope.json")
    sentiment.add_argument("--processed", type=Path, default=CODE_ROOT / "data/processed/reddit_policy_20261013")
    sentiment.add_argument("--interim", type=Path, default=CODE_ROOT / "data/interim/reddit_policy_20261013")
    sentiment.add_argument("--model", default="qwen2.5:7b")
    sentiment.add_argument("--batch-size", type=int, default=6)
    sentiment.add_argument("--review-overrides", type=Path, default=CODE_ROOT / "config/sentiment_review_overrides.csv")
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
    if args.command == "sentiment-analyze":
        try:
            result = analyze_sentiment(args.manifest, args.processed, args.interim, args.model,
                                       args.batch_size, args.review_overrides)
        except (ValueError, KeyError, OSError, json.JSONDecodeError) as error:
            parser.error(str(error))
        print(json.dumps(result, indent=2))
        return 0
    if args.command in {"policy-plan", "policy-rebuild"}:
        try:
            if args.command == "policy-plan":
                result = plan_policy_batch(args.policies, args.manifest, args.jobs)
            else:
                result = rebuild_policy_dataset(args.policies, args.raw, args.interim, args.processed,
                                                args.live_review, args.archive_review,
                                                args.manifest, args.jobs, args.coverage)
        except (ValueError, KeyError, OSError, json.JSONDecodeError) as error:
            parser.error(str(error))
        print(json.dumps(result, indent=2))
        return 0
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
