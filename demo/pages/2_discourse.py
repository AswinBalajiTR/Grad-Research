"""YouTube and Reddit discussion, compared using the same concern themes."""
from __future__ import annotations

import json
import re
from collections import Counter
from itertools import combinations
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard_common import (
    CODE_ROOT, DATA_ROOT, REDDIT_THEMES_PATH, THEME_PATTERNS, YOUTUBE_PATH,
    comment_themes, compact_number, find_col, load_data, run_collector,
)

REDDIT_COMMENTS_PATH = DATA_ROOT / "reddit/processed/reddit_reviewed_comments.jsonl"
SENTIMENT_LABELS = {
    "negative": "Negative", "neutral": "Neutral",
    "positive": "Positive", "unclassifiable": "Unclear",
}


@st.cache_data(show_spinner=False)
def read_reddit_comments(path: str, modified_ns: int) -> pd.DataFrame:
    with Path(path).open(encoding="utf-8") as source:
        return pd.DataFrame(json.loads(line) for line in source if line.strip())


def load_reddit_comments() -> pd.DataFrame:
    if REDDIT_COMMENTS_PATH.exists() and REDDIT_COMMENTS_PATH.stat().st_size:
        return read_reddit_comments(str(REDDIT_COMMENTS_PATH), REDDIT_COMMENTS_PATH.stat().st_mtime_ns)
    return pd.DataFrame()


def show_theme_totals(counts: pd.DataFrame, theme_column: str) -> None:
    """Keep sparse theme results readable without a full-height single bar."""
    counts = counts.sort_values("comments")
    if len(counts) == 1:
        row = counts.iloc[0]
        st.metric(str(row[theme_column]), f"{int(row['comments']):,} comments")
        st.caption("Select more themes to compare counts.")
        return

    maximum = int(counts["comments"].max())
    fig = px.bar(counts, x="comments", y=theme_column, orientation="h", text="comments")
    fig.update_traces(marker_color="#2a78d6", width=0.55, textposition="outside", cliponaxis=False)
    fig.update_layout(height=max(180, 48 * len(counts) + 75), showlegend=False,
                      margin=dict(l=10, r=35, t=15, b=40), bargap=0.35,
                      xaxis_title="Comments", yaxis_title=None)
    fig.update_xaxes(range=[0, max(1, maximum * 1.16)], dtick=1 if maximum <= 10 else None,
                     showgrid=True, gridcolor="rgba(128,128,128,.18)")
    fig.update_yaxes(showgrid=False)
    st.plotly_chart(fig, use_container_width=True)


st.title("Student discussions")
st.caption("Policy window · since January 2025")
youtube_tab, reddit_tab, methods_tab = st.tabs(["YouTube comments", "Reddit comments", "Methods"])

