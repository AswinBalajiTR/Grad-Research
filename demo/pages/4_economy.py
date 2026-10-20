"""Economic indicators since 2022
Run: streamlit run demo/app.py
"""

import sys
import textwrap
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "code/economic_indicators"))
from common import ROOT, STOP_DATE  # noqa: E402

# The processed files now live in data/economic_indicators and data/policy_timeline.
OUT = ROOT / "data" / "economic_indicators"
EVENTS_PATH = ROOT / "data" / "policy_timeline" / "policy_events_to_verify.csv"

# ---------------------------------------------------------------- palette
# Reference palette from the data-viz guidelines: categorical slots in fixed
# order and a single-hue blue ramp for magnitude.
PALETTE = {
    "light": {
        "series": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
        "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781", "grid": "#e1e0d9", "mid": "#f0efec",
    },
    "dark": {
        "series": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
        "ink": "#ffffff", "ink2": "#c3c2b7", "muted": "#898781", "grid": "#2c2c2a", "mid": "#383835",
    },
}
BLUE_RAMP = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
             "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
try:
    MODE = "dark" if st.context.theme.type == "dark" else "light"
except Exception:
    MODE = "light"
P = PALETTE[MODE]
SEQUENTIAL = [[i / (len(BLUE_RAMP) - 1), c] for i, c in enumerate(BLUE_RAMP)]


def series_color(i):
    return P["series"][i % len(P["series"])]


STATE_FIPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE", "11": "DC",
    "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT",
    "31": "NE", "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI", "56": "WY", "72": "PR",
}
SECTORS = {"1": "Public, 4-year+", "2": "Private nonprofit, 4-year+", "3": "Private for-profit, 4-year+",
           "4": "Public, 2-year", "5": "Private nonprofit, 2-year", "6": "Private for-profit, 2-year",
           "7": "Public, <2-year", "8": "Private nonprofit, <2-year", "9": "Private for-profit, <2-year"}
HOME_STATES = ["DC", "VA"]  # default selection wherever the page picks states or places
START, END = date(2022, 1, 1), date.fromisoformat(STOP_DATE)  # every chart covers the whole study period


# ---------------------------------------------------------------- data
def modified(name):
    """File modification time, passed to the cached loaders so a rebuilt file is read again."""
    path = OUT / name
    return path.stat().st_mtime if path.exists() else None


def load_long(name):
    return _load_long(name, modified(name))


def load_table(name, **kw):
    return _load_table(name, modified(name), **kw)


@st.cache_data(show_spinner="Loading data")
def _load_long(name, mtime):
    path = OUT / name
    if mtime is None:
        return None
    df = pd.read_csv(path, dtype={"unit_id": str, "period": str, "measure": str}, encoding="utf-8-sig")
    periods = pd.Series(df["period"].unique())
    if periods.str.contains("-Q").all():
        dates = pd.PeriodIndex(periods.str.replace("-Q", "Q"), freq="Q").to_timestamp()
    elif periods.str.match(r"^\d{4}-\d{2}$").all():
        dates = pd.to_datetime(periods + "-01")
    elif periods.str.match(r"^\d{4}-\d{2}-\d{2}$").all():
        dates = pd.to_datetime(periods)
    else:
        dates = pd.to_datetime(periods.str[:4] + "-01-01", errors="coerce")
    df["date"] = df["period"].map(dict(zip(periods, dates)))
    return df


@st.cache_data
def _load_table(name, mtime, **kw):
    return pd.read_csv(OUT / name, encoding="utf-8-sig", **kw) if mtime is not None else None


@st.cache_data
def load_events():
    if not EVENTS_PATH.exists():
        return pd.DataFrame(columns=["event_date", "title", "topic"])
    ev = pd.read_csv(EVENTS_PATH, encoding="utf-8-sig")
    ev["event_date"] = pd.to_datetime(ev["event_date"], errors="coerce")
    ev["topic"] = ev["topic"].fillna("Other / unassigned")
    return ev.dropna(subset=["event_date"])


# The derived tables below take the source files' modification times only so the cache
# is rebuilt when a file changes.
@st.cache_data(show_spinner="Preparing rents")
def zori_wide(mtimes):
    z = load_long("zori.csv")
    if z is None:
        return None
    return z.pivot_table(index="date", columns="unit_id", values="value").sort_index()


@st.cache_data
def zip_exposure(mtimes):
    """Lookup of ZORI ZIPs with metro, campus flag, and international students nearby."""
    zips = load_table("zori_zips.csv", dtype={"zip": str})
    exp = load_long("exposure.csv")
    if zips is None:
        return None
    zips["zip"] = zips["zip"].str.zfill(5)
    if exp is not None:
        near = exp[(exp.unit_type == "zcta") & exp.measure.str.startswith("intl_enrollment_within")]
        latest = near[near.period == near.period.max()].set_index("unit_id")["value"]
        zips["intl_nearby"] = zips["zip"].map(latest).fillna(0)
    else:
        zips["intl_nearby"] = 0
    return zips.set_index("zip")


@st.cache_data
def institutions(mtimes):
    inst = load_table("institutions.csv", dtype={"unitid": str, "sector": str, "county_fips": str, "cbsa": str})
    if inst is None:
        return None
    inst["sector_name"] = inst["sector"].map(SECTORS).fillna("Other")
    return inst


