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


def level_snapshot_bars(df, year, level):
    """Published headcounts for one study level in one Fall year."""
    rows = df[(df.year == year) & (df.country == "All countries")
              & (df.academic_level == level)].sort_values("count")
    if rows.empty:
        return None
    fig = go.Figure(go.Bar(
        x=rows["count"], y=rows["institution"].map(SHORT), orientation="h",
        marker=dict(color=rows["institution"].map(SCHOOL_COLORS).tolist(), cornerradius=4),
        text=[f"{count:,}" for count in rows["count"]], textposition="outside",
        cliponaxis=False,
        hovertemplate=f"<b>%{{y}}</b><br>{level}: %{{x:,}} students<extra></extra>",
    ))
    fig = base_layout(fig, height=100 + 55 * len(rows))
    fig.update_xaxes(title=f"{level} international students", range=[0, rows["count"].max() * 1.2])
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


def campus_comparison_lines(df, years):
    """Keep comparisons readable when many Fall years are selected."""
    fig = go.Figure()
    for school, color in SCHOOL_COLORS.items():
        rows = df[
            (df.institution == school) & df.year.isin(years)
            & (df.country == "All countries") & (df.academic_level == "All levels")
        ].set_index("year")["count"].reindex(years)
        if rows.isna().all():
            continue
        fig.add_trace(go.Scatter(
            x=years, y=rows, name=SHORT[school], mode="lines+markers", connectgaps=False,
            line=dict(color=color, width=2.5), marker=dict(size=8),
            hovertemplate=f"<b>{SHORT[school]}</b><br>Fall %{{x}}: %{{y:,}} students<extra></extra>",
        ))
    fig = base_layout(fig, height=430, hovermode="x unified",
                      legend=dict(orientation="h", y=1.12, x=0))
    fig.update_xaxes(title="Fall year", tickmode="array", tickvals=years)
    fig.update_yaxes(title="International students", rangemode="tozero")
    return fig


def level_year_lines(df, years, schools, level):
    """One colored trend per university for the selected study level."""
    fig = go.Figure()
    for school in schools:
        counts = df[(df.institution == school) & (df.country == "All countries")
                    & (df.academic_level == level)].set_index("year")["count"].reindex(years)
        if counts.isna().all():
            continue
        fig.add_trace(go.Scatter(
            x=years, y=counts, name=SHORT[school], mode="lines+markers", connectgaps=False,
            line=dict(color=SCHOOL_COLORS[school], width=3), marker=dict(size=9),
            hovertemplate=f"<b>{SHORT[school]}</b><br>Fall %{{x}}: %{{y:,}} {level.lower()} students<extra></extra>"
        ))
    fig = base_layout(fig, height=430, hovermode="x unified",
                      legend=dict(orientation="h", y=1.12, x=0))
    fig.update_xaxes(title="Fall year", tickmode="array", tickvals=years)
    fig.update_yaxes(title=f"{level} international students", rangemode="tozero")
    return fig


def india_year_lines(df, years, share=False):
    """India counts or India share by campus for all selected years."""
    fig = go.Figure()
    for school, color in SCHOOL_COLORS.items():
        india = df[(df.institution == school) & (df.country == "India")
                   & (df.academic_level == "All levels")].set_index("year")["count"].reindex(years)
        if india.isna().all():
            continue
        if share:
            total = df[(df.institution == school) & (df.country == "All countries")
                       & (df.academic_level == "All levels")].set_index("year")["count"].reindex(years)
            values = 100 * india / total
            hover = f"<b>{SHORT[school]}</b><br>Fall %{{x}}: %{{y:.1f}}% from India<extra></extra>"
        else:
            values = india
            hover = f"<b>{SHORT[school]}</b><br>Fall %{{x}}: %{{y:,}} students from India<extra></extra>"
        fig.add_trace(go.Scatter(
            x=years, y=values, name=SHORT[school], mode="lines+markers", connectgaps=False,
            line=dict(color=color, width=2.5), marker=dict(size=8), hovertemplate=hover))
    fig = base_layout(fig, height=400, hovermode="x unified",
                      legend=dict(orientation="h", y=1.12, x=0))
    fig.update_xaxes(title="Fall year", tickmode="array", tickvals=years)
    fig.update_yaxes(title="Share of international students from India (%)" if share
                     else "Students from India", rangemode="tozero")
    return fig


