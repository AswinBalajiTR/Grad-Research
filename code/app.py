from __future__ import annotations

import os
import re
import subprocess
import sys
from math import sqrt
from collections import Counter
from itertools import combinations
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


YOUTUBE_PATH = Path("data/processed/youtube_comments.csv")
H1B_PATH = Path("data/processed/h1b_filings_2025_to_latest.csv")
STOPWORDS = {
    "a", "about", "after", "all", "also", "am", "an", "and", "are", "as", "at",
    "be", "because", "been", "but", "by", "can", "do", "for", "from", "get", "had",
    "has", "have", "he", "her", "here", "him", "his", "how", "i", "if", "in", "is",
    "it", "its", "just", "me", "more", "my", "no", "not", "of", "on", "or", "our",
    "out", "she", "so", "some", "than", "that", "the", "their", "them", "there", "they",
    "this", "to", "too", "up", "us", "very", "was", "we", "were", "what", "when", "who",
    "will", "with", "would", "you", "your", "https", "www", "com",
}

THEME_PATTERNS = {
    "Visa status and revocation": r"\b(visa|revok|status|f-?1|student visa|consular|embassy)\b",
    "OPT, CPT and work authorization": r"\b(opt|stem opt|cpt|ead|work permit|work authori[sz]ation)\b",
    "H-1B and employment": r"\b(h-?1b|sponsor|employer|job|layoff|career|hiring|employment)\b",
    "Travel and entry": r"\b(travel|entry|airport|border|ban|deport|removal|re-?entry)\b",
    "University and enrollment": r"\b(university|college|campus|enroll|admission|degree|harvard|sevp)\b",
    "Financial pressure": r"\b(tuition|fee|cost|money|debt|rent|financial|scholarship)\b",
    "Safety, stress and uncertainty": r"\b(afraid|fear|anxi|stress|uncertain|worried|scared|unsafe|confus)\b",
}

POSITIVE_WORDS = {
    "able", "approve", "approved", "benefit", "better", "calm", "clear", "fair",
    "good", "great", "happy", "help", "helpful", "hope", "opportunity", "positive",
    "relief", "safe", "support", "thank", "thanks", "welcome",
}
NEGATIVE_WORDS = {
    "afraid", "anxiety", "anxious", "bad", "ban", "confused", "crisis", "deport",
    "deny", "denied", "difficult", "fear", "hate", "hurt", "illegal", "lose", "lost",
    "negative", "problem", "reject", "revoked", "risk", "scared", "stress", "terrible",
    "threat", "uncertain", "unfair", "unsafe", "worried", "worse",
}


st.set_page_config(page_title="International Student and H-1B EDA", page_icon="📊", layout="wide")


@st.cache_data(show_spinner=False)
def read_csv_path(path: str) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def load_data(path: Path) -> pd.DataFrame:
    if path.exists():
        return read_csv_path(str(path))
    return pd.DataFrame()


def run_collector(arguments: list[str], timeout: int = 7200) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [sys.executable, *arguments],
            cwd=Path(__file__).parent,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"Timed out while running {' '.join(arguments)}"
    message = "\n".join(part.strip() for part in [result.stdout, result.stderr] if part.strip())
    return result.returncode == 0, message[-2500:]


def refresh_youtube(max_videos: int, max_comments: int) -> tuple[str, bool, str]:
    youtube_ok, youtube_message = run_collector(
        [
            "scripts/collect_youtube.py",
            "--max-videos",
            str(max_videos),
            "--max-comments-per-video",
            str(max_comments),
            "--time-budget-seconds",
            "180",
        ],
        timeout=240,
    )
    read_csv_path.clear()
    return "YouTube", youtube_ok, youtube_message


def refresh_h1b() -> tuple[str, bool, str]:
    dol_ok, dol_message = run_collector(["scripts/collect_h1b.py", "--source", "dol"])
    result = ("H-1B 2025–latest", dol_ok, dol_message)
    read_csv_path.clear()
    return result


def compact_number(value: float | int) -> str:
    value = float(value)
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:,.0f}"


def find_col(frame: pd.DataFrame, names: list[str]) -> str | None:
    keys = {re.sub(r"[^a-z0-9]+", "_", str(c).lower()).strip("_"): c for c in frame.columns}
    for name in names:
        key = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        if key in keys:
            return keys[key]
    return None