@st.cache_data
def institution_years(mtimes):
    """Institution x fall wide table of enrollment measures."""
    exp = load_long("exposure.csv")
    if exp is None:
        return None
    inst = exp[exp.unit_type == "institution"]
    wide = inst.pivot_table(index=["unit_id", "unit_name", "period"], columns="measure", values="value").reset_index()
    wide["year"] = wide["period"].str[:4].astype(int)
    return wide


def to_wide(df, measure, unit_type):
    """Pivot one measure of a long table to dates x units."""
    d = df[(df.measure == measure) & (df.unit_type == unit_type)]
    return d.pivot_table(index="date", columns="unit_id", values="value").sort_index()


# ---------------------------------------------------------------- chart helpers
def line_chart(wide, title, unit, height=420):
    """One line per column, in actual values."""
    fig = go.Figure()
    for i, col in enumerate(wide.columns):
        s = wide[col].dropna()
        if not s.empty:
            fig.add_trace(go.Scatter(x=s.index, y=s.values, name=str(col), mode="lines",
                                     line=dict(width=2, color=series_color(i)), hovertemplate="%{y:,}"))
    fig.update_layout(title=dict(text=title, font=dict(size=15)), height=height, hovermode="x unified",
                      margin=dict(l=10, r=10, t=60, b=10), legend=dict(orientation="h", yanchor="top", y=-0.12, x=0),
                      yaxis=dict(title=unit, gridcolor=P["grid"], zeroline=False), xaxis=dict(showgrid=False))
    return fig


def arrow(v, fmt):
    """A change with an up or down arrow in front, e.g. '▲ +1.2%' or '▼ -$40' (fmt "dollars");
    a missing value shows as '–'."""
    if pd.isna(v):
        return "–"
    text = f"{'+' if v >= 0 else '-'}${abs(v):,.0f}" if fmt == "dollars" else fmt.format(v)
    return f"{'▲' if v > 0 else '▼' if v < 0 else '•'} {text}"


# Rent trend windows: months back from the latest month (None = the whole period).
TREND_WINDOWS = {"Last 3 months": 3, "Last 6 months": 6, "Last 12 months": 12, "Last 24 months": 24,
                 "Whole period": None}
FLAT = 12  # dollars per year; a slope smaller than this counts as flat


def fit(x, y):
    """(slope, intercept) of a least-squares straight line; flat when there is one point."""
    return tuple(np.polyfit(x, y, 1)) if len(y) > 1 else (0.0, float(y[0]))


def trend_sentence(window, recent):
    """One line naming the ZIPs rising, flat and falling over the window, fastest first."""
    def names(rows):
        return ", ".join(f"{z} ({'+' if v >= 0 else '-'}${abs(v):,.0f}/yr)" for v, z in rows)
    up = sorted([r for r in recent if r[0] >= FLAT], reverse=True)
    down = sorted(r for r in recent if r[0] <= -FLAT)
    flat = [r for r in recent if abs(r[0]) < FLAT]
    parts = [f"**Rising:** {names(up)}" if up else "", f"**Falling:** {names(down)}" if down else "",
             f"**Flat:** {names(flat)}" if flat else ""]
    return f"{window}: " + " · ".join(p for p in parts if p)


def wrap(text, width=70):
    """Hover text broken into lines of about `width` characters, so the hover box grows
    downwards to fit the whole text instead of running off the chart."""
    return "<br>&nbsp;&nbsp;".join(textwrap.wrap(str(text), width)) or ""


def show(fig, key=None):
    st.plotly_chart(fig, width="stretch", theme="streamlit", key=key)


def download(df, name, label="Download CSV"):
    st.download_button(label, df.to_csv(index=True).encode("utf-8"), file_name=name, mime="text/csv",
                       key=f"dl_{name}")


EVENTS = load_events()

st.title("International students and local economies, 2022 onward")


TAB_NAMES = ["International students", "Student flows", "Rents near campus", "University jobs", "Policy events",
             "Data & notes"]
T = dict(zip(TAB_NAMES, st.tabs(TAB_NAMES)))

ZW = zori_wide(modified("zori.csv"))
ZIPS = zip_exposure((modified("zori_zips.csv"), modified("exposure.csv")))
INST = institutions(modified("institutions.csv"))
IYEARS = institution_years(modified("exposure.csv"))
EXP = load_long("exposure.csv")
QCEW = load_long("qcew.csv")
BEA = load_long("bea_education.csv")
BLS = load_long("bls_ces.csv")
FUND = load_long("research_funding.csv")
VISA = load_long("visa_issuances.csv")
I94 = load_long("i94_arrivals.csv")
SEVIS = load_long("sevis.csv")