def india_contribution_bars(df, school, years):
    """India and other-country changes for each adjacent selected pair with data."""
    intervals, india_changes, other_changes = [], [], []
    for first, last in zip(years, years[1:]):
        if not (has_series(df, school, "India", start_year=first, end_year=last)
                and has_series(df, school, start_year=first, end_year=last)):
            continue
        india_change = value(df, school, last, "India") - value(df, school, first, "India")
        total_change = value(df, school, last) - value(df, school, first)
        intervals.append(f"{first} → {last}")
        india_changes.append(india_change)
        other_changes.append(total_change - india_change)
    if not intervals:
        return None
    fig = go.Figure()
    for name, amounts, color in (("India", india_changes, INDIA_COLOR),
                                 ("Other countries", other_changes, NEUTRAL)):
        fig.add_trace(go.Bar(x=intervals, y=amounts, name=name, marker_color=color,
                             text=[f"{amount:+,}" for amount in amounts], textposition="auto",
                             hovertemplate=f"%{{x}} · {name}: %{{y:+,}} students<extra></extra>"))
    fig = base_layout(fig, height=390, barmode="relative",
                      legend=dict(orientation="h", y=1.12, x=0))
    fig.update_xaxes(title="Selected Fall-year intervals")
    fig.update_yaxes(title="Change in international students")
    fig.add_hline(y=0, line=dict(color=NEUTRAL, width=1))
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
            x=s["year"], y=y, name=SHORT[school], mode="lines+markers",
            line=dict(color=color, width=2.5), marker=dict(size=8, line=dict(color="white", width=2)),
            customdata=s["count"],
            hovertemplate=f"<b>{school}</b><br>Fall %{{x}}: %{{customdata:,}} students"
                          + ("<br>Index: %{y:.1f}" if indexed else "") + "<extra></extra>",
        ))
    latest_year = int(df.year.max())
    fig.add_vrect(x0=latest_year - .5, x1=latest_year + .5, fillcolor=DROP, opacity=.08, line_width=0)
    if indexed:
        fig.add_hline(y=100, line=dict(color=NEUTRAL, width=1, dash="dash"))
    fig = base_layout(fig, height=520, hovermode="x unified",
                      margin=dict(l=10, r=10, t=20, b=130),
                      legend=dict(orientation="h", x=0, y=-.16, xanchor="left", yanchor="top",
                                  font=dict(size=11)))
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


def level_history_years(df, inst, country="All countries") -> set[int]:
    """Years with both published level counts for one campus and country scope."""
    rows = df[(df.institution == inst) & (df.country == country)]
    undergraduate = set(rows.loc[rows.academic_level == "Undergraduate", "year"])
    graduate = set(rows.loc[rows.academic_level == "Graduate", "year"])
    return undergraduate & graduate


# ── Page ─────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
  .block-container {padding-top: 2rem; max-width: 1150px;}
  div[data-testid="stMetric"] {border: 1px solid rgba(128,128,128,.25); border-radius: 12px; padding: 14px 18px;}
  div[data-testid="stMetricValue"] {font-size: 1.7rem;}
  .takeaway {border-left: 4px solid #2a78d6; padding: .5rem 1rem; margin: .5rem 0 1rem; background: rgba(42,120,214,.07);
             border-radius: 0 8px 8px 0;}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.subheader("University selection")
    selected_schools = st.multiselect(
        "Universities to compare", list(SCHOOL_COLORS), default=list(SCHOOL_COLORS),
        format_func=SHORT.get, key="enrollment_universities")
    st.caption("Applies to every enrollment view.")
    with st.expander("About these data"):
        st.markdown("- **Measure:** fall international headcount\n"
                    "- **Includes:** new and continuing students\n"
                    "- **Source:** university tables\n"
                    "- **Limits:** not new arrivals or causal proof")

# ── Opening ──
st.title("International enrollment")
if not selected_schools:
    st.info("Select at least one university in the sidebar to see the charts.")
    st.stop()

df = load().loc[lambda rows: rows.institution.isin(selected_schools)]
if df.empty:
    st.info("The selected universities have no published Fall counts.")
    st.stop()
all_years = sorted(int(year) for year in df.year.unique())
default_pair = [year for year in (2024, 2025) if year in all_years]
if len(default_pair) < 2:
    default_pair = all_years[-2:]
section_tabs = st.tabs([
    "Research context", "Fall snapshot", "Campuses", "By level", "India", "Year trends",
])

