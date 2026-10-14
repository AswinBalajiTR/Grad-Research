"""Streamlit story page for the mobility layer of the international-student project.

The project asks how online discussion of visa, travel, duration-of-stay, and
post-study work rules shifts over time, and whether it moves together with
international student mobility. This page covers the mobility side: what
happened to fall 2025 international enrollment at universities that publish it.

Reuses the source-linked counts in historical_international_eda.py, so the
numbers here always match the CSV, summary, and findings.md outputs.

Run: streamlit run code/src/historical_dashboard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from historical_international_eda import SOURCES, make_rows, validate  # noqa: E402

# Categorical slots in fixed order; DROP/GAIN are the diverging poles.
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
DROP, GAIN, NEUTRAL = "#e34948", "#2a78d6", "#9a9893"
SCHOOL_COLORS = {"Ohio University": BLUE, "MIT": ORANGE, "University of Hawaiʻi at Hilo": AQUA,
                 "University of Michigan–Ann Arbor": "#7955b3",
                 "University of Illinois Springfield": YELLOW,
                 "University of New Mexico": "#e87ba4", "UC Berkeley": "#008300"}
FONT = dict(family="Inter, system-ui, sans-serif", size=13)

st.set_page_config(page_title="International Enrollment 2025", page_icon="🎓", layout="wide")


@st.cache_data
def load() -> pd.DataFrame:
    rows = make_rows()
    validate(rows)
    return pd.DataFrame(rows)


def value(df, school, year, country="All countries", level="All levels") -> int:
    hit = df[(df.institution == school) & (df.year == year)
             & (df.country == country) & (df.academic_level == level)]
    return int(hit["count"].iloc[0])


def base_layout(fig, height=380, **kw):
    kw.setdefault("margin", dict(l=10, r=10, t=40, b=10))
    fig.update_layout(height=height, font=FONT,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      hoverlabel=dict(font=FONT), **kw)
    fig.update_xaxes(showgrid=False, zeroline=False, automargin=True)
    fig.update_yaxes(gridcolor="rgba(128,128,128,.18)", zeroline=False, automargin=True, title_standoff=12)
    return fig

SHORT = {"University of Michigan–Ann Arbor": "U-M Ann Arbor", "UC Berkeley": "UC Berkeley", "MIT": "MIT",
         "University of New Mexico": "New Mexico", "Ohio University": "Ohio University",
         "University of Illinois Springfield": "Illinois Springfield", "University of Hawaiʻi at Hilo": "UH Hilo"}
UG_COLOR, GRAD_COLOR, ALL_COLOR, INDIA_COLOR = ORANGE, BLUE, NEUTRAL, AQUA


def changes(df, country="All countries", level="All levels") -> pd.DataFrame:
    """2024→2025 change for every institution that publishes both years of this series."""
    p = (df[(df.country == country) & (df.academic_level == level) & df.year.isin([2024, 2025])]
         .pivot_table(index="institution", columns="year", values="count").dropna())
    out = pd.DataFrame({"institution": p.index, "c24": p[2024].astype(int).values,
                        "c25": p[2025].astype(int).values})
    out["label"] = out.institution.map(SHORT)
    out["diff"] = out.c25 - out.c24
    out["pct"] = (100 * (out.c25 / out.c24 - 1)).round(1)
    return out


def paired_bars(rows, series, unit):
    """Horizontal grouped bars: one row per campus, one bar per series (name, column, color)."""
    fig = go.Figure()
    for name, col, color in series:
        vals = rows[col]
        fig.add_trace(go.Bar(
            y=rows["label"], x=vals, name=name, orientation="h", marker=dict(color=color, cornerradius=4),
            text=[f"{v:+.1f}%" if unit == "pct" else f"{v:+,}" for v in vals],
            textposition="outside", cliponaxis=False,
            hovertemplate=f"<b>%{{y}}</b> · {name}<br>%{{text}}<extra></extra>",
        ))
    fig.add_vline(x=0, line=dict(color=NEUTRAL, width=1))
    lo = min(rows[c].min() for _, c, _ in series)
    hi = max(rows[c].max() for _, c, _ in series)
    pad = (hi - min(lo, 0)) * .18 + 1
    fig = base_layout(fig, height=110 + 70 * len(rows), barmode="group", bargap=.3, bargroupgap=.08,
                      legend=dict(orientation="h", y=1.12, x=0, traceorder="normal"))
    fig.update_xaxes(ticksuffix="%" if unit == "pct" else "", range=[min(lo, 0) - pad, max(hi, 0) + pad],
                     showgrid=True, gridcolor="rgba(128,128,128,.18)")
    fig.update_yaxes(showgrid=False, autorange="reversed")
    return fig


def has_series(df, inst, country="All countries", level="All levels") -> bool:
    """True when the campus publishes this series for both Fall 2024 and Fall 2025."""
    hit = df[(df.institution == inst) & (df.country == country) & (df.academic_level == level)
             & df.year.isin([2024, 2025])]
    return len(hit) == 2


SPLITS = {"india": "India vs other countries", "india_level": "India vs other, by level",
          "level": "Undergraduate vs graduate", "total": "Net change only"}


def available_splits(df, inst) -> list[str]:
    found = [key for key, ok in (
        ("india", has_series(df, inst, "India")),
        ("india_level", has_series(df, inst, "India", "Undergraduate")),
        ("level", has_series(df, inst, level="Undergraduate")),
    ) if ok]
    return found or ["total"]


def decompose(df, inst, by) -> dict[str, int]:
    """Split a campus's 2024→2025 change into parts that add up to its total change."""
    def d(country="All countries", level="All levels"):
        return value(df, inst, 2025, country, level) - value(df, inst, 2024, country, level)
    if by == "india":
        return {"India": d("India"), "Other countries": d() - d("India")}
    if by == "india_level":
        return {"India · UG": d("India", "Undergraduate"), "India · Grad": d("India", "Graduate"),
                "Other · UG": d(level="Undergraduate") - d("India", "Undergraduate"),
                "Other · Grad": d(level="Graduate") - d("India", "Graduate")}
    if by == "level":
        return {"Undergraduate": d(level="Undergraduate"), "Graduate": d(level="Graduate")}
    return {"Net change": d()}