# ---------------------------------------------------------------- student flows
# The three stages a student passes: visa issued, arrival at the border, active in SEVIS.
# Student visas match NTTO's I-94 student group (F-1, F-2, M-1; M-2 is not fetched).
STUDENT_CLASSES = ["f1_issuances", "f2_issuances", "m1_issuances"]
STAGES = ["Student visas issued (F-1, F-2, M-1)", "Arrivals on student visas (I-94)", "Active students (SEVIS)"]
STAGE_COLORS = {s: series_color(i) for i, s in enumerate(STAGES)}
ALL = "all"
# Each source names countries its own way: (visa nationality, I-94 country of residence, SEVIS code).
# None: the source does not break the country out (I-94 lists only the larger overseas markets).
COUNTRIES = {
    "All countries": (ALL, "Grand Total", ALL), "India": ("India", "India", "IN"),
    "China": ("China - mainland", "PRC (Excluding Hong Kong)", "CN"), "Vietnam": ("Vietnam", "Vietnam", "VN"),
    "South Korea": ("Korea, South", "Korea, South", "KR"), "Japan": ("Japan", "Japan", "JP"),
    "Taiwan": ("Taiwan", "Taiwan", "TW"), "Nepal": ("Nepal", None, "NP"), "Bangladesh": ("Bangladesh", None, "BD"),
    "Pakistan": ("Pakistan", "Pakistan", "PK"), "Nigeria": ("Nigeria", "Nigeria", "NG"),
    "Ghana": ("Ghana", "Ghana", "GH"), "Iran": ("Iran", "Iran", "IR"), "Saudi Arabia": ("Saudi Arabia", "Saudi Arabia", "SA"),
    "Turkey": ("Turkey", "Turkey", "TR"), "Brazil": ("Brazil", "Brazil", "BR"), "Colombia": ("Colombia", "Colombia", "CO"),
    "Mexico": ("Mexico", "Mexico Excluding Land", "MX"),
}
# H-1B issuances are left out: the H-1B page covers that pathway.
VISA_CLASSES = {"f1_issuances": "F-1 students", "j1_issuances": "J-1 exchange visitors",
                "b1_b2_issuances": "B1/B2 business and tourism"}


@st.cache_data
def stage_series(country):
    """Monthly counts of the three stages for one country, on a complete monthly index."""
    visa, i94, sevis = COUNTRIES[country]
    out = {}
    if VISA is not None:
        d = VISA[VISA.measure.isin(STUDENT_CLASSES)]
        out[STAGES[0]] = (d if visa == ALL else d[d.unit_id == visa]).groupby("date").value.sum()
    if I94 is not None and i94:
        d = I94[(I94.measure == "student_visa_arrivals") & (I94.unit_id == i94)]
        out[STAGES[1]] = d.groupby("date").value.sum()
    if SEVIS is not None:
        d = SEVIS[(SEVIS.unit_type == "country") & (SEVIS.measure == "active_students")]
        out[STAGES[2]] = (d if sevis == ALL else d[d.unit_id == sevis]).groupby("date").value.sum()
    w = pd.DataFrame({k: v for k, v in out.items() if not v.empty})
    return w.reindex(pd.date_range(w.index.min(), w.index.max(), freq="MS")) if not w.empty else w


@st.cache_data
def class_series(country):
    """Monthly issuances of the compared visa classes for one country."""
    visa = COUNTRIES[country][0]
    d = VISA[VISA.measure.isin(list(VISA_CLASSES))]
    d = d if visa == ALL else d[d.unit_id == visa]
    w = d.pivot_table(index="date", columns="measure", values="value", aggfunc="sum")
    return w.reindex(pd.date_range(w.index.min(), w.index.max(), freq="MS"))


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def year_colors(years):
    """A fixed color per year, so a year keeps it whatever else is picked; the latest gets the first slot."""
    years = sorted(years)
    return {y: series_color(len(years) - 1 - k) for k, y in enumerate(years)}


def year_bars(fig, s, picked, colors, row, col, legend):
    """Overlapping bars of a monthly series by month of the year, one set per picked year."""
    for y in picked:
        sy = s[s.index.year == y].dropna()
        fig.add_trace(go.Bar(x=sy.index.month, y=sy.values, name=str(y), legendgroup=str(y), showlegend=legend,
                             marker=dict(color=colors[y], opacity=0.55, line=dict(color=P["mid"], width=1)),
                             hovertemplate=f"{y}: %{{y:,.0f}}<extra></extra>"), row=row, col=col)
    fig.update_xaxes(tickmode="array", tickvals=list(range(1, 13)), ticktext=MONTHS, range=[0.5, 12.5],
                     showgrid=False, row=row, col=col)


def stage_chart(raw, picked, shown):
    """The picked stages overlapping for every month of the picked years, in one chart.
    SEVIS (a running total) goes on a right-hand axis when shown with the monthly counts."""
    # Only months of the picked years that have data for a shown stage, on a category axis, so the
    # years left out take no room on the chart.
    d = raw.loc[raw.index.year.isin(picked), shown].dropna(how="all")
    months = d.index.strftime("%b %Y")
    right = STAGES[2] in shown and len(shown) > 1
    fig = make_subplots(specs=[[{"secondary_y": right}]])
    # Drawn last stage first, so the usually smaller monthly visa bars sit on top; the legend keeps
    # the funnel order. One shared offsetgroup puts the bars at the same spot on both axes.
    for s in shown[::-1]:
        fig.add_trace(go.Bar(x=months, y=d[s], name=s, offsetgroup="stages", legendrank=STAGES.index(s),
                             marker=dict(color=STAGE_COLORS[s], opacity=0.6, line=dict(color=P["mid"], width=1)),
                             hovertemplate="%{y:,.0f}"), secondary_y=right and s == STAGES[2])
    monthly = [s for s in shown if s != STAGES[2]]
    fig.update_yaxes(title_text="Per month" if monthly else "Students", gridcolor=P["grid"], zeroline=False,
                     rangemode="tozero", secondary_y=False)
    if right:
        fig.update_yaxes(title_text="Active students (SEVIS)", showgrid=False, zeroline=False, rangemode="tozero",
                         secondary_y=True)
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=list(months), tickangle=-45,
                     showgrid=False)
    # A dotted line where each new year starts.
    for k in np.flatnonzero(np.diff(d.index.year)) + 1:
        fig.add_vline(x=k - 0.5, line=dict(color=P["muted"], width=1, dash="dot"))
    fig.update_layout(barmode="overlay", bargap=0.2,
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=1, xanchor="right"))
    return fig


