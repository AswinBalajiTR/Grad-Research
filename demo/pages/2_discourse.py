"""Collected Reddit discussion, sentiment, and concern themes."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard_common import (
    CODE_ROOT, DATA_ROOT, REDDIT_THEMES_PATH,
    comment_themes, load_data,
)

REDDIT_COMMENTS_PATH = DATA_ROOT / "reddit/processed/reddit_reviewed_comments.jsonl"
ALL_COMMENTS_PATH = DATA_ROOT / "reddit/processed/reddit_sentiment_all_comments.jsonl"
COVERAGE_PATH = DATA_ROOT / "reddit/processed/reddit_collection_coverage_by_policy.csv"
SENTIMENT_LABELS = {
    "negative": "Negative", "neutral": "Neutral",
    "positive": "Positive", "unclassifiable": "Unclear",
}


@st.cache_data(show_spinner=False)
def read_reddit_comments(path: str, modified_ns: int) -> pd.DataFrame:
    with Path(path).open(encoding="utf-8") as source:
        return pd.DataFrame(json.loads(line) for line in source if line.strip())


def load_reddit_comments() -> pd.DataFrame:
    path = ALL_COMMENTS_PATH if ALL_COMMENTS_PATH.exists() and ALL_COMMENTS_PATH.stat().st_size else REDDIT_COMMENTS_PATH
    if path.exists() and path.stat().st_size:
        return read_reddit_comments(str(path), path.stat().st_mtime_ns)
    return pd.DataFrame()


def theme_counts_for_comments(comments: pd.DataFrame) -> pd.DataFrame:
    body = comments["body"].fillna("").astype(str).str.strip().str.lower()
    usable = comments.loc[~body.isin({"", "[removed]", "[deleted]"})].copy()
    usable["month"] = pd.to_datetime(usable["posted_utc"], errors="coerce", utc=True).dt.strftime("%Y-%m")
    usable["theme"] = usable["body"].fillna("").map(comment_themes)
    return (usable.explode("theme").groupby(["month", "event_id", "theme"], dropna=False)
            .size().reset_index(name="comments"))


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


st.title("Reddit sentiment")
st.caption("Policy window · since January 2025")
coverage = load_data(COVERAGE_PATH)
full_comments = load_reddit_comments()
all_labeled = (
    ALL_COMMENTS_PATH.exists() and not coverage.empty
    and len(full_comments) == int(coverage.collected_comments.sum())
    and {"sentiment", "sentiment_source", "event_id", "post_id", "comment_id"}.issubset(full_comments.columns)
    and full_comments["sentiment"].isin(SENTIMENT_LABELS).all()
    and not full_comments.duplicated(["event_id", "post_id", "comment_id"]).any()
)
if not coverage.empty:
    collected = int(coverage.collected_comments.sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("Comments collected", f"{collected:,}")
    if all_labeled:
        body = full_comments["body"].fillna("").astype(str).str.strip().str.lower()
        c2.metric("Comments with text", f"{int((~body.isin({'', '[removed]', '[deleted]'})).sum()):,}")
        c3.metric("Policy discussions", f"{full_comments['post_id'].nunique():,}")
    else:
        c2.metric("Comments analyzed", f"{len(full_comments):,}")
        c3.metric("Policy discussions", "19")
    if all_labeled:
        st.caption("Sentiment reflects the commenter's reaction to the policy or its direct effects.")
    else:
        st.caption("Sentiment analysis is available for the comments shown below.")
reddit_tab, methods_tab = st.tabs(["Results", "About the data"])

with reddit_tab:
    reddit = theme_counts_for_comments(full_comments) if all_labeled else load_data(REDDIT_THEMES_PATH)
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
        comments = full_comments.copy()
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
                if all_labeled:
                    body = comments["body"].fillna("").astype(str).str.strip().str.lower()
                    comments = comments.loc[~body.isin({"", "[removed]", "[deleted]"})]
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
                st.caption(f"{len(comments):,} collected comments · author reaction to policy or its direct effects")
                fig = px.bar(sentiment, x="Comments", y="Sentiment", orientation="h",
                             text="Comments", color="Sentiment",
                             color_discrete_map=dict(zip(sentiment["Sentiment"], sentiment["color"])))
                fig.update_traces(textposition="outside", cliponaxis=False, width=0.55)
                fig.update_layout(height=300, showlegend=False, margin=dict(l=10, r=35, t=10, b=25),
                                  yaxis={"categoryorder": "array", "categoryarray": list(reversed(sentiment["Sentiment"]))})
                fig.update_xaxes(range=[0, max(1, sentiment["Comments"].max() * 1.16)], rangemode="tozero")
                st.plotly_chart(fig, width="stretch")
                st.subheader("Sentiment by policy event")
                event_counts = (comments.groupby(["event_id", "sentiment"]).size()
                                .unstack(fill_value=0).reindex(columns=list(SENTIMENT_LABELS), fill_value=0))
                event_counts["comments"] = event_counts.sum(axis=1)
                event_counts = event_counts.sort_index()
                event_counts["date"] = [
                    f"{event_id[-8:-4]}-{event_id[-4:-2]}-{event_id[-2:]}"
                    for event_id in event_counts.index]
                topics = comments.drop_duplicates("event_id").set_index("event_id")["policy_topic"]
                event_counts["short_policy"] = [
                    f"{event_counts.at[event_id, 'date']} · {topics.get(event_id, 'Policy event')}"
                    for event_id in event_counts.index]
                event_counts["full_policy"] = [
                    labels.get(event_id, event_id) for event_id in event_counts.index]
                event_fig = go.Figure()
                policy_colors = {"negative": "#e86d6d", "neutral": "#87919f",
                                 "positive": "#4caf8a", "unclassifiable": "#a67acb"}
                for name in SENTIMENT_LABELS:
                    event_fig.add_trace(go.Bar(
                        x=event_counts[name], y=event_counts["short_policy"], orientation="h",
                        name=SENTIMENT_LABELS[name], marker_color=policy_colors[name],
                        customdata=event_counts["full_policy"],
                        hovertemplate=f"<b>%{{customdata}}</b><br>{SENTIMENT_LABELS[name]}: %{{x}}<extra></extra>"))
                event_fig.update_layout(barmode="stack", height=max(420, 48 * len(event_counts) + 100),
                                        margin=dict(l=10, r=25, t=25, b=35),
                                        legend=dict(orientation="h", y=1.12, x=0))
                event_fig.update_xaxes(title="Collected comments" if all_labeled else "Reviewed comments")
                event_fig.update_yaxes(autorange="reversed", showgrid=False)
                st.plotly_chart(event_fig, width="stretch")
                st.caption("Full policy titles and counts")
                table = event_counts[["date", "full_policy", "comments", *SENTIMENT_LABELS]].rename(columns={
                    "date": "Date", "full_policy": "Policy", "comments": "Total",
                    **{key: label for key, label in SENTIMENT_LABELS.items()},
                })
                st.markdown("""
