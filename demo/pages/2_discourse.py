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
    CODE_ROOT, REDDIT_THEMES_PATH, THEME_PATTERNS, YOUTUBE_PATH,
    comment_themes, compact_number, find_col, load_data, run_collector,
)

st.title("Student discourse: YouTube and Reddit")
st.caption("Discussion in the policy window starting January 20, 2025. Themes identify topics mentioned, not the writer's attitude or student status.")
youtube_tab, reddit_tab, methods_tab = st.tabs(["YouTube comments", "Reddit themes", "Methods"])

with youtube_tab:
    with st.sidebar:
        st.subheader("YouTube collection")
        video_limit = st.slider("Videos to collect", 1, 60, 3)
        comment_limit = st.slider("Maximum comments per video", 25, 500, 50, step=25)
        refresh = st.button("Refresh YouTube", use_container_width=True)
        st.caption("Collection starts only when you click Refresh.")
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
                selected_dates = st.date_input("Comment date range", value=(start, end), min_value=start, max_value=end)
                keyword = st.text_input("Comment contains")
                selected_themes = st.multiselect("Concern themes", list(THEME_PATTERNS) + ["Other discussion"])
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
                    st.subheader("1. Discussion and concern mentions over time")
                    st.plotly_chart(px.line(weekly, x="week", y="comments", markers=True, labels={"comments": "Comments"}), use_container_width=True)
                    st.plotly_chart(px.line(weekly, x="week", y="theme_share", markers=True, range_y=[0, 1], labels={"theme_share": "Share mentioning a theme"}), use_container_width=True)

                    exploded = view[["month", "themes", comment_col]].explode("themes")
                    theme_counts = exploded.groupby("themes", as_index=False).size().rename(columns={"size": "comments"})
                    st.subheader("2. Which concerns appear most?")
                    st.caption("One comment can mention several themes.")
                    st.plotly_chart(px.bar(theme_counts, x="comments", y="themes", orientation="h").update_layout(yaxis={"categoryorder": "total ascending"}), use_container_width=True)

                    monthly = exploded.groupby(["month", "themes"], as_index=False).size().rename(columns={"size": "comments"})
                    st.subheader("3. How concern themes change by month")
                    st.plotly_chart(px.line(monthly, x="month", y="comments", color="themes", markers=True), use_container_width=True)

                    theme_names = list(THEME_PATTERNS)
                    cooccurrence = pd.DataFrame(0, index=theme_names, columns=theme_names, dtype=int)
                    for themes in view["themes"]:
                        present = [name for name in set(themes) if name in cooccurrence.index]
                        for name in present:
                            cooccurrence.loc[name, name] += 1
                        for left, right in combinations(present, 2):
                            cooccurrence.loc[left, right] += 1
                            cooccurrence.loc[right, left] += 1
                    st.subheader("4. Which concerns appear together?")
                    st.plotly_chart(px.imshow(cooccurrence, text_auto=True, color_continuous_scale="Blues", aspect="auto"), use_container_width=True)

                    st.subheader("5. Common language in the selected comments")
                    stopwords = {"the", "and", "for", "that", "this", "with", "have", "from", "are", "you", "was", "but", "not", "they", "about", "would", "will", "your", "can", "has", "just"}
                    words = Counter(token for text in view[comment_col].astype(str) for token in re.findall(r"[a-zA-Z]{3,}", text.lower()) if token not in stopwords)
                    word_counts = pd.DataFrame(words.most_common(20), columns=["word", "count"])
                    if not word_counts.empty:
                        st.plotly_chart(px.bar(word_counts, x="count", y="word", orientation="h").update_layout(yaxis={"categoryorder": "total ascending"}), use_container_width=True)
                    table = view[[date_col, "themes", comment_col]].copy()
                    table["themes"] = table["themes"].map(", ".join)
                    st.dataframe(table.sort_values(date_col, ascending=False), hide_index=True, use_container_width=True)

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
        selected_events = st.multiselect("Policy events", sorted(reddit["event"].unique()))
        selected_reddit_themes = st.multiselect("Reddit themes", sorted(reddit["theme"].unique()))
        if selected_events:
            reddit = reddit.loc[reddit["event"].isin(selected_events)]
        if selected_reddit_themes:
            reddit = reddit.loc[reddit["theme"].isin(selected_reddit_themes)]
        reddit["comments"] = pd.to_numeric(reddit["comments"], errors="coerce").fillna(0)
        st.caption("Counts are reviewed comment-event records tagged by topic. A comment can have several themes; the sample is not representative of all students.")
        if reddit.empty:
            st.info("No Reddit records match these filters.")
        else:
            by_theme = reddit.groupby("theme", as_index=False)["comments"].sum()
            st.subheader("Concern themes in reviewed Reddit comments")
            st.plotly_chart(px.bar(by_theme, x="comments", y="theme", orientation="h").update_layout(yaxis={"categoryorder": "total ascending"}), use_container_width=True)
            by_month = reddit.groupby(["month", "theme"], as_index=False)["comments"].sum()
            st.subheader("Reddit theme mentions by month")
            st.plotly_chart(px.line(by_month, x="month", y="comments", color="theme", markers=True), use_container_width=True)
            st.dataframe(reddit[["event", "month", "theme", "comments"]], hide_index=True, use_container_width=True)

with methods_tab:
    st.markdown("""YouTube discovery uses configurable searches and a bounded sample of public comments. Reddit counts come from manually reviewed records in the policy collection. Both sources use the same transparent keyword rules in `dashboard_common.py`. These labels describe topics, can overlap, and should be checked against source context before making claims. Neither source identifies every writer as an international student or establishes policy effects.""")