def top_words(series: pd.Series, limit: int = 25) -> pd.DataFrame:
    words: Counter[str] = Counter()
    for value in series.dropna().astype(str):
        words.update(
            token for token in re.findall(r"[a-zA-Z][a-zA-Z']{2,}", value.lower())
            if token not in STOPWORDS
        )
    return pd.DataFrame(words.most_common(limit), columns=["word", "count"])


def lexicon_sentiment(text: object) -> float:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z']+", str(text).lower())
    if not tokens:
        return 0.0
    positive = sum(token in POSITIVE_WORDS for token in tokens)
    negative = sum(token in NEGATIVE_WORDS for token in tokens)
    return max(-1.0, min(1.0, (positive - negative) / sqrt(len(tokens))))


def sentiment_label(score: float) -> str:
    if score <= -0.05:
        return "Negative"
    if score >= 0.05:
        return "Positive"
    return "Neutral"


def comment_themes(text: object) -> list[str]:
    value = str(text).lower()
    matches = [name for name, pattern in THEME_PATTERNS.items() if re.search(pattern, value)]
    return matches or ["Other discussion"]


def enrich_comments(frame: pd.DataFrame, date_col: str, comment_col: str) -> pd.DataFrame:
    enriched = frame.copy()
    enriched[date_col] = pd.to_datetime(enriched[date_col], errors="coerce", utc=True)
    enriched = enriched.dropna(subset=[date_col, comment_col])
    enriched["sentiment_score"] = enriched[comment_col].map(lexicon_sentiment)
    enriched["sentiment"] = enriched["sentiment_score"].map(sentiment_label)
    enriched["themes"] = enriched[comment_col].map(comment_themes)
    enriched["impact_concern"] = enriched["themes"].map(
        lambda themes: any(theme != "Other discussion" for theme in themes)
    )
    return enriched


def annualized_wage(frame: pd.DataFrame) -> pd.Series:
    wage_col = find_col(frame, ["wage_from", "wage_rate_of_pay_from"])
    unit_col = find_col(frame, ["wage_unit", "wage_unit_of_pay"])
    if not wage_col or not unit_col:
        return pd.Series(float("nan"), index=frame.index)
    wage = pd.to_numeric(frame[wage_col], errors="coerce")
    units = frame[unit_col].fillna("").astype(str).str.lower().str.strip()
    multipliers = {
        "year": 1,
        "month": 12,
        "bi-weekly": 26,
        "biweekly": 26,
        "week": 52,
        "hour": 2080,
    }
    return wage * units.map(multipliers)


st.title("International student news and H-1B filings")
st.caption("YouTube comments since January 20, 2025 and H-1B filings from 2025 through the latest official release")

with st.sidebar:
    st.header("Data")
    video_limit = st.slider(
        "Videos to collect",
        min_value=1,
        max_value=60,
        value=3,
        step=1,
        help="Start with 1–5 videos for a quick run, then increase the limit if needed.",
    )
    comment_limit = st.slider(
        "Maximum comments per video",
        min_value=25,
        max_value=500,
        value=50,
        step=25,
        help="A lower limit finishes faster. Replies are included within this limit.",
    )
    refresh_youtube_requested = st.button(
        "Refresh YouTube", type="primary", use_container_width=True
    )
    refresh_h1b_requested = st.button("Refresh H-1B", use_container_width=True)
    st.caption("YouTube fetches automatically when its local CSV is empty. H-1B refresh runs separately.")

youtube = load_data(YOUTUBE_PATH)
h1b = load_data(H1B_PATH)

auto_fetch_allowed = os.getenv("DISABLE_AUTO_FETCH", "0") != "1"
auto_fetch_needed = youtube.empty and not st.session_state.get("auto_fetch_attempted", False)
if refresh_youtube_requested or (auto_fetch_allowed and auto_fetch_needed):
    st.session_state["auto_fetch_attempted"] = True
    with st.spinner("Fetching YouTube comments for up to three minutes..."):
        youtube_result = refresh_youtube(video_limit, comment_limit)
        previous = [result for result in st.session_state.get("fetch_results", []) if result[0] != "YouTube"]
        st.session_state["fetch_results"] = [youtube_result, *previous]
    youtube = load_data(YOUTUBE_PATH)
    h1b = load_data(H1B_PATH)

