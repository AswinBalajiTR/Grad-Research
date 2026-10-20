"""Streamlit story page for the mobility layer of the international-student project.

The project asks how online discussion of visa, travel, duration-of-stay, and
post-study work rules shifts over time, and whether it moves together with
international student mobility. This page covers the mobility side through
published Fall enrollment counts at selected universities and years.

Reuses the source-linked counts in historical_international_eda.py, so the
numbers here always match the CSV, summary, and findings.md outputs.

Run: streamlit run demo/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "code/university"))
from historical_international_eda import SOURCES, make_rows, validate  # noqa: E402

# Categorical slots in fixed order; DROP/GAIN are the diverging poles.
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
DROP, GAIN, NEUTRAL = "#e34948", "#2a78d6", "#9a9893"
SCHOOL_COLORS = {"Ohio University": BLUE, "MIT": ORANGE, "University of Hawaiʻi at Hilo": AQUA,
                 "University of Michigan–Ann Arbor": "#7955b3",
                 "University of Illinois Springfield": YELLOW,
                 "University of New Mexico": "#e87ba4", "UC Berkeley": "#008300"}
FONT = dict(family="Inter, system-ui, sans-serif", size=13)



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


def changes(df, start_year, end_year, country="All countries", level="All levels") -> pd.DataFrame:
    """Change for institutions that publish the chosen series in both years."""
    columns = ["institution", "c_start", "c_end", "label", "diff", "pct"]
    if start_year == end_year:
        return pd.DataFrame(columns=columns)
    p = (df[(df.country == country) & (df.academic_level == level) & df.year.isin([start_year, end_year])]
         .pivot_table(index="institution", columns="year", values="count").dropna())
    if p.empty or not {start_year, end_year}.issubset(p.columns):
        return pd.DataFrame(columns=columns)
    out = pd.DataFrame({"institution": p.index, "c_start": p[start_year].astype(int).values,
                        "c_end": p[end_year].astype(int).values})
    out["label"] = out.institution.map(SHORT)
    out["diff"] = out.c_end - out.c_start
    out["pct"] = (100 * (out.c_end / out.c_start - 1)).round(1)
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


def has_series(df, inst, country="All countries", level="All levels",
               start_year=2024, end_year=2025) -> bool:
    """True when the campus publishes this series for both selected Fall years."""
    hit = df[(df.institution == inst) & (df.country == country) & (df.academic_level == level)
             & df.year.isin([start_year, end_year])]
    return len(hit) == 2


SPLITS = {"india": "India vs other countries", "india_level": "India vs other, by level",
          "level": "Undergraduate vs graduate", "total": "Net change only"}


def available_splits(df, inst, start_year=2024, end_year=2025) -> list[str]:
    found = [key for key, ok in (
        ("india", has_series(df, inst, "India", start_year=start_year, end_year=end_year)),
        ("india_level", has_series(df, inst, "India", "Undergraduate", start_year, end_year)
         and has_series(df, inst, "India", "Graduate", start_year, end_year)
         and has_series(df, inst, level="Graduate", start_year=start_year, end_year=end_year)),
        ("level", has_series(df, inst, level="Undergraduate", start_year=start_year, end_year=end_year)
         and has_series(df, inst, level="Graduate", start_year=start_year, end_year=end_year)),
    ) if ok]
    return found or ["total"]


def decompose(df, inst, by, start_year=2024, end_year=2025) -> dict[str, int]:
    """Split a campus's change between two Fall years into its published parts."""
    def d(country="All countries", level="All levels"):
        return value(df, inst, end_year, country, level) - value(df, inst, start_year, country, level)
    if by == "india":
        return {"India": d("India"), "Other countries": d() - d("India")}
    if by == "india_level":
        return {"India · UG": d("India", "Undergraduate"), "India · Grad": d("India", "Graduate"),
                "Other · UG": d(level="Undergraduate") - d("India", "Undergraduate"),
                "Other · Grad": d(level="Graduate") - d("India", "Graduate")}
    if by == "level":
        return {"Undergraduate": d(level="Undergraduate"), "Graduate": d(level="Graduate")}
    return {"Net change": d()}


