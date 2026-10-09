"""Find each policy's earliest signal: news coverage before the announcement.

For every listed policy without an `earliest_signal`:
  1. the LLM writes 2-3 phrases a news article would use for this policy,
  2. the GDELT news API is searched for them in the LOOKBACK_DAYS before the
     announcement,
  3. the LLM picks the earliest headline that reports this specific policy
     (a leak or advance report), or none.
The headline's date goes in `earliest_signal` and its URL in `signal_source`
for checking by hand. Blank means no earlier coverage: s = the announcement.

build_review_list.py runs this before writing the list. Run this script to add
signals to an existing list instead (needs the LLM server, not the fetch).

GDELT DOC API docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/

Usage:
    python find_earliest_signal.py --model Qwen/Qwen2.5-14B-Instruct-AWQ
"""

import argparse
import csv
import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

GDELT_API = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_PAUSE = 6          # GDELT allows one request every 5 seconds
LOOKBACK_DAYS = 60
MAX_HEADLINES = 80       # headlines shown to the LLM, earliest first

PHRASES_PROMPT = """You write news search phrases. Given a U.S. government policy document, return 2 or 3 short \
phrases (2-4 words each) that news articles would use when reporting this specific policy, for example \
"H-1B fee", "student visa interviews", "social media vetting". Use plain words only, no quotes or symbols.
Answer with JSON only: {"phrases": ["...", "..."]}"""

CONFIRM_PROMPT = """You check news coverage of a U.S. policy. You get the policy, its announcement date, and a \
numbered list of news headlines published before that date. Return the number of the EARLIEST headline that \
reports this specific policy in advance (a leak, a plan, or a draft). Headlines about a different policy on the \
same topic do not count. Return null if no headline reports this policy.
Answer with JSON only: {"index": <number or null>}"""


def reply_json(content):
    """The JSON object in an LLM reply, or {}."""
    content = re.sub(r"<think>.*?</think>", "", content or "", flags=re.S)
    m = re.search(r"\{.*\}", content, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}


def gdelt_articles(query, start, end):
    """Articles matching `query` published from `start` to `end` (dates),
    earliest first, one per headline. Empty list if the search fails."""
    params = {"query": query, "mode": "artlist", "format": "json", "maxrecords": 250, "sort": "dateasc",
              "startdatetime": start.strftime("%Y%m%d000000"), "enddatetime": end.strftime("%Y%m%d235959")}
    for attempt in range(4):
        time.sleep(GDELT_PAUSE)
        try:
            resp = requests.get(GDELT_API, params=params, timeout=60)
        except requests.RequestException:
            continue
        if resp.status_code == 429:
            time.sleep(20 * (attempt + 1))
            continue
        try:
            found = resp.json().get("articles", [])
        except ValueError:  # GDELT answers errors (e.g. a bad query) in plain text
            return []
        articles, seen = [], set()
        for a in found:
            title = (a.get("title") or "").strip()
            if title.lower() in seen:
                continue
            seen.add(title.lower())
            articles.append({"date": datetime.strptime(a["seendate"][:8], "%Y%m%d").date(), "title": title,
                             "domain": a.get("domain", ""), "url": a.get("url", "")})
        return articles
    return []


def signal_phrases(r, llm):
    """News-style search phrases for one policy, written by the LLM."""
    excerpt = " ".join(((r.get("text") or r.get("summary") or "")[:1500]).split())
    user = f"Title: {r['title']}\nWhat it does: {r.get('llm_reason', '')}\nText excerpt: {excerpt}"
    phrases = reply_json(llm.chat(PHRASES_PROMPT, user, max_tokens=100)).get("phrases", [])
    # GDELT accepts letters, digits, spaces, and hyphens in quoted phrases.
    cleaned = [re.sub(r"[^A-Za-z0-9 \-]", "", str(p)).strip() for p in phrases]
    return [p for p in cleaned if len(p) >= 3][:3]


def find_signal(r, llm):
    """(date, url) of the earliest news report of policy r before its
    announcement, or None."""
    a = date.fromisoformat(r["event_date"])
    phrases = signal_phrases(r, llm)
    if not phrases:
        return None
    query = "(" + " OR ".join(f'"{p}"' for p in phrases) + ")" if len(phrases) > 1 else f'"{phrases[0]}"'
    articles = gdelt_articles(query, a - timedelta(days=LOOKBACK_DAYS), a - timedelta(days=1))[:MAX_HEADLINES]
    if not articles:
        return None
    listing = "\n".join(f"{i}. {x['date']} | {x['domain']} | {x['title']}" for i, x in enumerate(articles, 1))
    user = (f"Policy: {r['title']}\nWhat it does: {r.get('llm_reason', '')}\nAnnounced: {a}\n\n"
            f"Headlines before the announcement:\n{listing}")
    index = reply_json(llm.chat(CONFIRM_PROMPT, user, max_tokens=50)).get("index")
    if not isinstance(index, int) or not 1 <= index <= len(articles):
        return None
    hit = articles[index - 1]
    return hit["date"], hit["url"]


def add_signals(listed, llm):
    """Fill `earliest_signal` and `signal_source` for listed policies that have
    no earliest_signal yet (one GDELT search each, so this takes a few minutes)."""
    todo = [r for r in listed if not (r.get("earliest_signal") or "").strip()]
    print(f"Earliest signal: searching news for {len(todo)} policies")
    found = 0
    for i, r in enumerate(todo, 1):
        try:
            hit = find_signal(r, llm)
        except Exception as err:  # one failed search should not stop the list being written
            print(f"  search failed for {r['title'][:60]}: {err}")
            hit = None
        r["earliest_signal"], r["signal_source"] = (hit[0].isoformat(), hit[1]) if hit else ("", "")
        found += bool(hit)
        if i % 5 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)} ({found} with earlier news coverage)")


def main():
    from build_event_windows import recompute_windows
    from build_review_list import LLMScreen

    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", default=str(root / "data" / "processed" / "policy_events_to_verify.csv"))
    parser.add_argument("--stop", default="2026-10-01", help="stop date (YYYY-MM-DD)")
    parser.add_argument("--llm-url", default="http://localhost:8000/v1")
    parser.add_argument("--model", default="Qwen/Qwen2.5-14B-Instruct-AWQ")
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--disable-thinking", action="store_true", help="turn off Qwen3 thinking mode")
    args = parser.parse_args()

    path = Path(args.list)
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        columns, rows = list(reader.fieldnames), list(reader)
    for r in rows:  # the list stores Excel-style dates once it has been saved in Excel
        for col in ("event_date", "earliest_signal"):
            v = (r.get(col) or "").strip()
            if v and "/" in v:
                r[col] = datetime.strptime(v, "%m/%d/%Y").date().isoformat()
    add_signals(rows, LLMScreen(args.llm_url, args.model, 1, args.disable_thinking, args.api_key))
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns + [c for c in ("signal_source",) if c not in columns])
        w.writeheader()
        w.writerows(rows)
    recompute_windows(path, date.fromisoformat(args.stop))


if __name__ == "__main__":
    main()