with youtube_tab:
    with st.expander("Collect comments"):
        video_limit = st.slider("Videos to collect", 1, 60, 3)
        comment_limit = st.slider("Maximum comments per video", 25, 500, 50, step=25)
        refresh = st.button("Refresh YouTube")
    if refresh:
        with st.spinner("Collecting YouTube comments for up to three minutes..."):
            ok, message = run_collector([
                "code/youtube/collect_youtube.py", "--max-videos", str(video_limit),
                "--max-comments-per-video", str(comment_limit), "--time-budget-seconds", "180",
            ], timeout=240)
        (st.success if ok else st.error)("YouTube refresh completed" if ok else "YouTube refresh failed")
        if message:
            st.code(message)
    youtube = load_data(YOUTUBE_PATH)
    if youtube.empty:
        st.info("No YouTube comments are loaded. Use Refresh YouTube to collect them, or run the collector from the command line.")
    else:
        date_col = find_col(youtube, ["date", "published_at", "comment_date"])
        comment_col = find_col(youtube, ["youtube_comment", "comment", "text"])
        if not date_col or not comment_col:
            st.error("YouTube CSV must contain date and youtube_comment columns.")
        else:
            view = youtube.copy()
            view[date_col] = pd.to_datetime(view[date_col], errors="coerce", utc=True)
            view = view.dropna(subset=[date_col, comment_col])
            view["themes"] = view[comment_col].map(comment_themes)
            if view.empty:
                st.warning("The YouTube file contains no dated comments.")
            else:
                start, end = view[date_col].min().date(), view[date_col].max().date()
                with st.expander("Filters"):
                    f1, f2, f3 = st.columns(3)
                    selected_dates = f1.date_input("Date range", value=(start, end), min_value=start, max_value=end)
                    keyword = f2.text_input("Contains")
                    selected_themes = f3.multiselect("Themes", list(THEME_PATTERNS) + ["Other discussion"])
                if isinstance(selected_dates, (tuple, list)) and len(selected_dates) == 2:
                    view = view.loc[view[date_col].dt.date.between(*selected_dates)]
                if keyword:
                    view = view.loc[view[comment_col].astype(str).str.contains(keyword, case=False, regex=False, na=False)]
                if selected_themes:
                    view = view.loc[view["themes"].map(lambda themes: bool(set(themes) & set(selected_themes)))]
                st.metric("Filtered YouTube comments", compact_number(len(view)))
                if view.empty:
                    st.info("No comments match these filters.")
                else:
                    view = view.copy()
                    view["week"] = view[date_col].dt.tz_localize(None).dt.to_period("W").dt.start_time
                    view["month"] = view[date_col].dt.tz_localize(None).dt.to_period("M").dt.to_timestamp()
                    view["has_theme"] = view["themes"].map(lambda themes: themes != ["Other discussion"])
                    weekly = view.groupby("week", as_index=False).agg(comments=(comment_col, "size"), theme_share=("has_theme", "mean"))
                    exploded = view[["month", "themes", comment_col]].explode("themes")
                    theme_counts = exploded.groupby("themes", as_index=False).size().rename(columns={"size": "comments"})
                    monthly = exploded.groupby(["month", "themes"], as_index=False).size().rename(columns={"size": "comments"})
                    theme_names = list(THEME_PATTERNS)
                    cooccurrence = pd.DataFrame(0, index=theme_names, columns=theme_names, dtype=int)
                    for themes in view["themes"]:
                        present = [name for name in set(themes) if name in cooccurrence.index]
                        for name in present:
                            cooccurrence.loc[name, name] += 1
                        for left, right in combinations(present, 2):
                            cooccurrence.loc[left, right] += 1
                            cooccurrence.loc[right, left] += 1
                    stopwords = {"the", "and", "for", "that", "this", "with", "have", "from", "are", "you", "was", "but", "not", "they", "about", "would", "will", "your", "can", "has", "just"}
                    words = Counter(token for text in view[comment_col].astype(str) for token in re.findall(r"[a-zA-Z]{3,}", text.lower()) if token not in stopwords)
                    word_counts = pd.DataFrame(words.most_common(20), columns=["word", "count"])
                    table = view[[date_col, "themes", comment_col]].copy()
                    table["themes"] = table["themes"].map(", ".join)
                    activity_tab, themes_tab, overlap_tab, words_tab = st.tabs(
                        ["Activity", "Themes", "Overlap", "Words"])
                    with activity_tab:
                        measure = st.radio("View", ["Comments", "Theme share"], horizontal=True)
                        if measure == "Comments":
                            st.plotly_chart(px.line(weekly, x="week", y="comments", markers=True,
                                                    labels={"comments": "Comments"}), use_container_width=True)
                        else:
                            st.plotly_chart(px.line(weekly, x="week", y="theme_share", markers=True,
                                                    range_y=[0, 1], labels={"theme_share": "Theme share"}),
                                            use_container_width=True)
                    with themes_tab:
                        totals_tab, monthly_tab = st.tabs(["Totals", "By month"])
                        with totals_tab:
                            st.caption("Themes may overlap.")
                            show_theme_totals(theme_counts, "themes")
                        with monthly_tab:
                            st.plotly_chart(px.line(monthly, x="month", y="comments", color="themes", markers=True),
                                            use_container_width=True)
                    with overlap_tab:
                        st.plotly_chart(px.imshow(cooccurrence, text_auto=True,
                                                 color_continuous_scale="Blues", aspect="auto"),
                                        use_container_width=True)
                    with words_tab:
                        if not word_counts.empty:
                            st.plotly_chart(px.bar(word_counts, x="count", y="word", orientation="h")
                                            .update_layout(yaxis={"categoryorder": "total ascending"}),
                                            use_container_width=True)
                    with st.expander("Comment records"):
                        st.dataframe(table.sort_values(date_col, ascending=False), hide_index=True,
                                     use_container_width=True)