with section_tabs[0]:
    st.write("Explore published Fall enrollment counts at selected universities. "
             "The counts include new and continuing students and do not show why enrollment changed.")
    with st.expander("Data & sources"):
        st.dataframe(df.drop(columns=["period", "measure", "source_definition"]),
                     hide_index=True, width="stretch")
        st.markdown("\n".join(f"- [{k}]({u})" for k, u in SOURCES.items()))

with section_tabs[1]:
    snapshot_years = sorted(st.multiselect(
        "Fall years for this snapshot (up to four)", all_years, default=default_pair,
        max_selections=4, key="snapshot_years"))
    if not snapshot_years:
        st.info("Select at least one Fall year.")
    else:
        first_year, snapshot_year = snapshot_years[0], snapshot_years[-1]
        snapshot_df = df[df.year.isin(snapshot_years)]
        st.subheader(f"Fall {snapshot_year}")
        st.plotly_chart(snapshot_bars(snapshot_df, snapshot_year), width="stretch", key="fall_snapshot_chart")
        st.caption("Published campuses only · not a national total")
        if len(snapshot_years) >= 2:
            overall = changes(snapshot_df, first_year, snapshot_year)
            if not overall.empty:
                india = changes(snapshot_df, first_year, snapshot_year, country="India")
                ug = changes(snapshot_df, first_year, snapshot_year, level="Undergraduate")
                grad = changes(snapshot_df, first_year, snapshot_year, level="Graduate")
                levels = ug.merge(grad, on=["institution", "label"], suffixes=("_ug", "_grad"))
                lost_grad = -levels.loc[levels.diff_grad < 0, "diff_grad"].sum()
                lost_ug = -levels.loc[levels.diff_ug < 0, "diff_ug"].sum()
                n_down = int((overall.pct < -1).sum())
                worst = overall.sort_values("pct").iloc[0]
                st.subheader(f"Fall {first_year} → Fall {snapshot_year}")
                sentences = [f"International enrollment fell by more than 1% at {n_down} of {len(overall)} "
                             "comparable campuses."]
                if worst.pct < 0:
                    sentences.append(f"{worst.label} had the largest decline, falling {abs(worst.pct):.1f}% "
                                     f"from {worst.c_start:,} to {worst.c_end:,} students.")
                elif worst.pct > 0:
                    sentences.append(f"{worst.label} had the smallest increase, rising {worst.pct:.1f}% "
                                     f"from {worst.c_start:,} to {worst.c_end:,} students.")
                else:
                    sentences.append(f"{worst.label} had no change, with {worst.c_end:,} students in both years.")
                if india.empty:
                    sentences.append("None of the selected campuses reported India enrollment for both years.")
                elif len(india) == 1:
                    row = india.iloc[0]
                    movement = "fell" if row.pct < 0 else "rose" if row.pct > 0 else "was unchanged"
                    amount = f" by {abs(row.pct):.1f}%" if row.pct else ""
                    sentences.append(f"Enrollment from India at {row.label} {movement}{amount}.")
                else:
                    n_india_down = int((india.pct < 0).sum())
                    sentences.append(f"Enrollment from India fell at {n_india_down} of {len(india)} "
                                     "campuses that reported it in both years.")
                if lost_grad + lost_ug:
                    sentences.append(f"Graduate students accounted for {lost_grad / (lost_grad + lost_ug):.0%} "
                                     "of the enrollment losses in published level counts "
                                     f"({lost_grad:,} graduate and {lost_ug:,} undergraduate).")
                elif levels.empty:
                    sentences.append("None of the selected campuses reported both study levels in both years.")
                else:
                    sentences.append("The published undergraduate and graduate counts showed no enrollment losses.")
                st.markdown("\n".join(f"- {sentence}" for sentence in sentences))
            else:
                st.info("Choose two years reported by the same university to see a comparison.")