def county_exposure(year):
    c = EXP[(EXP.unit_type == "county") & (EXP.measure == "intl_per_1000_residents")]
    c = c[c.period == f"{year}-fall"]
    return c.set_index("unit_id")["value"], dict(zip(c.unit_id, c.unit_name))


# ================================================================= International students
with T["International students"]:
    if IYEARS is None or INST is None:
        st.warning("Run build_exposure.py first.")
    else:
        years = sorted(IYEARS.year.unique())
        # Fall 2021 is only for the county chart; the table keeps to the study period.
        y0, y1 = min(y for y in years if y >= START.year), years[-1]
        wide = IYEARS.pivot_table(index="unit_id", columns="year",
                                  values=["intl_enrollment", "enrollment", "intl_share", "grad_intl_enrollment",
                                          "undergrad_intl_enrollment"])
        df = INST.set_index("unitid").join(pd.DataFrame({
            "intl_first": wide[("intl_enrollment", y0)], "intl_last": wide[("intl_enrollment", y1)],
            "share_last": wide[("intl_share", y1)] * 100, "grad_last": wide[("grad_intl_enrollment", y1)],
            "ug_last": wide[("undergrad_intl_enrollment", y1)], "enroll_last": wide[("enrollment", y1)],
        }), how="inner")

        # The graduate/undergraduate "Largest hosts" chart is left out: the Enrollment page covers that split.
        c1, c2 = st.columns([1, 2])
        picked = c1.multiselect("Falls to compare", years[::-1], default=[y1], key="county_years")
        top_n = c2.slider("Counties to show", 5, 30, 15)
        if not picked:
            st.info("Pick at least one fall.")
        else:
            picked = sorted(picked)
            year_color = year_colors(years)
            # Counties ranked by the latest fall picked, and shown for every picked fall.
            cexp, cnames = county_exposure(picked[-1])
            top = cexp.sort_values(ascending=False).head(top_n).index[::-1]
            labels = [cnames.get(i, i) for i in top]
            fig = go.Figure()
            xmax = 0
            for y in picked:
                per = county_exposure(y)[0].reindex(top)
                intl = EXP[(EXP.unit_type == "county") & (EXP.measure == "intl_enrollment")
                           & (EXP.period == f"{y}-fall")].set_index("unit_id")["value"].reindex(top)
                xmax = max(xmax, per.max())
                fig.add_trace(go.Bar(x=per.values, y=labels, orientation="h", name=f"Fall {y}",
                                     marker=dict(color=year_color[y], line=dict(color=P["mid"], width=1)),
                                     text=per.values, texttemplate="%{x:.1f}", textposition="outside",
                                     cliponaxis=False, customdata=intl.fillna(0).astype(int).values,
                                     hovertemplate=f"%{{y}}<br>Fall {y}: %{{x:.1f}} per 1,000 residents<br>"
                                                   f"%{{customdata:,}} international students<extra></extra>"))
            fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.05,
                              height=max(400, (10 + 14 * len(picked)) * len(top) + 160),
                              margin=dict(l=10, r=10, t=40, b=10), hovermode="closest",
                              title=f"Most dependent counties (ranked by fall {picked[-1]})",
                              legend=dict(orientation="h", yanchor="bottom", y=1.0, x=1, xanchor="right",
                                          traceorder="reversed"),
                              xaxis=dict(title="International students per 1,000 residents", gridcolor=P["grid"],
                                         range=[0, xmax * 1.2]))
            show(fig, "county_bar")

        with st.expander("Table"):
            cols = ["name", "state", "sector_name", "enroll_last", "intl_first", "intl_last", "share_last",
                    "grad_last", "ug_last", "county_name"]
            st.dataframe(df[cols].sort_values("intl_last", ascending=False), width="stretch",
                         column_config={"share_last": st.column_config.NumberColumn("Intl share %", format="%.1f")})
            download(df[cols].assign(share_last=df.share_last.round(1)), "institutions_filtered.csv")


