# International student research code

Run commands below from `code/` unless a command says otherwise.

## Dashboard

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r code/requirements.txt
streamlit run code/app.py
```

The dashboard has Enrollment, YouTube and Reddit discourse, and H-1B pages. It reads local files on startup. Only the YouTube and H-1B refresh buttons start collection. The committed Reddit theme summary at `data/processed/reddit_theme_counts.csv` contains aggregate counts, without usernames or comment text. These counts describe mentions in reviewed comments, not a representative student sample or policy effects.

## Reddit collection

`src/main.py` is the command line entry point. `src/reddit_scrapper.py` contains the collector, policy planning, review merge, coverage, and sentiment code. The filename retains its original spelling for existing imports.

To inspect the current 32-event candidate scope and generate search jobs without network requests:

```bash
python3 src/main.py policy-plan
```

The source table is `config/policy_events_to_verify.csv`. The committed `config/policy_batch_scope.json` supplies stable event IDs and dashboard labels; `config/policy_search_jobs.jsonl` is generated and ignored. The events are candidates for verification against primary sources.

To rebuild reviewed Reddit records, first place the saved collection responses in `data/raw/reddit/policy_20261013/` and then run:

```bash
python3 src/main.py policy-rebuild
python3 scripts/build_reddit_themes.py
```

The rebuild reads local raw responses and the review CSVs under `config/`; it does not fetch posts. It writes intermediate records under `data/interim/reddit_policy_20261013/`, reviewed records under `data/processed/reddit_policy_20261013/`, and coverage under `outputs/`. Those generated folders are ignored. The saved responses and reviewed records are **not included** in this branch, so the default rebuild and theme regeneration require local inputs. The committed theme summary remains available to the dashboard.

For a small collector dry run that makes no requests:

```bash
python3 src/main.py reddit-collect --policies config/policies.example.json --dry-run
```

`reddit-collect` accepts JSON or CSV policies with `event_id`, `announcement_date`, and `keywords`. Optional fields are `policy_name`, `subreddits`, and `days_after` (default 7). Without `--dry-run`, it uses Tavily to discover Reddit post URLs and requests Reddit's public JSON pages. Supply `TAVILY_API_KEY` in the environment or an ignored `code/.env` file. Use `--candidate-file` to provide URLs instead of Tavily search. The collector saves each run under `data/raw/reddit/runs/`, which Git ignores.

`sentiment-analyze` is an optional local Ollama workflow for reviewed comments. It needs the reviewed records and a running Ollama service with the chosen model; its labels require human validation.

## Other data workflows

- `python3 src/historical_international_eda.py` builds source-linked enrollment summaries and charts from its embedded published counts.
- `python3 src/university_intake_eda.py` analyzes `data/interim/university_intake/intake_observations.csv` when that local source table is available. The table is not included here.
- `python3 scripts/collect_youtube.py --queries-file config/search_queries.txt --start-date 2025-01-20 --max-videos 3 --max-comments-per-video 50` collects a bounded YouTube sample.
- `python3 scripts/collect_h1b.py --source dol` collects DOL filings. For a local USCIS export, use `--source uscis --input data/raw/uscis_h1b_fy2025.csv`.

Generated charts, API responses, and intermediate research records stay local. The enrollment counts and discourse samples are descriptive and do not establish policy effects.