<style>
.reddit-policy-table-wrap {overflow-x: auto; width: 100%;}
.reddit-policy-table {border-collapse: collapse; width: 100%; table-layout: fixed;}
.reddit-policy-table th, .reddit-policy-table td {padding: .55rem .65rem; border-bottom: 1px solid rgba(128,128,128,.3); vertical-align: top;}
.reddit-policy-table th {text-align: left;}
.reddit-policy-table th:nth-child(2), .reddit-policy-table td:nth-child(2) {width: 46%; white-space: normal; overflow-wrap: anywhere;}
.reddit-policy-table td:not(:nth-child(2)) {white-space: nowrap;}
@media (max-width: 800px) {.reddit-policy-table {min-width: 800px;}}
</style>
<div class="reddit-policy-table-wrap">
""" + table.to_html(index=False, escape=True, border=0, classes="reddit-policy-table") + "</div>",
                            unsafe_allow_html=True)
                st.caption("Neutral includes factual information, questions, and advice. Unclear means no reliable opinion could be assigned. "
                           "These are collected comments under policy-linked posts, not a representative sample of students or Reddit users. "
                           "Some policy entries still await source verification.")
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
            st.caption("Collected comments with usable text · themes may overlap" if all_labeled else "Reviewed sample · themes may overlap")
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
    if all_labeled:
        st.markdown("""
- **Source:** 2,810 comments from 19 Reddit posts about nine policy events.
- **Labels:** a local AI model classified usable comments by their reaction to the policy or its direct effects. Selected labels were checked and corrected with AI assistance. Questions and factual replies without a stance are neutral; deleted or empty comments are unclear.
- **Themes:** simple keyword matches; a comment may match more than one theme.
- **Limit:** these comments are not a representative survey, and AI labels may be wrong.
""")
    else:
        st.markdown("""
- **Reddit:** manually reviewed records.
- **Themes:** keyword matches; may overlap.
- **Other discussion:** no theme match.
- **Limits:** student status and policy effects are unverified.
""")