# ================================================================= Student flows
with T["Student flows"]:
    if VISA is None or SEVIS is None:
        st.warning("Run fetch_visa_issuances.py, fetch_i94_arrivals.py and fetch_sevis.py first.")
    else:
        c1, c2 = st.columns([1, 2])
        country = c1.selectbox("Country", list(COUNTRIES), index=1, key="flow_country")
        raw = stage_series(country)
        cw = class_series(country)
        flow_years = sorted(set(raw.dropna(how="all").index.year) | set(cw.dropna(how="all").index.year))
        picked = sorted(c2.multiselect("Years to compare", flow_years[::-1], default=flow_years[-2:][::-1],
                                       key="flow_years"))
        colors = year_colors(flow_years)

        if not picked:
            st.info("Pick at least one year.")
        else:
            st.markdown("#### Visa issued → arrival → enrolled")
            stages = [s for s in STAGES if s in raw]
            shown = st.pills("Show", stages, selection_mode="multi", default=stages, key="flow_stages")
            shown = [s for s in stages if s in (shown or [])]  # keep the funnel order whatever the click order
            if not shown:
                st.info("Pick at least one measure.")
            else:
                fig = stage_chart(raw, picked, shown)
                fig.update_layout(height=480, hovermode="x unified", margin=dict(l=10, r=10, t=70, b=10),
                                  title=dict(text=f"{country}: visas issued, arrivals and active students, "
                                                  "by month", font=dict(size=15)))
                show(fig, "flow_one")
                if STAGES[2] in shown and len(shown) > 1:
                    st.caption("Active students (SEVIS) are read on the right axis: they are a running total, "
                               "far larger than the monthly visa and arrival counts.")

            st.markdown("#### Visas issued by class")
            names = [m for m in VISA_CLASSES if m in cw]
            fig = make_subplots(rows=1, cols=len(names), horizontal_spacing=0.06,
                                subplot_titles=[VISA_CLASSES[m] for m in names])
            for k, m in enumerate(names):
                year_bars(fig, cw[m], picked, colors, 1, k + 1, legend=k == 0)
            fig.update_yaxes(gridcolor=P["grid"], zeroline=False, rangemode="tozero")
            fig.update_yaxes(title_text="Visas per month", col=1)
            fig.update_annotations(font=dict(size=13, color=P["ink2"]))
            fig.update_layout(height=400, hovermode="x unified", barmode="overlay",
                              margin=dict(l=10, r=10, t=70, b=10),
                              legend=dict(orientation="h", yanchor="bottom", y=1.1, x=1, xanchor="right"),
                              title=dict(text=f"{country}: visas issued per month, by class", font=dict(size=15)))
            show(fig, "flow_classes")

        with st.expander("Table"):
            tbl = raw.join(class_series(country).rename(columns=VISA_CLASSES)).rename_axis("month")
            st.dataframe(tbl.dropna(how="all"), width="stretch")
            download(tbl, f"student_flows_{country.lower().replace(' ', '_')}.csv")