def waterfall(df, inst, parts, height=400, title=None):
    start, end = value(df, inst, 2024), value(df, inst, 2025)
    running = [start]
    for v in parts.values():
        running.append(running[-1] + v)
    lo, hi = min(running), max(running)
    pad = max((hi - lo) * .45, hi * .02, 5)
    fig = go.Figure(go.Waterfall(
        x=(["2024", *[k.replace("Other countries", "Other") for k in parts], "2025"] if title
           else ["Fall 2024", *parts, "Fall 2025"]), y=[start, *parts.values(), end],
        measure=["absolute", *["relative"] * len(parts), "total"],
        text=[f"{start:,}", *[f"{v:+,}" for v in parts.values()], f"{end:,}"], textposition="outside",
        decreasing=dict(marker=dict(color=DROP)), increasing=dict(marker=dict(color=GAIN)),
        totals=dict(marker=dict(color=NEUTRAL)), connector=dict(line=dict(color=NEUTRAL, width=1, dash="dot")),
        hovertemplate="<b>%{x}</b><br>%{text}<extra></extra>", cliponaxis=False,
    ))
    fig = base_layout(fig, height=height, title=dict(text=title, x=0, font=dict(size=15)) if title else None)
    fig.update_yaxes(range=[max(0, lo - pad), hi + pad * .6], title="International students" if not title else None)
    fig.update_xaxes(tickangle=0, type="category")
    return fig


def india_share_donut(df, inst):
    """Outer ring: Fall 2025 mix. Inner ring: Fall 2024 mix. Center: India's share."""
    fig = go.Figure()
    shares = {}
    for year, domain, hole, india_color in ((2025, [0, 1], .74, INDIA_COLOR), (2024, [.13, .87], .8, "#8fd6bc")):
        ind, tot = value(df, inst, year, "India"), value(df, inst, year)
        shares[year] = ind / tot
        fig.add_trace(go.Pie(
            labels=["Students from India", "Other countries"], values=[ind, tot - ind], hole=hole, sort=False,
            direction="clockwise", domain=dict(x=domain, y=domain), textinfo="none", name=str(year),
            marker=dict(colors=[india_color, "rgba(154,152,147,.28)"], line=dict(color="white", width=2)),
            hovertemplate=f"<b>%{{label}}</b> · Fall {year}<br>%{{value:,}} students (%{{percent}})<extra></extra>",
        ))
    fig.add_annotation(
        text=f"<b>{shares[2025]:.1%}</b><br><span style='font-size:11px'>from India, 2025<br>"
             f"was {shares[2024]:.1%} in 2024</span>", showarrow=False, font=dict(size=20))
    return base_layout(fig, height=300, showlegend=False, margin=dict(l=10, r=10, t=36, b=10),
                       title=dict(text=SHORT[inst], x=.5, xanchor="center", font=dict(size=15)))


