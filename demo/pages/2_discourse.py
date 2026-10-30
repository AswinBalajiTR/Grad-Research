"""Reviewed Reddit discussion, sentiment, and concern themes."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard_common import (
    CODE_ROOT, DATA_ROOT, REDDIT_THEMES_PATH, THEME_PATTERNS,
    comment_themes, load_data,
)

REDDIT_COMMENTS_PATH = DATA_ROOT / "reddit/processed/reddit_reviewed_comments.jsonl"
POLICY_EVENTS_PATH = DATA_ROOT / "policy_timeline/policy_events_to_verify.csv"
SENTIMENT_LABELS = {
    "negative": "Negative", "neutral": "Neutral",
    "positive": "Positive", "unclassifiable": "Unclear",
}
THEMES = list(THEME_PATTERNS)  # concern themes; "Other discussion" is left out of the event charts
SENTIMENT_COLORS = ["#e86d6d", "#87919f", "#4caf8a", "#a67acb"]  # same order and colors as the Sentiment tab
BEFORE, AFTER = "#9a9893", "#2a78d6"


@st.cache_data(show_spinner=False)
def read_reddit_comments(path: str, modified_ns: int) -> pd.DataFrame:
    with Path(path).open(encoding="utf-8") as source:
        return pd.DataFrame(json.loads(line) for line in source if line.strip())


def load_reddit_comments() -> pd.DataFrame:
    if REDDIT_COMMENTS_PATH.exists() and REDDIT_COMMENTS_PATH.stat().st_size:
        return read_reddit_comments(str(REDDIT_COMMENTS_PATH), REDDIT_COMMENTS_PATH.stat().st_mtime_ns)
    return pd.DataFrame()


def event_labels() -> dict[str, str]:
    """event_id -> title from the Reddit collection manifest."""
    manifest = CODE_ROOT / "reddit/config/policy_batch_scope.json"
    if not manifest.exists():
        return {}
    return {event["event_id"]: event.get("title", event["event_id"])
            for event in json.loads(manifest.read_text()).get("events", [])}


def comment_frame(labels: dict[str, str]) -> pd.DataFrame:
    """Reviewed comments with event label, themes, and posting time; empty if unavailable."""
    comments = load_reddit_comments()
    if comments.empty or not {"event_id", "comment_id", "body", "sentiment", "posted_utc"}.issubset(comments.columns):
        return pd.DataFrame()
    comments = comments.drop_duplicates(subset=["event_id", "comment_id"]).copy()
    comments["event"] = comments["event_id"].map(lambda event: f"{labels.get(event, event)} ({event})")
    comments["themes"] = comments["body"].fillna("").map(comment_themes)
    # Timestamps come with and without fractional seconds.
    comments["posted_utc"] = pd.to_datetime(comments["posted_utc"], errors="coerce", utc=True, format="ISO8601")
    return comments


def theme_shares(frame: pd.DataFrame) -> pd.Series:
    """Percent of comments that mention each concern theme (a comment can mention several)."""
    if frame.empty:
        return pd.Series(0.0, index=THEMES)
    return pd.Series({theme: 100 * frame["themes"].map(lambda themes: theme in themes).mean() for theme in THEMES})


def before_after_bars(before: pd.Series, after: pd.Series, n_before: int, n_after: int):
    fig = go.Figure()
    for name, values, color, n in (("Before", before, BEFORE, n_before), ("After", after, AFTER, n_after)):
        fig.add_trace(go.Bar(
            x=values.values, y=values.index, orientation="h", name=f"{name} (n={n})",
            marker=dict(color=color, cornerradius=4), text=[f"{value:.0f}%" for value in values.values],
            textposition="outside", cliponaxis=False,
            hovertemplate=f"<b>%{{y}}</b><br>{name}: %{{x:.0f}}% of {n} comments<extra></extra>",
        ))
    fig.update_layout(height=420, barmode="group", bargap=.3, margin=dict(l=10, r=40, t=10, b=10),
                      legend=dict(orientation="h", y=1.08, x=0))
    fig.update_xaxes(range=[0, max(before.max(), after.max(), 10) * 1.2], ticksuffix="%",
                     title="Share of comments mentioning the theme", showgrid=True,
                     gridcolor="rgba(128,128,128,.18)")
    fig.update_yaxes(showgrid=False, autorange="reversed")
    return fig


def tone_bars(before: pd.DataFrame, after: pd.DataFrame):
    """One 100% bar per side, split by sentiment, so the before/after tone reads at a glance."""
    sides = {f"Before ({len(before)})": before, f"After ({len(after)})": after}
    fig = go.Figure()
    for key, color in zip(SENTIMENT_LABELS, SENTIMENT_COLORS):
        counts = [int((side["sentiment"] == key).sum()) for side in sides.values()]
        shares = [100 * count / len(side) for count, side in zip(counts, sides.values())]
        fig.add_trace(go.Bar(
            x=shares, y=list(sides), orientation="h", name=SENTIMENT_LABELS[key],
            marker=dict(color=color, line=dict(color="white", width=2)), customdata=counts,
            text=[f"{share:.0f}%" if share >= 4 else "" for share in shares], textposition="inside",
            insidetextanchor="middle",
            hovertemplate=f"<b>%{{y}}</b><br>{SENTIMENT_LABELS[key]}: %{{x:.0f}}% (%{{customdata}} comments)<extra></extra>",
        ))
    fig.update_layout(barmode="stack", height=200, bargap=.35, margin=dict(l=10, r=10, t=40, b=10),
                      title=dict(text="Tone of comments (number of comments in brackets)", font=dict(size=15)),
                      legend=dict(orientation="h", y=-0.15, x=0, traceorder="normal"))
    fig.update_xaxes(range=[0, 100], showgrid=False, showticklabels=False)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return fig


def show_comment_list(frame: pd.DataFrame, limit: int = 5) -> None:
    if frame.empty:
        st.caption("No comments.")
    for _, row in frame.sort_values("posted_utc").head(limit).iterrows():
        body = textwrap.shorten(str(row["body"]), 280, placeholder="…")
        st.markdown(f"**{row['posted_utc']:%b %d, %Y}** · {SENTIMENT_LABELS.get(row['sentiment'], 'Unclear')}  \n{body}")


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


st.title("Reddit discussions")
st.caption("Policy window · since January 2025")
reddit_tab, events_tab, methods_tab = st.tabs(["Reddit comments", "Policy events", "Methods"])
labels = event_labels()

with reddit_tab:
    reddit = load_data(REDDIT_THEMES_PATH)
    if reddit.empty:
        st.info("No Reddit theme summary is available. Rebuild the reviewed Reddit dataset and its theme summary first.")
    elif not {"month", "event_id", "theme", "comments"}.issubset(reddit.columns):
        st.error("Reddit theme summary must contain month, event_id, theme, and comments columns.")
    else:
        reddit["event"] = reddit["event_id"].map(lambda event: f"{labels.get(event, event)} ({event})")
        event_col, theme_col = st.columns(2)
        selected_events = event_col.multiselect("Policy events", sorted(reddit["event"].unique()))
        selected_reddit_themes = theme_col.multiselect("Theme (filters all Reddit views)", sorted(reddit["theme"].unique()))
        comments = comment_frame(labels)
        comments_ready = not comments.empty
        if comments_ready:
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
                    "color": SENTIMENT_COLORS,
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

with events_tab:
    linked = comment_frame(labels)
    if linked.empty:
        st.info("Reviewed Reddit comments are not available in the local data folder.")
    else:
        # How do online narratives change before and after specific policy events?
        st.subheader("Before and after an event", help=(
            "Comments were collected from each event's date onward, so the 'before' side is made of comments "
            "gathered for earlier events. Dates use the comment's posting time."))
        timeline = pd.read_csv(POLICY_EVENTS_PATH, encoding="utf-8-sig") if POLICY_EVENTS_PATH.exists() else pd.DataFrame()
        if timeline.empty:
            st.info("The policy timeline file is not available.")
        else:
            timeline["event_date"] = pd.to_datetime(timeline["event_date"], errors="coerce")
            timeline = timeline.dropna(subset=["event_date"]).sort_values("event_date").reset_index(drop=True)
            posted = linked.dropna(subset=["posted_utc"]).assign(day=lambda data: data["posted_utc"].dt.tz_localize(None))
            c1, c2 = st.columns([3, 1])
            days = c2.select_slider("Days on each side", [7, 14, 30, 60, 90], value=30)

            def split(row):
                when = pd.Timestamp(row.event_date)
                start, end = when - pd.Timedelta(days=int(days)), when + pd.Timedelta(days=int(days) + 1)
                return (posted[(posted.day >= start) & (posted.day < when)],
                        posted[(posted.day >= when) & (posted.day < end)])

            # Default to the event with the most comments on its thinner side.
            balance = [min(len(side) for side in split(row)) for row in timeline.itertuples()]
            pick = c1.selectbox(
                "Policy event", timeline.index, index=int(pd.Series(balance).idxmax()),
                format_func=lambda i: f"{timeline.event_date[i]:%b %d, %Y} · {timeline.title[i]}")
            before, after = split(timeline.loc[pick])
            if before.empty or after.empty:
                st.info(f"Only {len(before)} comments before and {len(after)} after within {days} days. "
                        "Widen the window or pick another event.")
            else:
                st.plotly_chart(tone_bars(before, after), width="stretch")
                st.plotly_chart(before_after_bars(theme_shares(before), theme_shares(after), len(before), len(after)),
                                width="stretch")
                with st.expander("Read comments from each side"):
                    left, right = st.columns(2)
                    with left:
                        st.markdown("**Before**")
                        show_comment_list(before)
                    with right:
                        st.markdown("**After**")
                        show_comment_list(after)

with methods_tab:
    st.markdown("""
- **Reddit:** manually reviewed records.
- **Themes:** keyword matches; may overlap.
- **Other discussion:** no theme match.
- **Policy events:** comments are linked to the event they were collected for; before/after uses posting dates.
- **Limits:** student status and policy effects are unverified.
""")