# ================================================================= Rents
with T["Rents near campus"]:
    if ZW is None or ZIPS is None:
        st.warning("Run fetch_zori.py first.")
    else:
        st.caption(f"Zillow Observed Rent Index: the typical monthly asking rent, in dollars, for homes and apartments "
                   f"listed in each ZIP code (smoothed). {ZW.index.min():%b %Y} to {ZW.index.max():%b %Y}.")
        cz = load_table("campus_zips.csv", dtype={"unitid": str, "zcta": str})
        radius = ""
        if EXP is not None:
            m = EXP.loc[EXP.measure.str.startswith("intl_enrollment_within"), "measure"]
            radius = m.iloc[0].split("within_")[1].replace("mi", "") if len(m) else ""
        # Every campus with international students within the radius of each ZIP, most international students first.
        if cz is not None:
            intl = INST.set_index("unitid")["intl_enrollment"] if INST is not None else pd.Series(dtype=float)
            cz = cz.assign(intl=cz.unitid.map(intl).fillna(0)).sort_values(["intl", "distance_mi"],
                                                                           ascending=[False, True])
            unis_hover = cz.groupby("zcta").apply(lambda g: "<br>".join(
                f"• {r['name']} ({int(r.intl)} intl students, {r.distance_mi:.1f} mi)" for _, r in g.iterrows()))
            unis_text = cz.groupby("zcta")["name"].agg("; ".join)
        else:
            unis_hover = unis_text = pd.Series(dtype=str)
        zl = ZIPS.loc[ZIPS.index.intersection(ZW.columns)]
        # Some ZIPs have no city or state in Zillow's file; a missing piece must not blank the whole label.
        place = (zl.city.fillna("").astype(str) + ", " + zl.state.fillna("").astype(str)).str.strip(", ")
        labels = {z: f"{z} – {p}" for z, p in zip(zl.index, place)}
        # ZIPs near a campus first, those with the most international students nearby at the top.
        options = list(zl.sort_values(["near_campus", "intl_nearby"], ascending=False).index)
        # Default: the three ZIPs with the most international students nearby in each home state.
        default = [z for s in HOME_STATES for z in [o for o in options if zl.state.get(o) == s][:3]]
        picks = st.multiselect("ZIP codes (up to 8; type a ZIP or city)", options, default=default,
                               format_func=labels.get, max_selections=8)
        if not picks:
            st.info("Pick at least one ZIP code.")
        else:
            short = {z: f"{z} {place.get(z, '')}".strip() for z in picks}
            w = ZW[picks]

            r1, r2, r3 = st.columns([2, 1, 1])
            view = r1.segmented_control("Show", ["Monthly rent", "Change from a year earlier"],
                                        default="Monthly rent", key="rent_view") or "Monthly rent"
            yoy = view != "Monthly rent"
            trend = not yoy and r2.toggle("Trend lines", value=True, key="rent_trend")
            window = r3.selectbox("Trend over", list(TREND_WINDOWS), index=0, key="rent_window", disabled=not trend,
                                  help="The arrow is a straight line fitted to the rent over these months; "
                                       "its slope is shown as dollars per year.")
            n_months = TREND_WINDOWS[window]

            fig = go.Figure()
            summary, trend_labels, recent = [], [], []
            for i, z in enumerate(picks):
                s = w[z].dropna()
                unis = unis_hover.get(z)
                listing = (f"<br><br>Universities within {radius} miles:<br>{unis}" if isinstance(unis, str)
                           else f"<br><br>No university with international students within {radius} miles")
                months = (s.index.year - s.index[0].year) * 12 + (s.index.month - s.index[0].month)
                slope, icept = fit(months, s.values)
                # The same fit over the chosen recent window only (n months back from the latest).
                k = 0 if n_months is None else max(0, len(s) - 1 - n_months)
                w_slope, w_icept = fit(months[k:], s.values[k:])
                year_ago = s.shift(12, freq="MS").reindex(s.index)
                pct = (s / year_ago - 1) * 100
                row = {"ZIP": short[z], f"Rent {s.index[-1]:%b %Y}": f"${s.iloc[-1]:,.0f}",
                       "Last 12 months": arrow(pct.iloc[-1], "{:+.1f}%"),
                       "Trend, whole period": arrow(slope * 12, "dollars")}
                if n_months is not None:
                    row[f"Trend, {window.lower()}"] = arrow(w_slope * 12, "dollars")
                row[f"Since {s.index[0]:%b %Y}"] = arrow((s.iloc[-1] / s.iloc[0] - 1) * 100, "{:+.1f}%")
                summary.append(row)
                recent.append((w_slope * 12, short[z]))
                if yoy:
                    p = pct.dropna()
                    fig.add_trace(go.Scatter(x=p.index, y=p.values, name=short[z], mode="lines",
                                             line=dict(width=2, color=series_color(i)),
                                             hovertemplate=f"<b>{short[z]}</b><br>%{{x|%b %Y}}: %{{y:+.1f}}% "
                                                           f"from a year earlier{listing}<extra></extra>"))
                    continue
                fig.add_trace(go.Scatter(x=s.index, y=s.values, name=short[z], mode="lines", legendgroup=z,
                                         line=dict(width=2, color=series_color(i)),
                                         hovertemplate=f"<b>{short[z]}</b><br>%{{x|%b %Y}}: $%{{y:,.2f}}"
                                                       f"{listing}<extra></extra>"))
                if trend:
                    if n_months is None:
                        # Whole period: the dashed fit across the chart, with the arrow on its last year.
                        fig.add_trace(go.Scatter(x=s.index, y=icept + slope * months, mode="lines", legendgroup=z,
                                                 showlegend=False,
                                                 line=dict(width=1.5, dash="dash", color=series_color(i)),
                                                 hovertemplate=f"<b>{short[z]}</b> trend: {slope * 12:+,.0f} $ per "
                                                               "year<extra></extra>"))
                        k = max(0, len(s) - 13)
                    end = w_icept + w_slope * months[-1]
                    fig.add_annotation(x=s.index[-1], y=end, ax=s.index[k], ay=w_icept + w_slope * months[k],
                                       xref="x", yref="y", axref="x", ayref="y", text="", showarrow=True,
                                       arrowhead=2, arrowsize=1.3, arrowwidth=2.5, arrowcolor=series_color(i))
                    trend_labels.append((end, s.index[-1], series_color(i),
                                         f"{'→' if abs(w_slope * 12) < FLAT else '▲' if w_slope > 0 else '▼'} "
                                         f"{'+' if w_slope >= 0 else '-'}${abs(w_slope * 12):,.0f}/yr"))
            if trend_labels:
                # Labels at the end of the trend lines, nudged apart so close ones do not overlap.
                lo, hi = w.min().min(), w.max().max()
                gap, prev = (hi - lo) * 0.06, -np.inf
                for y, x, color, text in sorted(trend_labels):
                    prev = max(y, prev + gap)
                    fig.add_annotation(x=x, y=prev, xanchor="left", xshift=8, text=text, showarrow=False,
                                       font=dict(size=12, color=color))
            if yoy:
                fig.add_hline(y=0, line=dict(color=P["muted"], width=1))
            fig.update_layout(height=460, hovermode="closest",
                              title=("Rent change from the same month a year earlier" if yoy else
                                     "Monthly rent" + (f" with trends ({window.lower()})" if trend else "")) +
                                    " (hover a line for the universities nearby)",
                              margin=dict(l=10, r=100 if trend else 10, t=40, b=70),
                              yaxis=dict(title="Change from a year earlier (%)" if yoy else "Rent ($ per month)",
                                         gridcolor=P["grid"], ticksuffix="%" if yoy else ""),
                              legend=dict(orientation="h", yanchor="top", y=-0.16, x=0))
            show(fig, "rent_lines")
            if trend:
                st.caption(trend_sentence(window, recent))
            with st.expander("Table: rent trend by ZIP"):
                st.dataframe(pd.DataFrame(summary).set_index("ZIP"), width="stretch")
                st.caption("▲ up, ▼ down. Trend: slope of a straight line fitted to the monthly rent, in dollars "
                           "per year. Last 12 months: latest month against the same month a year earlier.")

            ramp = BLUE_RAMP[3:] if MODE == "light" else BLUE_RAMP[:-2]

            one = st.selectbox("Rent by month of the year for", picks, format_func=labels.get)
            s = ZW[one].dropna()
            yrs = sorted(s.index.year.unique())
            steps = np.linspace(0, len(ramp) - 1, len(yrs)).round().astype(int)
            fig = go.Figure()
            for k, y in enumerate(yrs):
                sy = s[s.index.year == y]
                fig.add_trace(go.Scatter(x=sy.index.month, y=sy.values, name=str(y), mode="lines+markers",
                                         line=dict(width=2, color=ramp[steps[k]]), marker=dict(size=8),
                                         hovertemplate=f"{y}: $%{{y:,.2f}}<extra></extra>"))
            fig.update_layout(height=420, hovermode="x unified", title=f"{labels[one]}: one line per year",
                              margin=dict(l=10, r=10, t=40, b=10),
                              xaxis=dict(tickmode="array", tickvals=list(range(1, 13)),
                                         ticktext=["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
                                                   "Oct", "Nov", "Dec"]),
                              yaxis=dict(title="Rent ($ per month)", gridcolor=P["grid"]),
                              legend=dict(orientation="h", yanchor="top", y=-0.12, x=0))
            show(fig, "rent_season")

        with st.expander("Table: rent in every ZIP code near a campus"):
            near = zl[zl.near_campus.astype(bool)]
            same_all = ZW.loc[ZW.index.month == ZW.index.max().month, near.index]
            tbl = pd.DataFrame({"city": near.city, "state": near.state, "metro": near.metro,
                                f"universities_within_{radius}mi": unis_text.reindex(near.index),
                                f"intl_students_within_{radius}mi": near.intl_nearby.astype(int)})
            for ts, row in same_all.iterrows():
                tbl[f"rent_{ts:%b}_{ts.year}".lower()] = row
            tbl = tbl.rename_axis("zip").sort_values(f"intl_students_within_{radius}mi", ascending=False)
            st.dataframe(tbl, width="stretch")
            download(tbl, "rent_by_zip.csv")