if refresh_h1b_requested:
    with st.spinner("Fetching H-1B data separately..."):
        h1b_result = refresh_h1b()
        previous = [result for result in st.session_state.get("fetch_results", []) if "H-1B" not in result[0]]
        st.session_state["fetch_results"] = [*previous, h1b_result]
    h1b = load_data(H1B_PATH)

with st.sidebar:
    for label, succeeded, message in st.session_state.get("fetch_results", []):
        if succeeded:
            st.success(f"{label} data refreshed")
        else:
            st.error(f"{label} collection failed")
        if message:
            with st.expander(f"{label} collection log"):
                st.code(message)

overview_tab, youtube_tab, h1b_tab, methods_tab = st.tabs(
    ["Overview", "YouTube comments", "H-1B filings", "Methods"]
)

with overview_tab:
    st.subheader("Research overview")
    st.write(
        "This dashboard examines perceived effects in public YouTube comments alongside "
        "H-1B labor-condition activity. Treat the two sources as complementary signals, not as proof of causation."
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("YouTube comments", compact_number(len(youtube)))
    c2.metric("H-1B rows", compact_number(len(h1b)))
    state_col = find_col(h1b, ["employer_state", "state", "worksite_state"])
    c3.metric("States represented", int(h1b[state_col].nunique()) if state_col and not h1b.empty else 0)
    source_col = find_col(h1b, ["source"])
    c4.metric("H-1B sources", int(h1b[source_col].nunique()) if source_col and not h1b.empty else 0)

    if youtube.empty or h1b.empty:
        st.info(
            "One or both datasets are empty. Use the separate refresh buttons in the sidebar."
        )
    else:
        youtube_date = find_col(youtube, ["date", "published_at", "comment_date"])
        youtube_text = find_col(youtube, ["youtube_comment", "comment", "text"])
        h1b_date = find_col(h1b, ["decision_date", "date"])
        if youtube_date and youtube_text and h1b_date:
            comments_overview = enrich_comments(youtube, youtube_date, youtube_text)
            h1b_dates = pd.to_datetime(h1b[h1b_date], errors="coerce")
            comment_month = (
                comments_overview.assign(
                    month=comments_overview[youtube_date].dt.tz_localize(None).dt.to_period("M").dt.to_timestamp()
                )
                .groupby("month", as_index=False)
                .size()
                .rename(columns={"size": "Comments"})
            )
            h1b_month = (
                pd.DataFrame({"month": h1b_dates.dt.to_period("M").dt.to_timestamp()})
                .dropna()
                .groupby("month", as_index=False)
                .size()
                .rename(columns={"size": "H-1B filings"})
            )
            combined = comment_month.merge(h1b_month, on="month", how="outer").fillna(0).sort_values("month")
            for column in ["Comments", "H-1B filings"]:
                maximum = combined[column].max()
                combined[column] = combined[column] / maximum * 100 if maximum else 0
            combined_long = combined.melt("month", var_name="Series", value_name="Relative activity index")
            st.subheader("Monthly activity in both sources")
            st.caption("Each series is indexed to its own highest month = 100; magnitudes are not directly comparable.")
            st.plotly_chart(
                px.line(combined_long, x="month", y="Relative activity index", color="Series", markers=True),
                use_container_width=True,
            )
    if not h1b.empty and source_col:
        with st.expander("Loaded H-1B sources"):
            st.dataframe(h1b[[source_col]].drop_duplicates(), hide_index=True, use_container_width=True)

with youtube_tab:
    if youtube.empty:
        st.warning("No YouTube comments are loaded.")
    else:
        date_col = find_col(youtube, ["date", "published_at", "comment_date"])
        comment_col = find_col(youtube, ["youtube_comment", "comment", "text"])
        if date_col is None or comment_col is None:
            st.error("YouTube CSV must contain date and youtube_comment columns.")
        else:
            view = enrich_comments(youtube, date_col, comment_col)
            if view.empty:
                st.warning("The YouTube CSV has no valid dated comments.")
            else:
                min_date = view[date_col].min().date()
                max_date = view[date_col].max().date()
                selected_dates = st.date_input(
                    "Comment date range", value=(min_date, max_date), min_value=min_date, max_value=max_date
                )
                keyword = st.text_input("Comment contains", placeholder="visa, OPT, Trump...")
                filter_left, filter_right = st.columns(2)
                selected_sentiment = filter_left.multiselect(
                    "Sentiment", ["Negative", "Neutral", "Positive"]
                )
                available_themes = list(THEME_PATTERNS) + ["Other discussion"]
                selected_themes = filter_right.multiselect("Policy-impact theme", available_themes)
                if isinstance(selected_dates, (tuple, list)) and len(selected_dates) == 2:
                    mask = view[date_col].dt.date.between(selected_dates[0], selected_dates[1])
                    view = view.loc[mask]
                if keyword:
                    view = view.loc[view[comment_col].astype(str).str.contains(keyword, case=False, na=False, regex=False)]
                if selected_sentiment:
                    view = view.loc[view["sentiment"].isin(selected_sentiment)]
                if selected_themes:
                    view = view.loc[view["themes"].map(lambda values: bool(set(values) & set(selected_themes)))]

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Filtered comments", compact_number(len(view)))
            negative_share = view["sentiment"].eq("Negative").mean() if len(view) else 0
            k2.metric("Negative comments", f"{negative_share:.1%}")
            concern_share = view["impact_concern"].mean() if len(view) else 0
            k3.metric("Policy-impact mentions", f"{concern_share:.1%}")
            lengths = view[comment_col].astype(str).str.len()
            k4.metric("Median length", f"{lengths.median():.0f} characters" if len(lengths) else "0")

            weekly_impact = (
                view.assign(week=view[date_col].dt.tz_localize(None).dt.to_period("W").dt.start_time)
                .groupby("week", as_index=False)
                .agg(
                    comments=(comment_col, "size"),
                    negative_share=("sentiment", lambda values: values.eq("Negative").mean()),
                    impact_share=("impact_concern", "mean"),
                )
            )
            weekly_long = weekly_impact.melt(
                id_vars=["week", "comments"],
                value_vars=["negative_share", "impact_share"],
                var_name="Measure",
                value_name="Share",
            )
            weekly_long["Measure"] = weekly_long["Measure"].map(
                {"negative_share": "Negative sentiment", "impact_share": "Policy-impact mention"}
            )
            st.markdown("### YouTube EDA 1 of 5: Concern intensity over time")
            st.caption("Tracks weekly shares rather than raw volume, helping identify periods when concern intensified.")
            st.plotly_chart(
                px.line(
                    weekly_long,
                    x="week",
                    y="Share",
                    color="Measure",
                    markers=True,
                    range_y=[0, 1],
                ),
                use_container_width=True,
            )

            exploded = view[[comment_col, "sentiment", "themes"]].explode("themes")
            theme_prevalence = (
                exploded.groupby("themes", as_index=False)[comment_col]
                .size()
                .rename(columns={"size": "comments"})
                .sort_values("comments", ascending=False)
            )

            st.markdown("### YouTube EDA 2 of 5: Which student-impact issues dominate?")
            st.caption("A comment can mention multiple themes, so theme counts can exceed the number of comments.")
            st.plotly_chart(
                px.bar(theme_prevalence, x="comments", y="themes", orientation="h").update_layout(
                    yaxis={"categoryorder": "total ascending"}
                ),
                use_container_width=True,
            )

            theme_sentiment = exploded.groupby(["themes", "sentiment"], as_index=False).size()
            theme_sentiment["share"] = theme_sentiment["size"] / theme_sentiment.groupby("themes")["size"].transform("sum")
            st.markdown("### YouTube EDA 3 of 5: Sentiment composition within each issue")
            st.caption("Separates a frequently discussed issue from an issue discussed primarily in negative terms.")
            st.plotly_chart(
                px.bar(
                    theme_sentiment,
                    x="share",
                    y="themes",
                    color="sentiment",
                    orientation="h",
                    barmode="stack",
                    range_x=[0, 1],
                    color_discrete_map={"Negative": "#C0392B", "Neutral": "#7F8C8D", "Positive": "#238B45"},
                    labels={"themes": "Theme", "share": "Share of theme comments"},
                ),
                use_container_width=True,
            )

            theme_names = list(THEME_PATTERNS)
            cooccurrence = pd.DataFrame(0, index=theme_names, columns=theme_names, dtype=int)
            for values in view["themes"]:
                present = [theme for theme in values if theme in cooccurrence.index]
                for theme in present:
                    cooccurrence.loc[theme, theme] += 1
                for first, second in combinations(sorted(set(present)), 2):
                    cooccurrence.loc[first, second] += 1
                    cooccurrence.loc[second, first] += 1
            st.markdown("### YouTube EDA 4 of 5: Which effects are discussed together?")
            st.caption("Co-occurrence can reveal linked experiences, such as visa uncertainty appearing with employment or travel concerns.")
            st.plotly_chart(
                px.imshow(
                    cooccurrence,
                    text_auto=True,
                    color_continuous_scale="Blues",
                    labels={"color": "Comments"},
                    aspect="auto",
                ),
                use_container_width=True,
            )

            negative_words = top_words(view.loc[view["sentiment"].eq("Negative"), comment_col], 15)
            negative_words["Sentiment"] = "Negative"
            positive_words = top_words(view.loc[view["sentiment"].eq("Positive"), comment_col], 15)
            positive_words["Sentiment"] = "Positive"
            comparison_words = pd.concat([negative_words, positive_words], ignore_index=True)
            st.markdown("### YouTube EDA 5 of 5: Language used in negative versus positive reactions")
            st.caption("Compares frequent words across sentiment groups; use the comment table to verify context and sarcasm.")
            st.plotly_chart(
                px.bar(
                    comparison_words,
                    x="count",
                    y="word",
                    color="Sentiment",
                    facet_col="Sentiment",
                    orientation="h",
                    color_discrete_map={"Negative": "#C0392B", "Positive": "#238B45"},
                ).update_yaxes(categoryorder="total ascending"),
                use_container_width=True,
            )

            st.subheader("Comments")
            comment_table = view[[date_col, "sentiment", "sentiment_score", "themes", comment_col]].copy()
            comment_table["themes"] = comment_table["themes"].map(lambda values: ", ".join(values))
            st.dataframe(comment_table.sort_values(date_col, ascending=False), hide_index=True, use_container_width=True)

with h1b_tab:
    if h1b.empty:
        st.warning("No H-1B data are loaded.")
    else:
        view = h1b.copy()
        state_col = find_col(view, ["employer_state", "state", "worksite_state"])
        employer_col = find_col(view, ["employer_name", "employer"])
        status_col = find_col(view, ["case_status", "status"])
        title_col = find_col(view, ["job_title", "soc_title"])
        filing_col = find_col(view, ["total_filings", "filing_count"])
        approval_col = find_col(view, ["total_approvals"])
        denial_col = find_col(view, ["total_denials"])
        decision_col = find_col(view, ["decision_date", "date"])
        if decision_col:
            view[decision_col] = pd.to_datetime(view[decision_col], errors="coerce")
            earliest_decision = view[decision_col].min()
            if pd.notna(earliest_decision) and earliest_decision > pd.Timestamp("2025-01-31"):
                st.warning(
                    f"Current H-1B file begins {earliest_decision.date()}. Click Refresh H-1B to add the corrected FY2025 Q2 and Q3 files."
                )

        with st.expander("Filters", expanded=True):
            f1, f2, f3 = st.columns(3)
            if state_col:
                states = sorted(view[state_col].dropna().astype(str).unique())
                selected_states = f1.multiselect("Employer state", states)
                if selected_states:
                    view = view.loc[view[state_col].isin(selected_states)]
            employer_search = f2.text_input("Employer contains") if employer_col else ""
            if employer_search:
                view = view.loc[view[employer_col].astype(str).str.contains(employer_search, case=False, na=False, regex=False)]
            if status_col:
                statuses = sorted(view[status_col].dropna().astype(str).unique())
                selected_statuses = f3.multiselect("Case status", statuses)
                if selected_statuses:
                    view = view.loc[view[status_col].isin(selected_statuses)]
            if title_col:
                job_search = st.text_input("Job title contains")
                if job_search:
                    view = view.loc[view[title_col].astype(str).str.contains(job_search, case=False, na=False, regex=False)]
            if decision_col and view[decision_col].notna().any():
                min_decision = view[decision_col].min().date()
                max_decision = view[decision_col].max().date()
                decision_range = st.date_input(
                    "H-1B decision date range",
                    value=(min_decision, max_decision),
                    min_value=min_decision,
                    max_value=max_decision,
                )
                if isinstance(decision_range, (tuple, list)) and len(decision_range) == 2:
                    view = view.loc[view[decision_col].dt.date.between(*decision_range)]

        weights = pd.to_numeric(view[filing_col], errors="coerce").fillna(0) if filing_col else pd.Series(1, index=view.index)
        total = weights.sum()
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Filings / decisions", compact_number(total))
        m2.metric("Employers", compact_number(view[employer_col].nunique()) if employer_col else "n.a.")
        m3.metric("States", int(view[state_col].nunique()) if state_col else 0)
        if approval_col and denial_col:
            approvals = pd.to_numeric(view[approval_col], errors="coerce").fillna(0).sum()
            denials = pd.to_numeric(view[denial_col], errors="coerce").fillna(0).sum()
            rate = approvals / (approvals + denials) if approvals + denials else 0
            m4.metric("Approval rate", f"{rate:.1%}")
        elif status_col:
            status_upper = view[status_col].fillna("").astype(str).str.upper()
            decided = status_upper.ne("")
            certification_rate = status_upper.str.contains("CERTIFIED").sum() / decided.sum() if decided.sum() else 0
            m4.metric("Certification share", f"{certification_rate:.1%}")
        else:
            m4.metric("Filtered rows", compact_number(len(view)))
        annual_wages = annualized_wage(view)
        plausible_wages = annual_wages.loc[annual_wages.between(10_000, 2_000_000)]
        m5.metric("Median offered annual wage", f"${plausible_wages.median():,.0f}" if len(plausible_wages) else "n.a.")

        if decision_col:
            monthly = (
                view.dropna(subset=[decision_col])
                .assign(month=lambda data: data[decision_col].dt.to_period("M").dt.to_timestamp(), _filings=weights)
                .groupby("month", as_index=False)["_filings"]
                .sum()
            )
            st.markdown("### H-1B EDA 1 of 5: Employment-pathway demand over time")
            st.caption("Monthly LCA decisions show employer demand for the H-1B pathway, not the number of international students hired.")
            st.plotly_chart(
                px.line(monthly, x="month", y="_filings", markers=True, labels={"_filings": "Filings"}),
                use_container_width=True,
            )

        if decision_col and status_col:
            status_values = view[status_col].fillna("").astype(str).str.upper()
            status_group = pd.Series("Other", index=view.index)
            status_group.loc[status_values.str.contains("CERTIFIED")] = "Certified"
            status_group.loc[status_values.str.contains("DENIED")] = "Denied"
            status_group.loc[status_values.str.contains("WITHDRAWN") & ~status_values.str.contains("CERTIFIED")] = "Withdrawn"
            outcome_month = (
                view.assign(
                    month=view[decision_col].dt.to_period("M").dt.to_timestamp(),
                    outcome=status_group,
                    _filings=weights,
                )
                .dropna(subset=["month"])
                .groupby(["month", "outcome"], as_index=False)["_filings"]
                .sum()
            )
            outcome_month["share"] = outcome_month["_filings"] / outcome_month.groupby("month")["_filings"].transform("sum")
            st.markdown("### H-1B EDA 2 of 5: Filing outcomes over time")
            st.caption("Shows whether the mix of certified, denied and withdrawn LCAs changes across months.")
            st.plotly_chart(
                px.area(
                    outcome_month,
                    x="month",
                    y="share",
                    color="outcome",
                    groupnorm=None,
                    range_y=[0, 1],
                    color_discrete_map={"Certified": "#238B45", "Denied": "#C0392B", "Withdrawn": "#D4A017", "Other": "#7F8C8D"},
                    labels={"share": "Share of monthly filings"},
                ),
                use_container_width=True,
            )

        if state_col:
            state_summary = (
                view.assign(_filings=weights)
                .groupby(state_col, as_index=False)["_filings"]
                .sum()
                .sort_values("_filings", ascending=False)
            )
            state_summary["share"] = state_summary["_filings"] / state_summary["_filings"].sum()
            top_five_share = state_summary.head(5)["share"].sum()
            st.markdown("### H-1B EDA 3 of 5: Geographic concentration of opportunity")
            st.caption(f"The five largest employer states account for {top_five_share:.1%} of filtered filings.")
            st.plotly_chart(
                px.choropleth(
                    state_summary,
                    locations=state_col,
                    locationmode="USA-states",
                    color="share",
                    scope="usa",
                    color_continuous_scale="Blues",
                    labels={"share": "Share of filings", state_col: "State"},
                ),
                use_container_width=True,
            )

        occupation_col = find_col(view, ["soc_title", "job_title"])
        if occupation_col:
            occupation_summary = (
                view.assign(_filings=weights)
                .groupby(occupation_col, as_index=False)["_filings"]
                .sum()
                .nlargest(20, "_filings")
            )
            occupation_summary["share"] = occupation_summary["_filings"] / total if total else 0
            st.markdown("### H-1B EDA 4 of 5: Occupational pathways available to graduates")
            st.caption("Highlights which occupations dominate employer filings and how concentrated the pathway is by field.")
            st.plotly_chart(
                px.bar(
                    occupation_summary,
                    x="share",
                    y=occupation_col,
                    orientation="h",
                    labels={"share": "Share of filtered filings", occupation_col: "Occupation"},
                ).update_layout(yaxis={"categoryorder": "total ascending"}),
                use_container_width=True,
            )

            wage_frame = pd.DataFrame(
                {
                    "occupation": view[occupation_col],
                    "annual_wage": annual_wages,
                }
            )
            wage_frame = wage_frame.loc[wage_frame["annual_wage"].between(10_000, 2_000_000)].dropna()
            wage_summary = (
                wage_frame.groupby("occupation")["annual_wage"]
                .agg(filings="size", median="median", p25=lambda values: values.quantile(0.25), p75=lambda values: values.quantile(0.75))
                .reset_index()
                .nlargest(15, "filings")
            )
            wage_summary["upper"] = wage_summary["p75"] - wage_summary["median"]
            wage_summary["lower"] = wage_summary["median"] - wage_summary["p25"]
            st.markdown("### H-1B EDA 5 of 5: Wage access by major occupation")
            st.caption("Dots are median annualized offered wages; error bars show the 25th–75th percentile range.")
            st.plotly_chart(
                px.scatter(
                    wage_summary,
                    x="median",
                    y="occupation",
                    size="filings",
                    error_x="upper",
                    error_x_minus="lower",
                    labels={"median": "Annualized offered wage (USD)", "occupation": "Occupation", "filings": "Filings"},
                ),
                use_container_width=True,
            )

        st.subheader("H-1B records")
        st.dataframe(view.head(10000), hide_index=True, use_container_width=True)
        st.download_button(
            "Download filtered H-1B CSV",
            view.to_csv(index=False).encode("utf-8"),
            file_name="h1b_filtered.csv",
            mime="text/csv",
        )

with methods_tab:
    st.markdown(
        """
        ### Scope

        YouTube videos are discovered with configurable English-language search queries. A bounded sample of public comments and replies is filtered by comment date. Videos with disabled or inaccessible comments are recorded as unavailable during collection.

        ### Comment measures

        Sentiment is a transparent English keyword score, normalized for comment length. It is descriptive and can miss sarcasm, multilingual wording and context. Policy-impact themes use explicit keyword rules, and one comment may be assigned to several themes. Review the labeled comment table before reporting conclusions.

        ### H-1B interpretation

        The automatic H-1B refresh combines DOL FY2025 and the latest FY2026 cumulative disclosure release, then keeps decisions dated January 1, 2025 or later. USCIS Employer Data Hub records are aggregated petition decisions, while DOL disclosure records are Labor Condition Applications; they are different administrative stages.

        ### Limitations

        YouTube search does not provide a representative sample of all international students, commenter identities are not used to verify student status, and deleted comments are unavailable. H-1B LCAs measure employer filings rather than F-1 enrollment, visa revocations or individual student outcomes. A shared time pattern does not establish that a Trump administration action caused either series. The current latest DOL file is FY2026 Q3, covering decisions through June 30, 2026.
        """
    )

