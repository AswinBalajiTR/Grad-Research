# Research code

The code is grouped by source. Run these commands from the repository root:

| Folder | Purpose |
| --- | --- |
| `code/reddit/` | Policy planning, Reddit collection, review merging, theme aggregation, and configs |
| `code/youtube/` | YouTube comment collector and search queries |
| `code/h1b/` | USCIS and DOL H-1B collector |
| `code/university/` | Historical enrollment and intake analysis |
| `code/economic_indicators/` | Local economic indicator collection and exposure measures |
| `code/policy_timeline/` | Policy event collection and review windows |
| `code/tests/` | Collector and Reddit tests |

All datasets and generated analysis files live in top-level `data/`, grouped by the same source names. The Streamlit dashboard and its pages live in top-level `demo/`.

## Dashboard

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
streamlit run demo/app.py
```

The dashboard reads local files on startup. The YouTube and H-1B refresh buttons start their collectors. The committed Reddit summary at `data/reddit/processed/reddit_theme_counts.csv` has aggregate theme counts without usernames or comment text. These counts describe reviewed comments, not a representative student sample or policy effects. The locally generated H-1B CSV belongs at `data/h1b/processed/h1b_filings_2025_to_latest.csv`.

## Reddit

```bash
python3 code/reddit/main.py status
python3 code/reddit/main.py policy-plan
python3 code/reddit/main.py reddit-collect --policies code/reddit/config/policies.example.json --dry-run
```

`policy-plan` uses `code/reddit/config/policy_events_to_verify.csv`, updates the committed manifest in that config folder, and writes ignored search jobs to `data/reddit/interim/`. It makes no network requests. The 32 events are candidates for primary-source verification.

`reddit-collect` discovers Reddit post URLs through Tavily unless `--candidate-file` is provided; it saves runs under `data/reddit/raw/runs/`. To make requests, set `TAVILY_API_KEY` in the environment or in an ignored `code/.env` file. The dry run above makes no requests.

For a local rebuild, first provide the saved responses in `data/reddit/raw/policy_20261013/`, then run:

```bash
python3 code/reddit/main.py policy-rebuild
python3 code/reddit/build_reddit_themes.py
```

The rebuild uses local raw responses and the review CSVs in `code/reddit/config/`; it does not fetch posts. Its intermediate, reviewed, and coverage outputs go under `data/reddit/`. The saved responses and reviewed records are not included in this branch, so the default rebuild and theme regeneration need those local inputs. `sentiment-analyze` is an optional local Ollama workflow for reviewed comments; its labels require human validation.

## YouTube, H-1B, and university data

```bash
python3 code/youtube/collect_youtube.py --max-videos 3 --max-comments-per-video 50
python3 code/h1b/collect_h1b.py --source dol
python3 code/university/historical_international_eda.py
python3 code/university/university_intake_eda.py
```

The YouTube collector writes to `data/youtube/processed/`. The H-1B collector caches DOL downloads in `data/h1b/raw/` and writes the processed CSV to `data/h1b/processed/`. For a local USCIS export, use `--source uscis --input data/h1b/raw/uscis_h1b_fy2025.csv`. The historical university script uses the committed source-linked table in `data/university/interim/` and writes charts to `data/university/outputs/`. The intake script needs `data/university/interim/intake_observations.csv`, which is not included here.

These sources are descriptive and do not establish policy effects.
