# Policy-window Reddit collection

The collector takes dated policy events, discovers Reddit post URLs, retrieves each post and the comment tree exposed by its `.json` page, and keeps a record of its decisions. It uses Python's standard library. The default discovery service is Tavily Search; a candidate file lets you supply URLs found by an LLM, manual search, or another source.

## Start with a no-cost plan

From `code/`:

```bash
python3 src/main.py reddit-collect --policies config/policies.example.json --dry-run
```

This prints the queries and caps without a network call. Check `search_plan_truncated`: the default cap is 20 searches across the entire policy file. Edit the example policy file for your events. `announcement_date` through `days_after` dates later is inclusive; for May 27 with `days_after: 7`, the UTC window is May 27 00:00 through June 4 00:00 exclusive. The post's Reddit `created_utc` decides whether it belongs, not the search engine's date. Comments on qualifying posts are saved even if written later, with `within_policy_window` to distinguish them.

For the single-subreddit pilot, use `config/policies.may27.f1visa.json`; it plans four searches. The [pilot discovery report](pilot_may27_f1visa.md) records what Tavily returned and what remains unverified.

## Automatic discovery

The signed-in Tavily account's existing development key is stored locally in `code/.env`. The collector reads that file automatically; `code/.gitignore` excludes it. On another computer, put `TAVILY_API_KEY=...` in `code/.env` or export the variable in your shell. Run:

```bash
python3 src/main.py reddit-collect --policies config/policies.example.json --max-search-queries 16 --max-posts 50 --max-reddit-requests 60
```

The key is never written to output. Each basic search is expected to use one Tavily credit; the dry run shows the planned count. The current Researcher account displays 1,000 free monthly credits with pay as you go disabled. This workflow does not call Apify or an LLM. It refuses to start if the search cap would skip any policy queries. The request caps limit activity, though they cannot guarantee a complete collection.

## URLs discovered elsewhere

To skip Tavily, put one Reddit post URL per line in a `.txt` file and use `--candidate-file path/to/urls.txt` with a single policy. For multiple policies, use a CSV with `event_id,url` columns or a JSON list of objects containing those fields. This accepts output from an LLM URL-discovery step after you verify its links. No Tavily key is needed.

## Policy table format

JSON is a list of policy objects or `{ "policies": [...] }`. CSV is also accepted; see [`config/policies.example.csv`](config/policies.example.csv). Required fields: `event_id`, `announcement_date` (`YYYY-MM-DD`), `keywords` (JSON array or CSV `|`-separated values). Optional: `policy_name`, `subreddits` (array or `|`-separated), `days_after` (default 7). The default subreddits are r/f1visa, r/Indians_StudyAbroad, r/gradadmissions, and r/usvisascheduling. Search phrases should include specific variants of the policy language; broad phrases produce more false positives. Increase `--max-search-queries` if the dry run reports a truncated plan.

## Outputs

By default each run gets a new timestamped folder under `data/raw/reddit/runs/`, which Git ignores. You can set `--out` to a new directory. The collector refuses to overwrite an existing nonempty output directory. Each run contains:

- `posts.jsonl`: matching posts, event ID, timestamps, text, matched terms, provenance, comment completeness.
- `comments.jsonl`: retrieved comments and whether their timestamps are inside the event window.
- `review.jsonl`: fetched posts outside the date window or without an exact keyword match. Inspect these for relevant paraphrases.
- `candidates.jsonl`: deduplicated URLs eligible for fetching.
- `search_log.jsonl`: search queries, result counts, and reported Tavily credits.
- `errors.jsonl`: failed searches or Reddit requests.
- `report.json`: counts, caps, and incomplete comment threads.

A Reddit `.json` page can include `more` placeholders or omit deleted/removed comments. `comments_complete` is false in those cases. Search results can miss relevant posts, especially older ones. Treat outputs as discovered records rather than a complete census. Reddit may return 403 or 429; failures are logged without bypassing access controls. This collector does not infer nationality, intent to enroll, or sentiment. Keep raw text and usernames private and follow the site's applicable terms.

Tavily can return posts from other subreddits even when a query uses a `site:` path. The collector therefore checks each URL against the policy's subreddit list before requesting Reddit data.

The project design is in [`../proposal/workflow.md`](../proposal/workflow.md).
