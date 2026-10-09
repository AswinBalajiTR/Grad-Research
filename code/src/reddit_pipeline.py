"""Policy-window Reddit discovery and collection; Python standard library only."""
from __future__ import annotations

import csv
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

POST_PATH = re.compile(r"^/r/([A-Za-z0-9_]+)/comments/([A-Za-z0-9]+)/?", re.I)
USER_AGENT = "PolicyWindowCollector/0.1 (personal research; contact via repository owner)"
DEFAULT_SUBREDDITS = ["f1visa", "Indians_StudyAbroad", "gradadmissions", "usvisascheduling"]


def load_tavily_key():
    """Read a key from the environment or the ignored code/.env file."""
    if os.getenv("TAVILY_API_KEY"):
        return os.environ["TAVILY_API_KEY"]
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("TAVILY_API_KEY="):
                return line.partition("=")[2].strip().strip("\"'")
    return None


def _list(value):
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return [x.strip() for x in str(value or "").split("|") if x.strip()]


def load_policies(path: Path):
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("policies", []) if isinstance(data, dict) else data
    if not isinstance(rows, list) or not rows:
        raise ValueError("Policy file must contain at least one policy")
    policies = []
    seen = set()
    for row in rows:
        event_id = str(row.get("event_id", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", event_id) or event_id in seen:
            raise ValueError(f"Invalid or repeated event_id: {event_id!r}")
        seen.add(event_id)
        announced = date.fromisoformat(row["announcement_date"])
        raw_days = row.get("days_after")
        days_after = 7 if raw_days is None or raw_days == "" else int(raw_days)
        if days_after < 0 or days_after > 30:
            raise ValueError("days_after must be between 0 and 30")
        keywords = _list(row.get("keywords"))
        if not keywords:
            raise ValueError(f"{event_id}: keywords required")
        subreddits = _list(row.get("subreddits")) or DEFAULT_SUBREDDITS
        if any(not re.fullmatch(r"[A-Za-z0-9_]+", sub) for sub in subreddits):
            raise ValueError(f"{event_id}: invalid subreddit")
        policies.append({"event_id": event_id, "policy_name": row.get("policy_name", ""),
                         "announcement_date": announced.isoformat(), "days_after": days_after,
                         "keywords": keywords, "subreddits": subreddits,
                         "window_start_utc": announced.isoformat() + "T00:00:00Z",
                         "window_end_exclusive_utc": (announced + timedelta(days=days_after + 1)).isoformat() + "T00:00:00Z"})
    return policies


def search_plan(policies, max_queries):
    plan = []
    for p in policies:
        for keyword in p["keywords"]:
            for sub in p["subreddits"]:
                if len(plan) >= max_queries:
                    return plan
                plan.append({"event_id": p["event_id"], "query":
                             f'site:reddit.com/r/{sub}/comments/ "{keyword}"',
                             "subreddit": sub,
                             "start_date": p["announcement_date"],
                             "end_date": p["window_end_exclusive_utc"][:10]})
    return plan


def planned_query_count(policies):
    return sum(len(p["keywords"]) * len(p["subreddits"]) for p in policies)


def canonical_post(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in {"reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com", "np.reddit.com"}:
        return None
    match = POST_PATH.match(parsed.path)
    if not match:
        return None
    sub, post_id = match.groups()
    return post_id.lower(), f"https://www.reddit.com/r/{sub}/comments/{post_id.lower()}/"


def _request_json(url, payload=None, api_key=None, delay=0):
    if delay:
        time.sleep(delay)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(url, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
    for attempt in range(3):
        try:
            with urlopen(request, timeout=25) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise RuntimeError(f"HTTP {error.code} from {urlparse(url).hostname}") from error
            retry_after = error.headers.get("Retry-After", "")
            time.sleep(min(30, int(retry_after)) if retry_after.isdigit() else 2 ** (attempt + 1))
        except URLError as error:
            if attempt == 2:
                raise RuntimeError(f"Network error from {urlparse(url).hostname}: {error.reason}") from error
            time.sleep(2 ** (attempt + 1))


def tavily_search(item, api_key):
    response = _request_json("https://api.tavily.com/search", {
        "query": item["query"], "search_depth": "basic", "max_results": 20,
        "include_domains": ["reddit.com"], "include_answer": False,
        "include_raw_content": False, "include_usage": True,
        "start_date": item["start_date"], "end_date": item["end_date"],
    }, api_key=api_key)
    return response.get("results", []), response.get("usage", {}).get("credits", 1)


def read_candidates(path, policies):
    """TXT: URLs for one policy. CSV: event_id,url. JSON: objects or URLs."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    elif suffix == ".json":
        rows = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(rows, dict):
            rows = rows.get("candidates", [])
    else:
        rows = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
    if not isinstance(rows, list):
        raise ValueError("Candidate file must contain a list")
    out = []
    for row in rows:
        if isinstance(row, str):
            if len(policies) != 1:
                raise ValueError("Plain URL candidates require exactly one policy")
            out.append({"event_id": policies[0]["event_id"], "url": row, "source": "candidate_file"})
        else:
            out.append({"event_id": row["event_id"], "url": row["url"], "source": "candidate_file"})
    return out


def parse_reddit(data, policy, canonical):
    if not isinstance(data, list) or len(data) < 2:
        raise ValueError("Unexpected Reddit response shape")
    post = data[0]["data"]["children"][0]["data"]
    created = datetime.fromtimestamp(post["created_utc"], timezone.utc)
    start = datetime.fromisoformat(policy["window_start_utc"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(policy["window_end_exclusive_utc"].replace("Z", "+00:00"))
    def normalize(value):
        words = re.sub(r"[^\w]+", " ", value.casefold())
        return re.sub(r"\bf\s+1\b", "f1", words).strip()

    post_text = f'{post.get("title", "")} {post.get("selftext", "")}'
    text = f" {normalize(post_text)} "
    matches = [keyword for keyword in policy["keywords"] if f" {normalize(keyword)} " in text]
    if not start <= created < end:
        status = "outside_window"
    elif not matches:
        status = "review_relevance"
    else:
        status = "matched"
    base = {"event_id": policy["event_id"], "post_id": post["id"], "url": canonical,
            "subreddit": post.get("subreddit"), "created_utc": created.isoformat(),
            "title": post.get("title"), "selftext": post.get("selftext"),
            "author": post.get("author"), "score": post.get("score"),
            "num_comments_reported": post.get("num_comments"), "matched_keywords": matches,
            "status": status, "retrieved_utc": datetime.now(timezone.utc).isoformat()}
    comments, unresolved = [], []
    stack = list(reversed(data[1].get("data", {}).get("children", [])))
    while stack:
        node = stack.pop()
        kind, item = node.get("kind"), node.get("data", {})
        if kind == "more":
            unresolved.append({"parent_id": item.get("parent_id"), "count": item.get("count", len(item.get("children", [])))})
            continue
        if kind != "t1":
            continue
        timestamp = datetime.fromtimestamp(item["created_utc"], timezone.utc)
        comments.append({"event_id": policy["event_id"], "post_id": post["id"],
                         "comment_id": item.get("id"), "parent_id": item.get("parent_id"),
                         "author": item.get("author"), "body": item.get("body"),
                         "score": item.get("score"), "created_utc": timestamp.isoformat(),
                         "within_policy_window": start <= timestamp < end,
                         "retrieved_utc": base["retrieved_utc"]})
        replies = item.get("replies")
        if isinstance(replies, dict):
            stack.extend(reversed(replies.get("data", {}).get("children", [])))
    base["comments_retrieved"] = len(comments)
    base["unresolved_more_nodes"] = unresolved
    base["comments_complete"] = not unresolved and (post.get("num_comments") or 0) <= len(comments)
    return base, comments


def _write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def collect(policies, output_dir, max_queries=20, max_posts=100, max_requests=100,
            candidate_file=None, dry_run=False, delay=2.0):
    plan = [] if candidate_file else search_plan(policies, max_queries)
    total_queries = 0 if candidate_file else planned_query_count(policies)
    estimate = {"search_queries_needed_for_full_plan": total_queries,
                "search_queries_with_current_cap": len(plan),
                "search_plan_truncated": len(plan) < total_queries,
                "tavily_basic_credits_planned": len(plan),
                "reddit_requests_max": max_requests, "posts_max": max_posts,
                "cash_cost_if_within_tavily_free_tier_usd": 0}
    if dry_run:
        return {"estimate": estimate, "queries": plan, "network_calls": 0}
    if estimate["search_plan_truncated"]:
        raise ValueError(f"Search plan needs {total_queries} queries but --max-search-queries is {max_queries}; raise the cap after checking the dry run")
    api_key = None if candidate_file else load_tavily_key()
    if not candidate_file and not api_key:
        raise ValueError("TAVILY_API_KEY is required in the environment or code/.env; or use --candidate-file")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"Output directory already contains files: {output_dir}; choose a new --out path")
    output_dir.mkdir(parents=True, exist_ok=True)
    policy_map = {p["event_id"]: p for p in policies}
    candidates, search_log, errors = [], [], []
    credits = 0
    if candidate_file:
        candidates = read_candidates(candidate_file, policies)
    else:
        for item in plan:
            try:
                results, used = tavily_search(item, api_key)
                credits += used
                found_at = datetime.now(timezone.utc).isoformat()
                search_log.append({**item, "results": len(results), "credits": used, "searched_utc": found_at})
                candidates.extend({"event_id": item["event_id"], "url": result.get("url", ""),
                                   "source": "tavily", "query": item["query"],
                                   "subreddit": item["subreddit"], "discovered_utc": found_at} for result in results)
            except (RuntimeError, ValueError, KeyError) as error:
                errors.append({"stage": "search", "query": item["query"], "error": str(error)})
                search_log.append({**item, "error": str(error)})
    unique, seen = [], set()
    rejected_other_subreddit = 0
    for candidate in candidates:
        canonical = canonical_post(candidate.get("url", ""))
        if candidate["event_id"] not in policy_map or canonical is None:
            continue
        post_id, url = canonical
        actual_subreddit = POST_PATH.match(urlparse(url).path).group(1)
        expected_subreddit = candidate.get("subreddit")
        allowed_subreddits = {sub.casefold() for sub in policy_map[candidate["event_id"]]["subreddits"]}
        if actual_subreddit.casefold() not in allowed_subreddits or (
            expected_subreddit and actual_subreddit.casefold() != expected_subreddit.casefold()
        ):
            rejected_other_subreddit += 1
            continue
        key = (candidate["event_id"], post_id)
        if key not in seen:
            seen.add(key)
            unique.append({**candidate, "post_id": post_id, "canonical_url": url})
    posts, comments, reviewed = [], [], []
    requests = 0
    for candidate in unique:
        if requests >= max_requests or len(posts) >= max_posts:
            break
        requests += 1
        try:
            data = _request_json(candidate["canonical_url"].rstrip("/") + ".json?raw_json=1&limit=500&sort=old", delay=delay)
            post, children = parse_reddit(data, policy_map[candidate["event_id"]], candidate["canonical_url"])
            post["discovered_by"] = candidate["source"]
            post["discovery_query"] = candidate.get("query")
            if post["status"] == "matched":
                posts.append(post)
                comments.extend(children)
            else:
                reviewed.append(post)
        except (RuntimeError, ValueError, KeyError, IndexError, TypeError) as error:
            errors.append({"stage": "reddit", "url": candidate["canonical_url"], "error": str(error)})
    _write_jsonl(output_dir / "posts.jsonl", posts)
    _write_jsonl(output_dir / "comments.jsonl", comments)
    _write_jsonl(output_dir / "review.jsonl", reviewed)
    _write_jsonl(output_dir / "candidates.jsonl", unique)
    _write_jsonl(output_dir / "search_log.jsonl", search_log)
    _write_jsonl(output_dir / "errors.jsonl", errors)
    report = {"estimate": estimate, "tavily_credits_reported": credits,
              "candidate_urls": len(unique), "reddit_requests": requests,
              "rejected_other_subreddit": rejected_other_subreddit,
              "matched_posts": len(posts), "comments_retrieved": len(comments),
              "review_posts": len(reviewed), "errors": len(errors),
              "truncated_by_limit": len(unique) > requests,
              "incomplete_comment_threads": sum(not p["comments_complete"] for p in posts),
              "output_dir": str(output_dir)}
    (output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