def waterfall(df, inst, parts, height=400, title=None, start_year=2024, end_year=2025):
    start, end = value(df, inst, start_year), value(df, inst, end_year)
    running = [start]
    for v in parts.values():
        running.append(running[-1] + v)
    lo, hi = min(running), max(running)
    pad = max((hi - lo) * .45, hi * .02, 5)
    fig = go.Figure(go.Waterfall(
        x=([str(start_year), *[k.replace("Other countries", "Other") for k in parts], str(end_year)] if title
           else [f"Fall {start_year}", *parts, f"Fall {end_year}"]), y=[start, *parts.values(), end],
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


def change_bars(parts):
    """Show each group's contribution to a campus change from a shared zero line."""
    labels = list(parts)
    amounts = list(parts.values())
    span = max(abs(amount) for amount in amounts)
    pad = max(span * .22, 1)
    fig = go.Figure(go.Bar(
        x=amounts, y=labels, orientation="h",
        marker=dict(color=[GAIN if amount >= 0 else DROP for amount in amounts], cornerradius=4),
        text=[f"{amount:+,}" for amount in amounts], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Change: %{x:+,} students<extra></extra>",
    ))
    fig.add_vline(x=0, line=dict(color=NEUTRAL, width=1))
    fig = base_layout(fig, height=130 + 65 * len(parts), showlegend=False,
                      margin=dict(l=10, r=35, t=15, b=10))
    fig.update_xaxes(title="Change in international students",
                     range=[min(0, *amounts) - pad, max(0, *amounts) + pad],
                     showgrid=True, gridcolor="rgba(128,128,128,.18)")
    fig.update_yaxes(showgrid=False, autorange="reversed")
    return fig


def india_share_donut(df, inst, start_year, end_year):
    """Outer ring: later mix. Inner ring: earlier mix. Center: India's share."""
    fig = go.Figure()
    shares = {}
    for year, domain, hole, india_color in ((end_year, [0, 1], .74, INDIA_COLOR),
                                           (start_year, [.13, .87], .8, "#8fd6bc")):
        ind, tot = value(df, inst, year, "India"), value(df, inst, year)
        shares[year] = ind / tot
        fig.add_trace(go.Pie(
            labels=["Students from India", "Other countries"], values=[ind, tot - ind], hole=hole, sort=False,
            direction="clockwise", domain=dict(x=domain, y=domain), textinfo="none", name=str(year),
            marker=dict(colors=[india_color, "rgba(154,152,147,.28)"], line=dict(color="white", width=2)),
            hovertemplate=f"<b>%{{label}}</b> · Fall {year}<br>%{{value:,}} students (%{{percent}})<extra></extra>",
        ))
    fig.add_annotation(
        text=f"<b>{shares[end_year]:.1%}</b><br><span style='font-size:11px'>from India, {end_year}<br>"
             f"was {shares[start_year]:.1%} in {start_year}</span>", showarrow=False, font=dict(size=20))
    return base_layout(fig, height=300, showlegend=False, margin=dict(l=10, r=10, t=36, b=10),
                       title=dict(text=SHORT[inst], x=.5, xanchor="center", font=dict(size=15)))


def diverging(summary, start_year, end_year):
    s = summary.sort_values("pct", ascending=False)
    fig = go.Figure(go.Bar(
        x=s["pct"], y=s["label"], orientation="h",
        marker=dict(color=[DROP if v < 0 else GAIN for v in s["pct"]], cornerradius=4),
        text=[f"{v:+.1f}%" for v in s["pct"]], textposition="outside", cliponaxis=False,
        customdata=s[["c_start", "c_end"]],
        hovertemplate=f"<b>%{{y}}</b><br>Fall {start_year}: %{{customdata[0]:,}}"
                      f"<br>Fall {end_year}: %{{customdata[1]:,}}"
                      "<br>Change: %{x:+.1f}%<extra></extra>",
    ))
    fig.add_vline(x=0, line=dict(color=NEUTRAL, width=1))
    fig = base_layout(fig, height=90 + 50 * len(s), bargap=.35)
    fig.update_xaxes(ticksuffix="%", range=[s["pct"].min() * 1.35, max(s["pct"].max(), 0) + 8],
                     gridcolor="rgba(128,128,128,.18)", showgrid=True)
    fig.update_yaxes(showgrid=False)
    return fig


def fall_headcounts(df, year):
    return df[(df.year == year) & (df.country == "All countries")
              & (df.academic_level == "All levels")]


def snapshot_bars(df, year):
    rows = fall_headcounts(df, year).sort_values("count")
    fig = go.Figure(go.Bar(
        x=rows["count"], y=rows["institution"].map(SHORT), orientation="h",
        marker=dict(color=rows["institution"].map(SCHOOL_COLORS).tolist(), cornerradius=4),
        text=[f"{count:,}" for count in rows["count"]], textposition="outside",
        cliponaxis=False, hovertemplate="<b>%{y}</b><br>%{x:,} students<extra></extra>",
    ))
    fig = base_layout(fig, height=90 + 48 * len(rows))
    fig.update_xaxes(title="International students", range=[0, rows["count"].max() * 1.2])
    fig.update_yaxes(showgrid=False)
    return fig


def level_snapshot_bars(df, year):
    """Published undergraduate and graduate headcounts in one Fall year."""
    rows = df[(df.year == year) & (df.country == "All countries")
              & df.academic_level.isin(["Undergraduate", "Graduate"])]
    counts = rows.pivot_table(index="institution", columns="academic_level", values="count").dropna()
    if counts.empty:
        return None
    counts = counts.sort_values("Graduate")
    fig = go.Figure()
    for level, color in (("Graduate", GRAD_COLOR), ("Undergraduate", UG_COLOR)):
        fig.add_trace(go.Bar(
            x=counts[level], y=[SHORT[school] for school in counts.index], name=level,
            orientation="h", marker=dict(color=color, cornerradius=4),
            hovertemplate=f"<b>%{{y}}</b><br>{level}: %{{x:,}}<extra></extra>",
        ))
    fig = base_layout(fig, height=110 + 62 * len(counts), barmode="group",
                      legend=dict(orientation="h", y=1.12, x=0))
    fig.update_xaxes(title="International students", range=[0, counts.max().max() * 1.2])
    fig.update_yaxes(showgrid=False)
    return fig


def india_snapshot_bars(df, year):
    """India's share of each reporting campus's international headcount."""
    total = fall_headcounts(df, year).set_index("institution")["count"]
    india = df[(df.year == year) & (df.country == "India")
               & (df.academic_level == "All levels")].set_index("institution")["count"]
    schools = [school for school in total.index if school in india.index]
    if not schools:
        return None
    schools.sort(key=lambda school: india[school] / total[school])
    shares = [100 * india[school] / total[school] for school in schools]
    fig = go.Figure(go.Bar(
        x=shares, y=[SHORT[school] for school in schools], orientation="h",
        marker=dict(color=INDIA_COLOR, cornerradius=4),
        text=[f"{share:.1f}%" for share in shares], textposition="outside", cliponaxis=False,
        customdata=[[int(india[school]), int(total[school])] for school in schools],
        hovertemplate="<b>%{y}</b><br>From India: %{customdata[0]:,}"
                      "<br>All international: %{customdata[1]:,}<br>Share: %{x:.1f}%<extra></extra>",
    ))
    fig = base_layout(fig, height=110 + 52 * len(schools))
    fig.update_xaxes(title="Share from India", ticksuffix="%", range=[0, max(shares) * 1.25])
    fig.update_yaxes(showgrid=False)
    return fig


def campus_comparison_bars(df, years):
    """Compare the selected Fall years for every selected campus with any data."""
    counts = {year: fall_headcounts(df, year).set_index("institution")["count"] for year in years}
    schools = sorted(set().union(*(set(series.index) for series in counts.values())),
                     key=lambda school: counts[years[-1]].get(school, 0))
    labels = [SHORT[school] for school in schools]
    fig = go.Figure()
    colors = {1: [BLUE], 2: [NEUTRAL, BLUE], 3: [NEUTRAL, AQUA, BLUE],
              4: [NEUTRAL, AQUA, ORANGE, BLUE]}[len(years)]
    for year, color in zip(years, colors):
        fig.add_trace(go.Bar(
            x=[counts[year].get(school) for school in schools], y=labels, name=f"Fall {year}",
            orientation="h", marker=dict(color=color, cornerradius=4),
            hovertemplate="<b>%{y}</b><br>Fall " + str(year) + ": %{x:,}<extra></extra>",
        ))
    fig = base_layout(fig, height=110 + 58 * len(schools), barmode="group",
                      legend=dict(orientation="h", y=1.12, x=0))
    fig.update_xaxes(title="International students", range=[0, max(series.max() for series in counts.values()) * 1.2])
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
    latest_year = int(df.year.max())
    fig.add_vrect(x0=latest_year - .5, x1=latest_year + .5, fillcolor=DROP, opacity=.08, line_width=0,
                  annotation_text=f"Fall {latest_year}", annotation_position="top left")
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
    latest_year = int(df.year.max())
    fig.add_vrect(x0=latest_year - .5, x1=latest_year + .5, fillcolor=DROP, opacity=.08, line_width=0)
    fig = base_layout(fig, height=340, hovermode="x unified", legend=dict(orientation="h", y=1.1, x=0))
    fig.update_xaxes(dtick=1)
    return fig


# ── Page ─────────────────────────────────────────────────────────────────────

def chapter(num, title, lede, anchor):
    st.markdown(f'<p class="kicker">Part {num}</p>', unsafe_allow_html=True)
    st.header(title, anchor=anchor, divider="gray")
    if lede:
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
    with st.expander("About these data"):
        st.markdown("- **Measure:** fall international headcount\n"
                    "- **Includes:** new and continuing students\n"
                    "- **Source:** university tables\n"
                    "- **Limits:** not new arrivals or causal proof")

# ── Opening ──
st.markdown('<p class="kicker">International student mobility</p>', unsafe_allow_html=True)
st.title("International enrollment")
school_col, year_col = st.columns([1.5, 1])
selected_schools = school_col.multiselect(
    "Universities to compare", list(SCHOOL_COLORS), default=list(SCHOOL_COLORS),
    format_func=SHORT.get, key="enrollment_universities")
all_years = sorted(int(year) for year in load().year.unique())
selected_years = year_col.multiselect(
    "Fall years to compare (up to four)", all_years, default=[2024, 2025],
    max_selections=4, format_func=lambda year: f"Fall {year}", key="enrollment_years")
if not selected_schools or not selected_years:
    st.info("Select at least one university and one Fall year to see the charts.")
    st.stop()

selected_years = sorted(selected_years)
start_year, end_year = selected_years[0], selected_years[-1]
df = load().loc[lambda rows: rows.institution.isin(selected_schools) & rows.year.isin(selected_years)]
if df.empty:
    st.info("The selected universities do not report data for those Fall years.")
    st.stop()
overall = changes(df, start_year, end_year)
india = changes(df, start_year, end_year, country="India")
ug, grad = (changes(df, start_year, end_year, level="Undergraduate"),
            changes(df, start_year, end_year, level="Graduate"))
levels = ug.merge(grad, on=["institution", "label"], suffixes=("_ug", "_grad"))
india_vs_all = india.merge(overall, on=["institution", "label"], suffixes=("_india", "_all"))
n_down = int((overall.pct < -1).sum())
n_flat = int((overall.pct.abs() <= 1).sum())
lost_grad = -levels.loc[levels.diff_grad < 0, "diff_grad"].sum()
lost_ug = -levels.loc[levels.diff_ug < 0, "diff_ug"].sum()
if start_year < end_year:
    st.caption(f"Fall {start_year} → {end_year} · {n_down}/{len(overall)} comparable campuses declined")
else:
    st.caption(f"Fall {end_year} · {len(selected_schools)} selected campuses")

section_tabs = st.tabs([
    "The question", "Fall snapshot", "Campuses", "By level",
    "India", "Year trends",
])

with section_tabs[0]:
    chapter(1, "The question", "", "question")
    q1, q2 = st.columns([1.4, 1], gap="large")
    with q1:
        st.markdown("- **Policy changes**\n- **Student concerns**\n- **Enrollment shifts**")
        st.caption("Do online concerns and enrollment move together around visa, travel, and work rules?")
    with q2:
        st.markdown("- **Compare within campuses**\n- **Case studies only**\n- **No national estimate**")
        with st.expander("Tracked campuses"):
            st.caption(", ".join(SHORT[school] for school in selected_schools))
    with st.expander("Data & sources"):
        if not overall.empty:
            table = overall.rename(columns=dict(label="Campus", c_start=f"Fall {start_year}", c_end=f"Fall {end_year}",
                                                diff="Change", pct="% change")).drop(columns="institution")
            st.dataframe(table, hide_index=True, use_container_width=True)
        st.dataframe(df.drop(columns=["period", "measure", "source_definition"]),
                     hide_index=True, use_container_width=True)
        st.markdown("\n".join(f"- [{k}]({u})" for k, u in SOURCES.items()))

with section_tabs[1]:
    # ── 2. Glance ──
    snapshot_year = st.selectbox("Fall year", sorted(df.year.unique(), reverse=True),
                                 format_func=lambda year: f"Fall {year}", key="snapshot_year")
    chapter(2, f"Fall {snapshot_year} snapshot", "", "glance")
    st.plotly_chart(snapshot_bars(df, snapshot_year), use_container_width=True)
    st.caption("Published campuses only · not a national total")
    if not overall.empty:
        st.subheader(f"{start_year} → {end_year}")
        worst = overall.sort_values("pct").iloc[0]
        k = st.columns(4)
        k[0].metric("Campus declines", f"{n_down} of {len(overall)}",
                    f"{n_flat} roughly flat (within ±1%)", delta_color="off", delta_arrow="off")
        k[1].metric("Largest decline", f"{worst.pct:+.1f}%", f"{worst.label}: {worst.c_start:,} → {worst.c_end:,}",
                    delta_color="off", delta_arrow="off")
        k[2].metric("India declines", f"{int((india.pct < 0).sum())} of {len(india)}" if len(india) else "No data",
                    f"{india.pct.min():+.1f}% to {india.pct.max():+.1f}%" if len(india) else "", delta_color="off", delta_arrow="off")
        k[3].metric("Graduate share", f"{lost_grad / (lost_grad + lost_ug):.0%}" if lost_grad + lost_ug else ("No data" if levels.empty else "No decline"),
                    f"{lost_grad:,} graduate vs {lost_ug:,} undergraduate", delta_color="off", delta_arrow="off",
                    help="Across campuses that publish an undergraduate/graduate split; only declines are counted.")
    else:
        st.info("Choose two years reported by the same university to see change metrics.")

with section_tabs[2]:
    # ── 3. Campuses ──
    chapter(3, "Campus changes", "", "campuses")
    st.plotly_chart(campus_comparison_bars(df, selected_years), use_container_width=True)
    missing_year = set(selected_schools) - set(fall_headcounts(df, end_year).institution)
    if missing_year:
        st.caption("No Fall " + str(end_year) + " total: " + ", ".join(SHORT[school] for school in selected_schools if school in missing_year))
    st.caption("Only selected Fall years are shown · gaps mean unpublished data")

    st.subheader("Inside selected campuses")
    by_drop = [school for school in selected_schools if school not in missing_year]
    detail_schools = st.multiselect("Break down up to two universities", by_drop,
                                    default=by_drop[:min(2, len(by_drop))], max_selections=2,
                                    format_func=SHORT.get, key=f"explorer_campuses_{start_year}_{end_year}_{'|'.join(by_drop)}")
    for col, inst in zip(st.columns(len(detail_schools)), detail_schools) if detail_schools else []:
        with col:
            st.markdown(f"**{SHORT[inst]}**")
            previous_year = start_year if start_year < end_year and has_series(df, inst, start_year=start_year,
                                                                                end_year=end_year) else None
            selected_count = value(df, inst, end_year)
            st.metric(f"Fall {end_year} students", f"{selected_count:,}")
            if previous_year is not None:
                previous_count = value(df, inst, previous_year)
                difference = selected_count - previous_count
                st.metric(f"{previous_year} → {end_year} change", f"{difference:+,}",
                          f"{100 * difference / previous_count:+.1f}%", delta_color="off")
                splits = available_splits(df, inst, previous_year, end_year)
                split = st.selectbox("Break down by", splits, format_func=SPLITS.get,
                                     key=f"explorer_split_{inst}_{previous_year}_{end_year}")
                parts = decompose(df, inst, split, previous_year, end_year)
                st.plotly_chart(change_bars(parts), use_container_width=True)
                st.caption(f"Fall {previous_year} → {end_year} · right = gain, left = loss")
            else:
                st.info("Choose two years reported by this campus for a breakdown.")

    with st.expander("Compare selected campuses and read related reports"):
        if not overall.empty:
            st.plotly_chart(diverging(overall, start_year, end_year), use_container_width=True)
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

with section_tabs[3]:
    # ── 4. Levels ──
    chapter(4, "By study level", "", "levels")
    if levels.empty:
        fig = level_snapshot_bars(df, end_year)
        if fig is None:
            st.info("No undergraduate and graduate counts for the selected year and universities.")
        else:
            st.caption(f"Fall {end_year} · reported headcounts")
            st.plotly_chart(fig, use_container_width=True)
    else:
        unit = st.segmented_control("Show change as", ["Percent", "Students"], default="Percent",
                                    key="level_unit") or "Percent"
        col_ug, col_grad = ("pct_ug", "pct_grad") if unit == "Percent" else ("diff_ug", "diff_grad")
        st.plotly_chart(paired_bars(levels.sort_values("diff_grad"),
                                    [("Graduate", col_grad, GRAD_COLOR), ("Undergraduate", col_ug, UG_COLOR)],
                                    "pct" if unit == "Percent" else "count"), use_container_width=True)
        st.caption(f"Fall {start_year} → {end_year} · campuses with both level counts")

with section_tabs[4]:
    # ── 5. India ──
    chapter(5, "Students from India", "", "india")

    if india_vs_all.empty:
        fig = india_snapshot_bars(df, end_year)
        if fig is None:
            st.info("No India counts for the selected year and universities.")
        else:
            st.caption(f"Fall {end_year} · share of international students from India")
            st.plotly_chart(fig, use_container_width=True)
    else:
        india_campuses = india_vs_all.sort_values("pct_india").institution.tolist()
        change_tab, share_tab, contribution_tab, history_tab = st.tabs(
            ["Change", "India share", "Contribution", "History"])
        with change_tab:
            st.plotly_chart(paired_bars(india_vs_all.sort_values("pct_india"),
                                        [("Students from India", "pct_india", INDIA_COLOR),
                                         ("All international students", "pct_all", ALL_COLOR)], "pct"),
                            use_container_width=True)
            st.caption(f"Fall {start_year} → {end_year} · reporting campuses only")
        with share_tab:
            st.caption(f"Outer ring = {end_year} · inner ring = {start_year}")
            for col, inst in zip(st.columns(len(india_campuses)), india_campuses):
                col.plotly_chart(india_share_donut(df, inst, start_year, end_year), use_container_width=True)
        with contribution_tab:
            for col, inst in zip(st.columns(len(india_campuses)), india_campuses):
                col.plotly_chart(waterfall(df, inst, decompose(df, inst, "india", start_year, end_year),
                                         height=360, title=SHORT[inst], start_year=start_year, end_year=end_year),
                                 use_container_width=True)
        with history_tab:
            st.plotly_chart(trends(df, True, start_year, country="India"), use_container_width=True)
            st.caption(f"Index: first selected Fall year = 100 · hover for counts")
            if "UC Berkeley" in india_campuses:
                with st.expander("Berkeley source note"):
                    st.caption("Berkeley's 2024 value uses its 2024 report; its 2025 report repeats an older baseline.")

with section_tabs[5]:
    # ── 6. History ──
    chapter(6, "Year trends", "", "history")
    indexed = st.toggle("Index each campus to its first selected year", value=True)
    st.plotly_chart(trends(df, indexed, start_year), use_container_width=True)
    st.caption("Only selected Fall years are shown · index = 100 at each campus's first selected year")

    level_campuses = [i for i in SHORT if
                      df[(df.institution == i) & (df.academic_level == "Undergraduate")].year.nunique() >= 2]
    if level_campuses:
        with st.expander("Undergraduate and graduate over time, by campus"):
            area_schools = st.multiselect("Compare up to two campuses", level_campuses,
                                          default=level_campuses[:min(2, len(level_campuses))],
                                          max_selections=2, format_func=SHORT.get,
                                          key=f"level_campuses_{'|'.join(level_campuses)}")
            for col, inst in zip(st.columns(len(area_schools)), area_schools) if area_schools else []:
                with col:
                    st.markdown(f"**{SHORT[inst]}**")
                    scopes = ["All countries"] + (["India"] if has_series(df, inst, "India", "Undergraduate",
                                                                           start_year, end_year) else [])
                    country = st.radio("Country scope", scopes, horizontal=True, key=f"level_scope_{inst}")
                    st.plotly_chart(level_area(df, inst, country), use_container_width=True)