# ================================================================= University jobs
with T["University jobs"]:
    if BLS is None:
        st.warning("Run fetch_bls_ces.py first.")
    else:
        nat = BLS[BLS.unit_type == "national"].pivot_table(index="date", columns="measure", values="value").sort_index()

        st.markdown("#### United States")
        us = {"private_colleges_employment_thousands_sa": "Private colleges and universities",
              "state_govt_education_employment_thousands_sa": "Public universities (state-government education)"}
        w = nat[[m for m in us if m in nat.columns]].rename(columns=us)
        show(line_chart(w, "University jobs, seasonally adjusted", "Jobs (thousands)"), "jobs_us")

        st.markdown("#### States")
        state_series = {"state_govt_education_employment_thousands_nsa": "Public universities (state-government education)",
                        "private_colleges_employment_thousands_nsa": "Private colleges and universities"}
        s1, s2 = st.columns([1, 2])
        sm = s1.selectbox("Universities", list(state_series), format_func=state_series.get)
        sw = to_wide(BLS, sm, "state")
        sw.columns = [STATE_FIPS.get(c, c) for c in sw.columns]
        pick = s2.multiselect("States (up to 8)", sorted(sw.columns), max_selections=8,
                              default=[s for s in HOME_STATES if s in sw.columns])
        if pick:
            show(line_chart(sw[pick], f"{state_series[sm]}, by state", "Jobs (thousands)"), "jobs_states")
        st.caption("Not seasonally adjusted: jobs dip each summer, so compare the same month across years. A state is "
                   "missing from the list when BLS does not publish that series for it.")


# ================================================================= Policy events
with T["Policy events"]:
    ev = EVENTS
    st.caption("From the policy timeline (unverified).")
    order = sorted(ev.topic.unique())
    # Two charts over the same dates with the same plot width, so a date sits at the same place
    # in both: monthly student visas issued (events as dotted lines), then the events by topic.
    x_range = [pd.Timestamp(START), pd.Timestamp(END)]
    frame = dict(margin=dict(l=190, r=20, t=50, b=10), xaxis=dict(range=x_range, showgrid=False))
    if VISA is not None:
        ev_country = st.selectbox("Visas issued to students from", list(COUNTRIES), index=1, key="ev_country")
        visas = stage_series(ev_country)[STAGES[0]].dropna()
        top = visas.max() * 1.05
        fig = go.Figure()
        by_day = ev.groupby("event_date").apply(lambda g: "<br>".join(wrap(f"• {t}: {s}") for t, s in zip(g.topic, g.title)))
        # Each event date is a faded dotted line drawn as a trace (shapes cannot be hovered), with
        # points all the way up so hovering anywhere along it shows that date's policies.
        faded = "rgba({},{},{},0.5)".format(*(int(P["muted"][i:i + 2], 16) for i in (1, 3, 5)))
        ys = np.linspace(0, top, 30)
        for day, text in by_day.items():
            fig.add_trace(go.Scatter(x=[day] * len(ys), y=ys, mode="lines", name="Policy event",
                                     line=dict(color=faded, width=1.5, dash="dot"), customdata=[text] * len(ys),
                                     hovertemplate=f"<b>{day:%d %b %Y}</b><br>%{{customdata}}<extra></extra>",
                                     hoverlabel=dict(align="left")))
        fig.add_trace(go.Bar(x=visas.index, y=visas.values, name="Visas issued", marker_color=STAGE_COLORS[STAGES[0]],
                             marker_line=dict(color=P["mid"], width=2),
                             hovertemplate="%{x|%b %Y}: %{y:,.0f} visas<extra></extra>"))
        fig.update_layout(height=380, hovermode="closest", hoverdistance=8, showlegend=False, bargap=0.15, **frame,
                          title=dict(text=f"Student visas issued per month to {ev_country} (F-1, F-2, M-1); "
                                          "dotted lines = policy events", font=dict(size=15)),
                          yaxis=dict(title="Visas per month", gridcolor=P["grid"], zeroline=False,
                                     range=[0, top], automargin=False))
        show(fig, "ev_visas")
        st.caption(f"Actual counts, {visas.index.min():%b %Y} to {visas.index.max():%b %Y} (the latest month the "
                   "State Department has posted). Visas peak each May–July before the fall term. Hover a dotted "
                   "line to see the policies announced that day; the chart below lists them by topic on the same dates.")

    fig = go.Figure()
    for topic in order:
        e = ev[ev.topic == topic]
        fig.add_trace(go.Scatter(
            x=e.event_date, y=[topic] * len(e), mode="markers", name=topic, showlegend=False,
            marker=dict(size=12, color=P["ink2"], line=dict(width=2, color=P["mid"])),
            customdata=e.title.map(wrap), hovertemplate="%{x|%d %b %Y}<br>%{customdata}<extra></extra>"))
    fig.update_layout(height=120 + 45 * len(order), hovermode="closest", **frame,
                      title=dict(text="Policy events by topic", font=dict(size=15)),
                      yaxis=dict(categoryorder="array", categoryarray=order[::-1], automargin=False,
                                 gridcolor=P["grid"]))
    show(fig, "ev_timeline")
    cnt = ev.groupby([ev.event_date.dt.to_period("Q").astype(str), "topic"]).size().rename("events").reset_index()
    fig = px.bar(cnt, x="event_date", y="events", color="topic", color_discrete_sequence=P["series"],
                 category_orders={"topic": order, "event_date": sorted(cnt.event_date.unique())},
                 labels={"event_date": "Quarter", "events": "Events", "topic": "Topic"})
    fig.update_traces(marker_line=dict(color=P["mid"], width=2))
    fig.update_layout(height=360, title="Events per quarter", margin=dict(l=10, r=10, t=40, b=10),
                      yaxis=dict(gridcolor=P["grid"]), legend=dict(orientation="h", y=-0.2))
    show(fig, "ev_count")
    with st.expander("Table: policy events"):
        st.dataframe(ev[["event_date", "topic", "title", "source", "doc_type", "url"]].sort_values("event_date"),
                     width="stretch", hide_index=True,
                     column_config={"url": st.column_config.LinkColumn("Link"),
                                    "event_date": st.column_config.DateColumn("Date")})


