# International Student News and H-1B EDA

This project collects YouTube comments about U.S. international-student policy after January 20, 2025, prepares H-1B filing data from January 2025 through the latest official release, and displays exploratory analysis in Streamlit.

## What is included

- `scripts/collect_youtube.py`: uses `yt-dlp` to find 1–60 relevant videos and export a bounded sample of accessible comments without a YouTube API key.
- `scripts/collect_h1b.py`: downloads and combines the official Department of Labor FY2025 and latest FY2026 H-1B LCA disclosure files.
- `app.py`: research dashboard with comment sentiment, policy-impact themes, timelines, H-1B statuses, states, occupations, employers and annualized wage analysis.
- `data/processed/youtube_comments.csv`: requested two-column YouTube output (`date`, `youtube_comment`).
- `data/processed/h1b_filings_2025_to_latest.csv`: normalized H-1B output from January 1, 2025 through the latest official release.

No fabricated records are included. The two CSV files initially contain headers only because this build environment cannot reach YouTube or the government download endpoints. Streamlit automatically runs the collectors when it starts and finds empty CSV files.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Collect YouTube comments

The default start date is the presidential inauguration date, January 20, 2025. Edit `config/search_queries.txt` to change or expand the topic coverage.

```bash
python scripts/collect_youtube.py \
  --queries-file config/search_queries.txt \
  --start-date 2025-01-20 \
  --max-videos 60
```

No API key is needed. The collector uses public guest-session access through `yt-dlp`, searches the configured topics, and deduplicates up to 60 relevant videos. For predictable runtime, the dashboard defaults to 3 videos and 50 comments per video, and the collector stops starting new videos after a three-minute budget. YouTube may throttle guest sessions, some videos disable comments, and public search cannot guarantee a complete census. The collector writes the requested two-column file and a video-audit file at `data/processed/youtube_videos.csv`.

## Prepare H-1B data from 2025 through the latest release

Export FY2025 results from the official USCIS H-1B Employer Data Hub as CSV, save the file locally, then run:

```bash
python scripts/collect_h1b.py \
  --source uscis \
  --input data/raw/uscis_h1b_fy2025.csv
```

The script also tries the official USCIS bulk-file naming convention when `--input` is omitted. If USCIS does not expose FY2025 through that legacy URL, it stops with instructions instead of substituting another dataset.

### Automatic DOL collection

The automatic workflow downloads DOL FY2025 Q2, Q3 and Q4 plus the latest FY2026 cumulative release, filters to H-1B, removes decisions before January 1, 2025 and deduplicates case numbers:

```bash
python scripts/collect_h1b.py --source dol
```

Raw DOL workbooks are cached under `data/raw/`, so later refreshes do not download the same large files again.

## Run the dashboard

```bash
streamlit run app.py
```

The app automatically fetches YouTube data when its processed CSV is empty. Select 1–60 videos and 25–500 comments per video in the sidebar; the defaults are 3 videos and 50 comments. Use **Refresh YouTube** to fetch again. **Refresh H-1B** separately downloads FY2025 plus the latest FY2026 release and keeps decisions from January 1, 2025 onward, so the larger H-1B files do not delay a YouTube test. There are no file-upload controls.

### Research EDA

The YouTube view contains five distinct analyses: concern intensity over time, impact-theme prevalence, sentiment composition by theme, theme co-occurrence, and negative-versus-positive language. The H-1B view contains five different analyses: monthly demand, filing outcomes, geographic concentration, occupational pathways, and wage access by occupation.

## Data definitions

- `date` in the YouTube CSV is the comment publication timestamp in UTC.
- Each DOL row represents one Labor Condition Application disclosure record, not a USCIS petition decision or visa issuance.
- The latest currently published FY2026 file is Q3 and covers decisions through June 30, 2026.
- YouTube comments are public user-generated content. Avoid publishing commenter identities, and follow the YouTube API Services Terms when retaining or redistributing data.