with section_tabs[2]:
    campus_years = sorted(st.multiselect(
        "Fall years", all_years, default=default_pair, key="campus_years"))

    if not campus_years:
        st.info("Select at least one Fall year to see campuses.")
    else:
        start_year, end_year = campus_years[0], campus_years[-1]
        campus_df = df[df.year.isin(campus_years)]
        if len(campus_years) == 1:
            st.plotly_chart(snapshot_bars(campus_df, end_year), width="stretch", key="campus_snapshot_chart")
        elif len(campus_years) <= 4:
            st.plotly_chart(campus_comparison_bars(campus_df, campus_years), width="stretch")
        else:
            st.plotly_chart(campus_comparison_lines(campus_df, campus_years), width="stretch")
            st.caption("Line chart keeps comparisons readable when more than four years are selected.")
        st.caption("Published campuses only · gaps mean unpublished data · not a national total")

        if len(campus_years) >= 2:
            overall = changes(campus_df, start_year, end_year)
            if not overall.empty:
                n_down = int((overall.pct < -1).sum())
                worst = overall.sort_values("pct").iloc[0]
                st.subheader(f"Fall {start_year} → {end_year}")
                if n_down:
                    st.write(
                        f"From Fall {start_year} to {end_year}, enrollment fell by over 1% at {n_down} of "
                        f"{len(overall)} campuses; {worst.label} had the largest drop "
                        f"({abs(worst.pct):.1f}%)."
                    )
                else:
                    st.write(
                        f"From Fall {start_year} to {end_year}, enrollment did not fall by over 1% at "
                        f"any of the {len(overall)} campuses with data for both years."
                    )
            else:
                st.info("No selected university reports totals in both endpoint years.")

        st.subheader("Inside selected campuses")
        available = set(fall_headcounts(campus_df, end_year).institution)
        detail_options = [school for school in selected_schools if school in available]
        if detail_options:
            for inst in detail_options:
                selected_count = value(campus_df, inst, end_year)
                comparable = len(campus_years) >= 2 and has_series(
                    campus_df, inst, start_year=start_year, end_year=end_year)
                heading = f"{SHORT[inst]} · Fall {end_year}: {selected_count:,} students"
                if comparable:
                    previous_count = value(campus_df, inst, start_year)
                    difference = selected_count - previous_count
                    heading += f" · {difference:+,} ({100 * difference / previous_count:+.1f}%) vs {start_year}"
                with st.expander(heading):
                    if comparable:
                        st.write(f"Fall {end_year}: {selected_count:,} international students, "
                                 f"{difference:+,} from Fall {start_year}.")
                        splits = available_splits(campus_df, inst, start_year, end_year)
                        split = st.selectbox("Break down by", splits, format_func=SPLITS.get,
                                             key=f"explorer_split_{inst}_{start_year}_{end_year}")
                        parts = decompose(campus_df, inst, split, start_year, end_year)
                        st.plotly_chart(change_bars(parts), width="stretch")
                        st.caption(f"Fall {start_year} → {end_year} · right = gain, left = loss")
                    elif len(campus_years) >= 2:
                        st.info("This campus has no total in both selected endpoint years.")
                    else:
                        st.write(f"Fall {end_year}: {selected_count:,} international students.")
        else:
            st.info(f"No selected campus reports a Fall {end_year} total.")

        with st.expander("Change chart and related reports"):
            if len(campus_years) >= 2 and not overall.empty:
                st.plotly_chart(diverging(overall, start_year, end_year), width="stretch")
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
    level_years = sorted(st.multiselect(
        "Fall years for this chart", all_years, default=default_pair, key="level_years"))
    study_level = st.radio("Study level", ["Graduate", "Undergraduate"],
                           horizontal=True, key="study_level")
    if not level_years:
        st.info("Select at least one Fall year.")
    else:
        level_df = df[df.year.isin(level_years)]
        level_schools = [school for school in selected_schools if not level_df[
            (level_df.institution == school) & (level_df.country == "All countries") &
            (level_df.academic_level == study_level)].empty]
        if not level_schools:
            st.info(f"No selected university publishes {study_level.lower()} counts for these years.")
        elif len(level_years) == 1:
            fig = level_snapshot_bars(
                level_df[level_df.institution.isin(level_schools)],
                level_years[0], study_level)
            if fig is None:
                st.info(f"No {study_level.lower()} counts for this selection.")
            else:
                st.plotly_chart(fig, width="stretch")
                st.caption(f"Fall {level_years[0]} · reported headcounts")
        else:
            st.plotly_chart(level_year_lines(level_df, level_years, level_schools, study_level),
                            width="stretch")
            st.caption(f"Each line shows {study_level.lower()} students at one selected university. "
                       "Higher means more students; gaps mean no published count.")

