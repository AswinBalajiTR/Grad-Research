# International student research dashboard and collection


## Run the combined dashboard

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r code/requirements.txt
streamlit run code/app.py
```

The app has three pages in research order: **Enrollment**, **YouTube and Reddit**, and **H-1B**. The launcher alone sets Streamlit page configuration. It reads local data on startup and makes no collection requests until a refresh button is clicked. The Enrollment page uses the source-linked university counts in `src/historical_international_eda.py`. The YouTube and H-1B pages use Aswin's collectors. The Reddit page shows aggregate concern-theme counts from reviewed comments, without including usernames or raw comment text in the dashboard data file. The same transparent theme rules classify YouTube and Reddit text; these are topic mentions rather than positive/negative sentiment.

From `code/`, run either collector directly when you want to control inputs:

```bash
python3 scripts/collect_youtube.py --queries-file config/search_queries.txt --start-date 2025-01-20 --max-videos 3 --max-comments-per-video 50
python3 scripts/collect_h1b.py --source dol
# Or use a local USCIS FY2025 export:
python3 scripts/collect_h1b.py --source uscis --input data/raw/uscis_h1b_fy2025.csv
```

The YouTube start date is a neutral policy window starting January 20, 2025. Its collector writes `data/processed/youtube_comments.csv` and `data/processed/youtube_videos.csv`. The H-1B collector writes `data/processed/h1b_filings_2025_to_latest.csv`; DOL downloads are cached under `data/raw/`. DOL Labor Condition Applications are distinct from USCIS petition decisions. These data sources describe discussion and employer filings, and do not establish policy effects. YouTube guest access can fail or be throttled; the dashboard reports collector errors.

The committed `data/processed/reddit_theme_counts.csv` has aggregate month, event, theme, and count fields derived from the reviewed local comments. When reviewed comments change, regenerate the file with `python3 scripts/build_reddit_themes.py` and the shared rules in `concern_themes.py`. The 32-policy CSV is a candidate research scope and its events are marked unverified; check events against primary sources before drawing conclusions.

## Historical international enrollment EDA

`src/historical_international_eda.py` builds a source-linked historical CSV from
published university tables and writes three trend charts, a 2025 comparison CSV,
and `findings.md` to `outputs/historical_international_eda/`. It covers Ohio
University (2019–2025, including India and academic level), MIT (2016–2025),
UH Hilo (2011–2025), U-M Ann Arbor (2019–2025, by academic level),
Illinois Springfield (2022–2025, with level splits in 2024–2025),
New Mexico (2021–2025, including India and academic level), and UC Berkeley
(2021–2025, including India). The data
measure total fall enrollment, including continuing students; they do not
measure new arrivals or policy effects. Michigan's 2025 performance-report
count differs from the International Center's annual report. Source URLs and
reporting definitions are documented in the CSV and `findings.md`.
For the India series, the New Mexico 2025 report's change column and the
Berkeley 2025 report's 2024 comparison column conflict with those universities'
published annual counts. The dataset uses the annual counts and flags both
discrepancies in `findings.md`.

```bash
python3 src/historical_international_eda.py
```

`src/historical_dashboard.py` is an interactive Streamlit story page for the
project's mobility layer. In seven parts it covers the research question, a Fall
2025 snapshot, campus-by-campus changes, the undergraduate/graduate split,
Indian students vs. all international students (with an Ohio breakdown), the
long-run context, and the next steps that link enrollment to student discourse.

```bash
pip install streamlit plotly pandas
streamlit run app.py
```

## University intake EDA

`src/university_intake_eda.py` analyzes the source-linked aggregate table in
`data/interim/university_intake/intake_observations.csv`. It writes annual series,
an international-student 2025 snapshot, 2024-to-2025 changes, admissions
funnels, academic-level comparisons, source quality flags, four PNG charts,
and a short `insights.md` to
`outputs/university_intake_eda/`. It makes no network calls.

```bash
python3 -m pip install matplotlib
python3 src/university_intake_eda.py
```

Run these commands from `code/`. Use `--input` and `--out` to choose different
paths. Counts from different cohort definitions are kept separate, and the
report treats differences as descriptive rather than causal policy effects.
The current observations cover international students from all countries
combined; they do not support an India-specific intake estimate.

## Current 32-policy collection

The supplied `policy_events_to_verify.csv` uses `event_date` and `extended_end`. See [the 13 October collection report](outputs/reddit_policy_collection_20261013.md) for the fixed ten-subreddit panel, saved raw files, reviewed posts and comments, costs, and coverage limits. The combined reviewed records are in `data/processed/reddit_policy_20261013/all_reviewed_posts.jsonl` and `all_reviewed_comments.jsonl`. The May 27 pilot raw files were removed and are excluded.

The code has two entry files: `src/main.py` is the command line interface, and `src/reddit_scrapper.py` contains collection, search audit, review normalization, merging, and coverage logic. From `code/`, run:

```bash
python3 src/main.py policy-plan
python3 src/main.py policy-rebuild
```

`policy-plan` writes the 32-policy manifest and 320 planned search jobs. `policy-rebuild` reads saved Tavily and Apify/archive responses plus the review CSVs, then regenerates candidates, review queue, processed records, and coverage. Both commands make **no network calls or charges**. The rebuild does not discover or fetch additional Reddit content; search result candidates that still need a post fetch are listed in `data/raw/reddit/policy_20261013/unfetched_candidates.jsonl`. The raw responses remain available for audit. Use the path flags shown by `python3 src/main.py policy-rebuild --help` to rebuild another batch.

The data folders now have distinct roles: `data/raw/reddit/policy_20261013/` holds saved API responses and discovery artifacts; `data/interim/reddit_policy_20261013/` holds the archive review queue, source-specific normalized records, exclusions, and normalization reports; `data/processed/reddit_policy_20261013/` holds only the merged reviewed posts, merged reviewed comments, and combined report. The separate university intake files remain under `data/interim/university_intake/`.

The older `reddit-collect` command below remains for short-window pilot policies with `announcement_date` and `days_after`. It can make Tavily and Reddit requests unless `--dry-run` is set. The real 32-policy CSV belongs to `policy-plan` and `policy-rebuild`.

## Optional legacy comment sentiment by policy

With a locally running Ollama service and the installed `qwen2.5:7b` model, run `python3 src/main.py sentiment-analyze`. It joins every reviewed comment to its parent post using `(event_id, post_id)` and checks for missing parents and duplicate comment IDs. It labels the author's expressed reaction to the policy or its direct effects as `positive`, `negative`, or `neutral`; removed or unusable text is `unclassifiable`. Factual questions, legal explanations, and practical advice are neutral even when they describe a harmful outcome. This uses the local model, with no paid API calls.

The command writes `data/processed/reddit_policy_20261013/comment_sentiment.jsonl` with parent-post context, `sentiment_by_policy.csv` with counts for each policy, and `sentiment_report.json` with overall counts. Incomplete work is cached in `data/interim/reddit_policy_20261013/sentiment_progress_v2.jsonl`, so rerunning the command resumes without relabeling unchanged comments. `config/sentiment_review_overrides.csv` records targeted corrections where the model confused factual statements, gratitude, or unrelated platform complaints with policy sentiment. The final file retains each original model label and its corrected label. These exploratory labels still need independent human validation before substantive conclusions.

The collector takes dated policy events, discovers Reddit post URLs, retrieves each post and the comment tree exposed by its `.json` page, and keeps a record of its decisions. It uses Python's standard library. The default discovery service is Tavily Search; a candidate file lets you supply URLs found by an LLM, manual search, or another source.

## Start with a no-cost plan

From `code/`:

```bash
python3 src/main.py reddit-collect --policies config/policies.example.json --dry-run
```

This prints the queries and caps without a network call. Check `search_plan_truncated`: the default cap is 20 searches across the entire policy file. Edit the example policy file for your events. `announcement_date` through `days_after` dates later is inclusive; for May 27 with `days_after: 7`, the UTC window is May 27 00:00 through June 4 00:00 exclusive. The post's Reddit `created_utc` decides whether it belongs, not the search engine's date. Comments on qualifying posts are saved even if written later, with `within_policy_window` to distinguish them.

For the single-subreddit pilot, use `config/policies.may27.f1visa.json`; it plans four searches. The [pilot discovery report](report_logs.md) records what Tavily returned and what remains unverified. Its raw files have been removed.

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