def diverging(summary):
    s = summary.sort_values("pct", ascending=False)
    fig = go.Figure(go.Bar(
        x=s["pct"], y=s["label"], orientation="h",
        marker=dict(color=[DROP if v < 0 else GAIN for v in s["pct"]], cornerradius=4),
        text=[f"{v:+.1f}%" for v in s["pct"]], textposition="outside", cliponaxis=False,
        customdata=s[["c24", "c25"]],
        hovertemplate="<b>%{y}</b><br>Fall 2024: %{customdata[0]:,}<br>Fall 2025: %{customdata[1]:,}"
                      "<br>Change: %{x:+.1f}%<extra></extra>",
    ))
    fig.add_vline(x=0, line=dict(color=NEUTRAL, width=1))
    fig = base_layout(fig, height=90 + 50 * len(s), bargap=.35)
    fig.update_xaxes(ticksuffix="%", range=[s["pct"].min() * 1.35, max(s["pct"].max(), 0) + 8],
                     gridcolor="rgba(128,128,128,.18)", showgrid=True)
    fig.update_yaxes(showgrid=False)
    return fig


def trends(df, indexed, start_year, country="All countries"):
    fig = go.Figure()
    for school, color in SCHOOL_COLORS.items():
        s = df[(df.institution == school) & (df.country == country)
               & (df.academic_level == "All levels") & (df.year >= start_year)].sort_values("year")
        if s.empty:
            continue
        y = 100 * s["count"] / s["count"].iloc[0] if indexed else s["count"]
        fig.add_trace(go.Scatter(
            x=s["year"], y=y, name=school, mode="lines+markers",
            line=dict(color=color, width=2.5), marker=dict(size=8, line=dict(color="white", width=2)),
            customdata=s["count"],
            hovertemplate=f"<b>{school}</b><br>Fall %{{x}}: %{{customdata:,}} students"
                          + ("<br>Index: %{y:.1f}" if indexed else "") + "<extra></extra>",
        ))
        fig.add_annotation(x=s["year"].iloc[-1], y=y.iloc[-1], text=f"{y.iloc[-1]:.0f}" if indexed
                           else f"{s['count'].iloc[-1]:,}", xanchor="left", xshift=8, showarrow=False,
                           font=dict(size=12))
    fig.add_vrect(x0=2024.5, x1=2025.5, fillcolor=DROP, opacity=.08, line_width=0,
                  annotation_text="Fall 2025", annotation_position="top left")
    if indexed:
        fig.add_hline(y=100, line=dict(color=NEUTRAL, width=1, dash="dash"))
    fig = base_layout(fig, height=420, hovermode="x unified",
                      legend=dict(orientation="h", y=1.08, x=0))
    fig.update_xaxes(dtick=1)
    fig.update_yaxes(title="Index (first visible year = 100)" if indexed else "International students",
                     rangemode="normal" if indexed else "tozero")
    return fig


def level_area(df, inst, country="All countries"):
    fig = go.Figure()
    for level, color in (("Graduate", GRAD_COLOR), ("Undergraduate", UG_COLOR)):
        s = df[(df.institution == inst) & (df.country == country)
               & (df.academic_level == level)].sort_values("year")
        fig.add_trace(go.Scatter(
            x=s["year"], y=s["count"], name=level, mode="lines+markers", stackgroup="one",
            line=dict(color=color, width=2), marker=dict(size=7),
            hovertemplate=f"<b>{level}</b> · Fall %{{x}}: %{{y:,}}<extra></extra>",
        ))
    fig.add_vrect(x0=2024.5, x1=2025.5, fillcolor=DROP, opacity=.08, line_width=0)
    fig = base_layout(fig, height=340, hovermode="x unified", legend=dict(orientation="h", y=1.1, x=0))
    fig.update_xaxes(dtick=1)
    return fig