with section_tabs[4]:
    india_years = sorted(st.multiselect(
        "Fall years for India charts", all_years, default=default_pair, key="india_years"))
    change_tab, share_tab, contribution_tab, history_tab = st.tabs(
        ["Change", "India share", "Contribution", "History"])
    india_df = df[df.year.isin(india_years)]
    india_schools = [school for school in selected_schools if not india_df[
        (india_df.institution == school) & (india_df.country == "India") &
        (india_df.academic_level == "All levels")].empty]
    if len(india_years) >= 2:
        first, last = india_years[0], india_years[-1]
        india = changes(india_df, first, last, country="India")
        overall = changes(india_df, first, last)
        india_vs_all = india.merge(overall, on=["institution", "label"],
                                   suffixes=("_india", "_all"))
    else:
        india_vs_all = pd.DataFrame()

    with change_tab:
        if not india_years:
            st.info("Select at least one Fall year.")
        elif not india_schools:
            st.info("No India counts for these years and universities.")
        elif len(india_years) == 1:
            st.plotly_chart(india_snapshot_bars(india_df, india_years[0]),
                            width="stretch", key="india_change_snapshot")
            st.caption(f"Fall {india_years[0]} · share of international students from India")
        else:
            st.plotly_chart(india_year_lines(india_df, india_years),
                            width="stretch")
            st.caption("India headcounts for every selected Fall year · gaps mean unpublished data")
            if not india_vs_all.empty:
                with st.expander(f"Percent change: Fall {first} → {last}"):
                    st.caption("Change compares the earliest and latest selected years.")
                    st.plotly_chart(paired_bars(
                        india_vs_all.sort_values("pct_india"),
                        [("Students from India", "pct_india", INDIA_COLOR),
                         ("All international students", "pct_all", ALL_COLOR)], "pct"),
                        width="stretch")
    with share_tab:
        if not india_years:
            st.info("Select at least one Fall year.")
        elif not india_schools:
            st.info("No India counts for these years and universities.")
        elif len(india_years) == 1:
            st.plotly_chart(india_snapshot_bars(india_df, india_years[0]),
                            width="stretch", key="india_share_snapshot")
        else:
            st.plotly_chart(india_year_lines(india_df, india_years, share=True),
                            width="stretch")
            st.caption("India count ÷ all international students at each campus")
    with contribution_tab:
        if len(india_years) < 2:
            st.info("Select at least two Fall years.")
        elif not india_schools:
            st.info("No India counts for these years and universities.")
        else:
            st.caption("Each interval uses adjacent selected years with published counts. "
                       "India change + other-country change = total change.")
            for index, school in enumerate(india_schools):
                with st.expander(SHORT[school], expanded=index == 0):
                    fig = india_contribution_bars(india_df, school, india_years)
                    if fig is None:
                        st.info("This campus needs two selected years with both India and total counts.")
                    else:
                        st.plotly_chart(fig, width="stretch")
    with history_tab:
        india_history_years = sorted(st.multiselect(
            "Fall years for India history", all_years, default=all_years[-5:],
            key="india_history_years"))
        if india_history_years:
            history_df = df[df.year.isin(india_history_years)]
            if history_df[history_df.country == "India"].empty:
                st.info("No India counts for these years and universities.")
            else:
                st.plotly_chart(trends(history_df, True, india_history_years[0],
                                       country="India"), width="stretch")
                st.caption("Index: first selected year reported by each campus = 100 · hover for counts")
                if "UC Berkeley" in selected_schools:
                    with st.expander("Berkeley source note"):
                        st.caption("Berkeley's 2024 value uses its 2024 report; its 2025 report repeats an older baseline.")
        else:
            st.info("Select at least one Fall year.")

with section_tabs[5]:
    trend_years = sorted(st.multiselect(
        "Fall years for trends", all_years, default=all_years[-5:],
        key="trend_years"))
    if not trend_years:
        st.info("Select at least one Fall year.")
    else:
        trend_df = df[df.year.isin(trend_years)]
        indexed = st.toggle("Index each campus to its first selected year",
                            value=True, key="trend_indexed")
        st.plotly_chart(trends(trend_df, indexed, trend_years[0]), width="stretch")
        st.caption("Only selected Fall years are shown · index = 100 at each campus's first selected year · hover for counts")

        level_campuses = [school for school in selected_schools if
                          len(level_history_years(trend_df, school)) >= 2]
        if level_campuses:
            with st.expander("Undergraduate and graduate over time, by campus"):
                for index, inst in enumerate(level_campuses):
                    with st.expander(SHORT[inst], expanded=index == 0):
                        scopes = ["All countries"] + (["India"] if
                            len(level_history_years(trend_df, inst, "India")) >= 2 else [])
                        country = st.radio("Country scope", scopes, horizontal=True,
                                           key=f"level_scope_{inst}")
                        st.plotly_chart(level_area(trend_df, inst, country), width="stretch")