with reddit_tab:
    reddit = load_data(REDDIT_THEMES_PATH)
    if reddit.empty:
        st.info("No Reddit theme summary is available. Rebuild the reviewed Reddit dataset and its theme summary first.")
    elif not {"month", "event_id", "theme", "comments"}.issubset(reddit.columns):
        st.error("Reddit theme summary must contain month, event_id, theme, and comments columns.")
    else:
        manifest = CODE_ROOT / "reddit/config/policy_batch_scope.json"
        labels = {}
        if manifest.exists():
            labels = {event["event_id"]: event.get("title", event["event_id"]) for event in json.loads(manifest.read_text()).get("events", [])}
        reddit["event"] = reddit["event_id"].map(lambda event: f"{labels.get(event, event)} ({event})")
        event_col, theme_col = st.columns(2)
        selected_events = event_col.multiselect("Policy events", sorted(reddit["event"].unique()))
        selected_reddit_themes = theme_col.multiselect("Theme (filters all Reddit views)", sorted(reddit["theme"].unique()))
        comments = load_reddit_comments()
        comment_columns = {"event_id", "comment_id", "body", "sentiment", "posted_utc"}
        comments_ready = not comments.empty and comment_columns.issubset(comments.columns)
        if comments_ready:
            comments = comments.drop_duplicates(subset=["event_id", "comment_id"]).copy()
            comments["event"] = comments["event_id"].map(lambda event: f"{labels.get(event, event)} ({event})")
            comments["themes"] = comments["body"].fillna("").map(comment_themes)
            comments["posted_utc"] = pd.to_datetime(comments["posted_utc"], errors="coerce", utc=True)
            if selected_events:
                comments = comments.loc[comments["event"].isin(selected_events)]
            if selected_reddit_themes:
                chosen = set(selected_reddit_themes)
                comments = comments.loc[comments["themes"].map(lambda themes: bool(chosen.intersection(themes)))]
        if selected_events:
            reddit = reddit.loc[reddit["event"].isin(selected_events)]
        if selected_reddit_themes:
            reddit = reddit.loc[reddit["theme"].isin(selected_reddit_themes)]
        reddit["comments"] = pd.to_numeric(reddit["comments"], errors="coerce").fillna(0)
        sentiment_tab, comments_tab, themes_tab = st.tabs(["Sentiment", "Read comments", "Themes"])
        with sentiment_tab:
            if not comments_ready:
                st.info("Reviewed Reddit comments and sentiment labels are not available in the local data folder.")
            elif comments.empty:
                st.info("No comments match these filters.")
            else:
                counts = comments["sentiment"].value_counts()
                sentiment = pd.DataFrame({
                    "Sentiment": list(SENTIMENT_LABELS.values()),
                    "Comments": [int(counts.get(key, 0)) for key in SENTIMENT_LABELS],
                    "color": ["#e86d6d", "#87919f", "#4caf8a", "#a67acb"],
                })
                st.caption(f"{len(comments):,} reviewed comments · author reaction to policy or its direct effects")
                fig = px.bar(sentiment, x="Comments", y="Sentiment", orientation="h",
                             text="Comments", color="Sentiment",
                             color_discrete_map=dict(zip(sentiment["Sentiment"], sentiment["color"])))
                fig.update_traces(textposition="outside", cliponaxis=False, width=0.55)
                fig.update_layout(height=300, showlegend=False, margin=dict(l=10, r=35, t=10, b=25),
                                  yaxis={"categoryorder": "array", "categoryarray": list(reversed(sentiment["Sentiment"]))})
                fig.update_xaxes(range=[0, max(1, sentiment["Comments"].max() * 1.16)], rangemode="tozero")
                st.plotly_chart(fig, width="stretch")
                st.caption("Neutral includes factual information, questions, and advice. Unclear means no reliable opinion could be assigned. This reviewed sample does not represent all Reddit users.")
        with comments_tab:
            if not comments_ready:
                st.info("Reviewed Reddit comment text is not available in the local data folder.")
            elif comments.empty:
                st.info("No comments match these filters.")
            else:
                st.caption("Choose a theme above and a sentiment below to read comments matching both. A comment can have multiple themes.")
                filter_col, search_col = st.columns(2)
                selected_sentiments = filter_col.multiselect("Sentiment", list(SENTIMENT_LABELS.values()), key="reddit_comment_sentiment")
                search_text = search_col.text_input("Search comments", key="reddit_comment_search")
                shown = comments.copy()
                shown["sentiment_label"] = shown["sentiment"].map(SENTIMENT_LABELS).fillna("Unclear")
                if selected_sentiments:
                    shown = shown.loc[shown["sentiment_label"].isin(selected_sentiments)]
                if search_text:
                    shown = shown.loc[shown["body"].fillna("").str.contains(search_text, case=False, regex=False)]
                shown = shown.sort_values("posted_utc", ascending=False, na_position="last")
                if shown.empty:
                    st.info("No comments match these filters.")
                else:
                    page_count = (len(shown) + 5) // 6
                    page = st.number_input("Page", min_value=1, max_value=page_count, value=1,
                                           step=1, key="reddit_comment_page")
                    first = (page - 1) * 6
                    st.caption(f"Showing {first + 1}–{min(first + 6, len(shown))} of {len(shown):,} comments")
                    for _, row in shown.iloc[first:first + 6].iterrows():
                        date = row["posted_utc"].strftime("%b %d, %Y") if pd.notna(row["posted_utc"]) else "Date unavailable"
                        subreddit = str(row.get("subreddit") or "Reddit")
                        st.markdown(f"**{date} · r/{subreddit} · {row['sentiment_label']}**")
                        st.caption("Themes: " + ", ".join(row["themes"]))
                        body = str(row["body"])
                        if len(body) > 700:
                            st.write(body[:700].rstrip() + "…")
                            with st.expander("Read full comment"):
                                st.write(body)
                        else:
                            st.write(body)
                        url = row.get("comment_url")
                        if isinstance(url, str) and url.startswith(("https://www.reddit.com/", "http://www.reddit.com/")):
                            st.link_button("Open on Reddit", url)
                        st.divider()
        with themes_tab:
            st.caption("Reviewed sample · themes may overlap")
            st.caption("**Other discussion:** comments with no matches to the seven theme rules.")
            if reddit.empty:
                st.info("No Reddit records match these filters.")
            else:
                by_theme = reddit.groupby("theme", as_index=False)["comments"].sum()
                by_month = reddit.groupby(["month", "theme"], as_index=False)["comments"].sum()
                totals_tab, monthly_tab, records_tab = st.tabs(["Theme totals", "By month", "Records"])
                with totals_tab:
                    show_theme_totals(by_theme, "theme")
                with monthly_tab:
                    st.plotly_chart(px.line(by_month, x="month", y="comments", color="theme", markers=True),
                                    use_container_width=True)
                with records_tab:
                    st.dataframe(reddit[["event", "month", "theme", "comments"]], hide_index=True,
                                 use_container_width=True)

with methods_tab:
    st.markdown("""
- **YouTube:** bounded public sample.
- **Reddit:** manually reviewed records.
- **Themes:** keyword matches; may overlap.
- **Other discussion:** no theme match.
- **Limits:** student status and policy effects are unverified.
""")