# ── Page ─────────────────────────────────────────────────────────────────────

df = load()
overall = changes(df)
india = changes(df, country="India")
ug, grad = changes(df, level="Undergraduate"), changes(df, level="Graduate")
levels = ug.merge(grad, on=["institution", "label"], suffixes=("_ug", "_grad"))
india_vs_all = india.merge(overall, on=["institution", "label"], suffixes=("_india", "_all"))
n_down = int((overall.pct < -1).sum())
n_flat = int((overall.pct.abs() <= 1).sum())
lost_grad = -levels.loc[levels.diff_grad < 0, "diff_grad"].sum()
lost_ug = -levels.loc[levels.diff_ug < 0, "diff_ug"].sum()


def chapter(num, title, lede, anchor):
    st.markdown(f'<p class="kicker">Part {num}</p>', unsafe_allow_html=True)
    st.header(title, anchor=anchor, divider="gray")
    st.markdown(f'<p class="lede">{lede}</p>', unsafe_allow_html=True)


st.markdown("""
<style>
  .block-container {padding-top: 3.5rem; max-width: 1150px;}
  div[data-testid="stMetric"] {border: 1px solid rgba(128,128,128,.25); border-radius: 12px; padding: 14px 18px;}
  div[data-testid="stMetricValue"] {font-size: 1.7rem;}
  .kicker {letter-spacing: .08em; text-transform: uppercase; font-size: .78rem; opacity: .65; margin: 1.6rem 0 -.6rem;}
  .lede {font-size: 1.08rem; line-height: 1.6; max-width: 62rem; opacity: .9;}
  .takeaway {border-left: 4px solid #2a78d6; padding: .5rem 1rem; margin: .5rem 0 1rem; background: rgba(42,120,214,.07);
             border-radius: 0 8px 8px 0;}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### The story")
    st.markdown("""
1. [The question](#question)
2. [Fall 2025 at a glance](#glance)
3. [Campuses moved differently](#campuses)
4. [Graduate seats took the hit](#levels)
5. [Indian students fell faster](#india)
6. [Is 2025 unusual?](#history)
7. [What comes next](#next)
""")
    st.divider()
    st.caption("**What these numbers are:** fall headcounts of *all* enrolled international students, "
               "new and continuing, from each university's own published tables.")
    st.caption("**What they are not:** new arrivals, visa decisions, or proof of why enrollment changed.")

# ── Opening ──
st.markdown('<p class="kicker">International student mobility · Fall 2025</p>', unsafe_allow_html=True)
st.title("Fewer international students in Fall 2025, and Indian students fell faster")
st.markdown(
    f'<p class="lede">At {n_down} of the {len(overall)} U.S. universities tracked here, international '
    "enrollment declined between Fall 2024 and Fall 2025. At every campus that reports students from "
    "India separately, that group shrank faster than international students overall.</p>",
    unsafe_allow_html=True)

chapter(1, "The question", "", "question")
q1, q2 = st.columns([1.4, 1], gap="large")
with q1:
    st.markdown("""
Rules on **student visas, travel and entry, duration of stay, visa screening, and post-study work
(CPT, OPT, STEM OPT, H-1B)** shape whether the United States looks like a good place to study.

Our project asks two linked questions:

- **Discourse:** how do the concerns students raise online (visa uncertainty, job prospects,
  delaying study, other destinations) change around these rule changes, especially among
  **Indian students**?
- **Mobility:** do those shifts move together with what actually happens to international enrollment?

**This page is the mobility side.** It sets the baseline the discourse analysis will be compared against.
""")
with q2:
    st.markdown("""
<div class="takeaway">
<b>How to read this page</b><br>
Each university is compared with its own past. Campus sizes and counting rules differ,
so these campuses are a set of case studies, not a national estimate.
</div>
""", unsafe_allow_html=True)
    st.caption(f"Campuses: {', '.join(overall.label.sort_values())}.")

# ── 2. Glance ──
chapter(2, "Fall 2025 at a glance",
        "Four numbers summarize what the university tables show.", "glance")
worst = overall.sort_values("pct").iloc[0]
k = st.columns(4)
k[0].metric("Campuses with fewer international students", f"{n_down} of {len(overall)}",
            f"{n_flat} roughly flat (within ±1%)", delta_color="off", delta_arrow="off")
k[1].metric("Steepest campus decline", f"{worst.pct:+.1f}%", f"{worst.label}: {worst.c24:,} → {worst.c25:,}",
            delta_color="off", delta_arrow="off")
k[2].metric("Indian students, where reported", f"down at {int((india.pct < 0).sum())} of {len(india)}",
            f"{india.pct.min():+.1f}% to {india.pct.max():+.1f}%", delta_color="off", delta_arrow="off")
k[3].metric("Graduate share of lost seats", f"{lost_grad / (lost_grad + lost_ug):.0%}",
            f"{lost_grad:,} graduate vs {lost_ug:,} undergraduate", delta_color="off", delta_arrow="off",
            help="Across campuses that publish an undergraduate/graduate split; only declines are counted.")

# ── 3. Campuses ──
chapter(3, "Not every campus moved the same way",
        f"The decline was uneven. {', '.join(overall[overall.pct < -1].sort_values('pct').label)} lost "
        f"international students, while {', '.join(overall[overall.pct.abs() <= 1].label)} held roughly steady.",
        "campuses")
st.plotly_chart(diverging(overall), width="stretch")
c1, c2 = st.columns(2, gap="large")
with c1:
    st.markdown(
        f'<div class="takeaway"><b>What one campus said.</b> Illinois Springfield attributed its drop to visa '
        "processing delays, added documentation requirements, and limited consular appointments that kept "
        f'students from arriving in time. <a href="{SOURCES["uis_2025"]}">UIS announcement</a></div>',
        unsafe_allow_html=True)
with c2:
    st.markdown(
        '<div class="takeaway"><b>New students only.</b> UM-Dearborn reported a 44% fall in <i>new</i> '
        "international enrollment, with 144 expected students unable to enroll. That is a different measure "
        f'from the headcounts above, so it is not charted. <a href="{SOURCES["dearborn"]}">UM-Dearborn report</a></div>',
        unsafe_allow_html=True)

st.subheader("Inside each campus's change")
st.markdown("Pick a campus to see its Fall 2024 → Fall 2025 change broken into the groups it publishes: "
            "students from India vs other countries, undergraduate vs graduate, or both.")
by_drop = overall.sort_values("pct").institution.tolist()
e1, e2 = st.columns([1, 1.6])
inst = e1.selectbox("Campus", by_drop, format_func=SHORT.get, key="explorer_campus")
splits = available_splits(df, inst)
split = e2.radio("Break the change down by", splits, format_func=SPLITS.get, horizontal=True,
                 key=f"explorer_split_{inst}")
st.plotly_chart(waterfall(df, inst, decompose(df, inst, split)), width="stretch")
if splits == ["total"]:
    st.caption(f"{SHORT[inst]} publishes only a campus-wide international total.")

# ── 4. Levels ──
chapter(4, "Graduate seats took most of the hit",
        "Where universities split their counts by level, most of the students lost were graduate students, "
        "the group the project's OPT and post-study employment themes speak to most directly.", "levels")
unit = st.segmented_control("Show change as", ["Percent", "Students"], default="Percent",
                            key="level_unit") or "Percent"
col_ug, col_grad = ("pct_ug", "pct_grad") if unit == "Percent" else ("diff_ug", "diff_grad")
st.plotly_chart(paired_bars(levels.sort_values("diff_grad"),
                            [("Graduate", col_grad, GRAD_COLOR), ("Undergraduate", col_ug, UG_COLOR)],
                            "pct" if unit == "Percent" else "count"), width="stretch")
st.caption("New Mexico's undergraduate international count rose while its graduate count fell; "
           "Ohio's undergraduates fell faster in percent terms but lost fewer students.")

# ── 5. India ──
chapter(5, "Indian students fell faster than the overall total",
        "Indian students are the project's main subgroup. Three campuses publish India-specific counts, "
        "and at all three the India series dropped more steeply than total international enrollment, "
        "even at Berkeley, where the total barely moved.", "india")
st.plotly_chart(paired_bars(india_vs_all.sort_values("pct_india"),
                            [("Students from India", "pct_india", INDIA_COLOR),
                             ("All international students", "pct_all", ALL_COLOR)], "pct"), width="stretch")

india_campuses = india_vs_all.sort_values("pct_india").institution.tolist()

st.subheader("India's share of international students")
st.markdown("Outer ring: Fall 2025. Inner ring: Fall 2024. India's share of the international student body "
            "shrank at every campus that reports it.")
for col, inst in zip(st.columns(len(india_campuses)), india_campuses):
    col.plotly_chart(india_share_donut(df, inst), width="stretch")

st.subheader("How much of each campus's change came from India")
offset = india_vs_all[(india_vs_all.diff_india < india_vs_all.diff_all)]
if not offset.empty:
    st.markdown(f"At **{' and '.join(offset.label)}**, the drop in students from India was larger than the "
                "campus's entire net change: enrollment from other countries rose and partly offset it.")
for col, inst in zip(st.columns(len(india_campuses)), india_campuses):
    col.plotly_chart(waterfall(df, inst, decompose(df, inst, "india"), height=360, title=SHORT[inst]),
                     width="stretch")

st.subheader("Students from India over time")
st.plotly_chart(trends(df, True, 2021, country="India"), width="stretch")
st.caption("Indexed to Fall 2021 = 100 so campuses of different sizes share one scale; hover for student counts. "
           "Berkeley's 2024 value comes from its 2024 report; its 2025 report repeats an older baseline.")

# ── 6. History ──
chapter(6, "Is 2025 unusual? The long view",
        "One year can be noise. Indexing each campus to its own starting year shows whether Fall 2025 "
        "breaks a recovery or continues a trend. The campuses that declined in 2025 had peaked between "
        "2022 and 2024, so Fall 2025 extends a turn that was already under way at some of them.", "history")
c1, c2 = st.columns([1, 2])
indexed = c1.toggle("Index each campus to its start year", value=True)
start_year = c2.select_slider("Start year", options=list(range(2011, 2025)), value=2019)
st.plotly_chart(trends(df, indexed, start_year), width="stretch")
st.caption("Series begin in different years: UH Hilo 2011, MIT 2016, Ohio and U-M Ann Arbor 2019, "
           "New Mexico and UC Berkeley 2021, Illinois Springfield 2022. "
           "In indexed mode, each line uses its own first visible year.")

level_campuses = [i for i in SHORT if
                  df[(df.institution == i) & (df.academic_level == "Undergraduate")].year.nunique() >= 3]
with st.expander("Undergraduate and graduate over time, by campus"):
    l1, l2 = st.columns([1, 1.6])
    inst = l1.selectbox("Campus", level_campuses, format_func=SHORT.get, key="level_campus")
    scopes = ["All countries"] + (["India"] if has_series(df, inst, "India", "Undergraduate") else [])
    country = l2.radio("Country scope", scopes, horizontal=True, key=f"level_scope_{inst}")
    st.plotly_chart(level_area(df, inst, country), width="stretch")

# ── 7. Next ──
chapter(7, "What comes next",
        "This page establishes <i>when</i> and <i>where</i> enrollment moved. The next steps test whether "
        "student discourse moved with it.", "next")
n1, n2, n3 = st.columns(3, gap="medium")
n1.markdown("**1 · Line up the timeline**  \nPlace each visa, travel, stay, and work-rule event on the same "
            "calendar as these enrollment changes.")
n2.markdown("**2 · Compare with discourse**  \nTrack how concerns in Reddit and other student forums "
            "(visa uncertainty, OPT and jobs, delaying study, other destinations) rise and fall around "
            "those events, allowing for a lag before enrollment responds.")
n3.markdown("**3 · Estimate exposure**  \nProject enrollment under different scenarios and estimate "
            "the tuition revenue and staffing that universities with high international shares could lose.")
st.info("Enrollment changes can line up with rule changes in time, but they also reflect student choice, "
        "costs, and campus conditions. These numbers describe what happened; they do not on their own "
        "show why.")

with st.expander("Data & sources"):
    table = overall.rename(columns=dict(label="Campus", c24="Fall 2024", c25="Fall 2025",
                                        diff="Change", pct="% change")).drop(columns="institution")
    st.dataframe(table, hide_index=True, width="stretch")
    st.dataframe(df.drop(columns=["period", "measure", "source_definition"]),
                 hide_index=True, width="stretch")
    st.markdown("\n".join(f"- [{k}]({u})" for k, u in SOURCES.items()))