# ================================================================= Data & notes
with T["Data & notes"]:
    sets = {"Exposure (IPEDS)": EXP, "Rents (ZORI)": load_long("zori.csv"), "Employment (QCEW)": QCEW,
            "Monthly employment (BLS CES)": BLS, "Research funding (USAspending)": FUND,
            "Education exports (BEA)": BEA, "Visa issuances (State Department)": VISA,
            "Student arrivals (I-94)": I94, "Active students (SEVIS)": SEVIS}
    name = st.selectbox("Dataset", [k for k, v in sets.items() if v is not None])
    df = sets[name]
    f1, f2, f3 = st.columns(3)
    ut = f1.multiselect("Unit type", sorted(df.unit_type.unique()), default=sorted(df.unit_type.unique())[:1])
    ms = f2.multiselect("Measure", sorted(df[df.unit_type.isin(ut)].measure.unique()))
    q = f3.text_input("Unit name or ID contains")
    d = df[df.unit_type.isin(ut)]
    if ms:
        d = d[d.measure.isin(ms)]
    if q:
        d = d[d.unit_name.fillna("").str.contains(q, case=False) | d.unit_id.str.contains(q, case=False)]
    d = d[(d.date >= pd.Timestamp(START)) & (d.date <= pd.Timestamp(END))]
    with st.expander(f"Table: {len(d):,} rows (first 5,000 shown)"):
        st.dataframe(d.drop(columns=["date"]).head(5000), width="stretch", hide_index=True)
        download(d.drop(columns=["date"]), f"{name.split(' (')[0].lower().replace(' ', '_')}_filtered.csv")

    st.markdown("""
#### Notes and caveats
- **IPEDS** enrollment is available for fall 2022 and fall 2023 only; fall 2024 and fall 2025 are not
  published yet, so the enrollment decline itself is not visible here. Students on OPT are not counted.
- **County dependence** is international students per 1,000 residents, for each fall from 2021 to 2023
  (fall 2021 is a pre-study baseline and appears only in that chart).
- **Zillow ZORI** is a smoothed index of asking rents; small towns may have no ZIP coverage.
- **QCEW** is in the dataset browser only. BLS suppresses cells that would reveal one employer, which hides
  the university sector in many college towns.
- **Policy events** come from the unverified review list; they are marked only on the visa chart in the
  Policy events tab.
- **Visa issuances** (State Department, by nationality) count new visas, not applications, so refusals do
  not appear. They run to the latest month posted, currently February 2026.
- **I-94 arrivals** (NTTO, by country of residence; student visas = F-1, F-2, M-1, M-2, not J-1) count every
  entry, including continuing students returning from a trip home, so they run several times higher than
  visas issued and peak each August and January. Latest month: February 2026. Smaller countries
  (e.g. Nepal, Bangladesh) are not broken out.
- **SEVIS** active students (by citizenship, including OPT) are monthly from January 2023 (May, September
  and November in 2022), currently to September 2026. SEVIS counts were questioned in 2025 and some months
  look wrong (India drops to 275,009 in November 2023, then recovers), so check sudden jumps against
  visas and arrivals.
- All charts show actual values, except the rent chart's optional change-from-a-year-earlier view and
  its straight-line trends.
""")
