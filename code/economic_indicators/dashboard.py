"""Dashboard of the economic indicators since 2022: international enrollment,
student visas, arrivals and SEVIS counts, rents near campus, and university
employment, with the policy events, all as actual values.

Run the build and fetch scripts first, then:
    streamlit run code/economic_indicators/dashboard.py
"""

from datetime import date

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from common import OUT, ROOT, STOP_DATE

st.set_page_config(page_title="International students and local economies", page_icon="📈", layout="wide")

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
START, END = date(2022, 1, 1), date.fromisoformat(STOP_DATE)  # every chart covers the whole study period


# ---------------------------------------------------------------- data
@st.cache_data(show_spinner="Loading data")
def load_long(name):
    path = OUT / name
    if not path.exists():
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
def load_table(name, **kw):
    path = OUT / name
    return pd.read_csv(path, encoding="utf-8-sig", **kw) if path.exists() else None


@st.cache_data
def load_events():
    path = ROOT / "data" / "processed" / "policy_events_to_verify.csv"
    if not path.exists():
        return pd.DataFrame(columns=["event_date", "title", "topic"])
    ev = pd.read_csv(path, encoding="utf-8-sig")
    ev["event_date"] = pd.to_datetime(ev["event_date"], errors="coerce")
    ev["topic"] = ev["topic"].fillna("Other / unassigned")
    return ev.dropna(subset=["event_date"])


@st.cache_data(show_spinner="Preparing rents")
def zori_wide():
    z = load_long("zori.csv")
    if z is None:
        return None
    return z.pivot_table(index="date", columns="unit_id", values="value").sort_index()


@st.cache_data
def zip_exposure():
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
def institutions():
    inst = load_table("institutions.csv", dtype={"unitid": str, "sector": str, "county_fips": str, "cbsa": str})
    if inst is None:
        return None
    inst["sector_name"] = inst["sector"].map(SECTORS).fillna("Other")
    return inst


@st.cache_data
def institution_years():
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


def show(fig, key=None):
    st.plotly_chart(fig, width="stretch", theme="streamlit", key=key)


def download(df, name, label="Download CSV"):
    st.download_button(label, df.to_csv(index=True).encode("utf-8"), file_name=name, mime="text/csv",
                       key=f"dl_{name}")


EVENTS = load_events()

st.title("International students and local economies, 2022 onward")
st.caption(f"Actual values since 2022 for enrollment, student visas and arrivals, rents, and university jobs. "
           f"Study period ends {STOP_DATE}. Each source runs to its latest release (see Data & notes).")

TAB_NAMES = ["International students", "Student flows", "Rents near campus", "University jobs", "Policy events",
             "Data & notes"]
T = dict(zip(TAB_NAMES, st.tabs(TAB_NAMES)))

ZW = zori_wide()
ZIPS = zip_exposure()
INST = institutions()
IYEARS = institution_years()
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
VISA_CLASSES = {"f1_issuances": "F-1 students", "j1_issuances": "J-1 exchange visitors",
                "h1b_issuances": "H-1B workers", "b1_b2_issuances": "B1/B2 business and tourism"}


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


def stage_panels(raw):
    """One panel per stage, stacked on a shared time axis, each on its own scale (the stages
    differ by two orders of magnitude)."""
    stages = [s for s in STAGES if s in raw]
    fig = make_subplots(rows=len(stages), cols=1, shared_xaxes=True, vertical_spacing=0.05, subplot_titles=stages)
    for k, s in enumerate(stages, 1):
        v = raw[s].dropna()
        fig.add_trace(go.Scatter(x=v.index, y=v.values, name=s, mode="lines+markers", showlegend=False,
                                 line=dict(width=2, color=STAGE_COLORS[s]), marker=dict(size=4),
                                 hovertemplate="%{y:,.0f}"), row=k, col=1)
        fig.update_yaxes(title_text="Students" if s == STAGES[2] else "Per month", gridcolor=P["grid"],
                         zeroline=False, rangemode="tozero", row=k, col=1)
    fig.update_xaxes(showgrid=False)
    fig.update_annotations(font=dict(size=13, color=P["ink2"]), xanchor="left", x=0)
    return fig, len(stages)


def county_exposure():
    c = EXP[(EXP.unit_type == "county") & (EXP.measure == "intl_per_1000_residents")]
    c = c[c.period == c.period.max()]
    return c.set_index("unit_id")["value"], dict(zip(c.unit_id, c.unit_name))


# ================================================================= International students
with T["International students"]:
    if IYEARS is None or INST is None:
        st.warning("Run build_exposure.py first.")
    else:
        years = sorted(IYEARS.year.unique())
        y0, y1 = years[0], years[-1]
        wide = IYEARS.pivot_table(index="unit_id", columns="year",
                                  values=["intl_enrollment", "enrollment", "intl_share", "grad_intl_enrollment",
                                          "undergrad_intl_enrollment"])
        df = INST.set_index("unitid").join(pd.DataFrame({
            "intl_first": wide[("intl_enrollment", y0)], "intl_last": wide[("intl_enrollment", y1)],
            "share_last": wide[("intl_share", y1)] * 100, "grad_last": wide[("grad_intl_enrollment", y1)],
            "ug_last": wide[("undergrad_intl_enrollment", y1)], "enroll_last": wide[("enrollment", y1)],
        }), how="inner")

        with st.expander("Filters"):
            f1, f2 = st.columns(2)
            sectors = f1.multiselect("Sector", sorted(df.sector_name.unique()), default=sorted(df.sector_name.unique()))
            states = f2.multiselect("States (empty = all)", sorted(df.state.dropna().unique()))
        d = df[df.sector_name.isin(sectors)]
        if states:
            d = d[d.state.isin(states)]

        st.markdown("#### Where international students are")
        g = d.dropna(subset=["latitude", "longitude"])
        g = g[g.intl_last > 0]  # a campus with none has no bubble to draw
        fig = px.scatter_geo(g, lat="latitude", lon="longitude", size="intl_last", color="share_last",
                             scope="usa", hover_name="name", size_max=35, color_continuous_scale=SEQUENTIAL,
                             hover_data={"intl_last": True, "enroll_last": True, "share_last": ":.1f",
                                         "latitude": False, "longitude": False},
                             labels={"intl_last": f"Intl students (fall {y1})", "enroll_last": "All students",
                                     "share_last": "Intl share %"})
        fig.update_traces(marker=dict(line=dict(width=0.5, color=P["mid"])))
        fig.update_layout(height=520, margin=dict(l=0, r=0, t=40, b=0), geo=dict(bgcolor="rgba(0,0,0,0)"),
                          title=f"Campuses sized by international students, colored by their share of enrollment (fall {y1})")
        show(fig, "map_inst")

        top_n = st.slider("Institutions and counties to show", 5, 30, 15)
        top = d.sort_values("intl_last", ascending=False).head(top_n)[::-1]
        fig = go.Figure()
        for i, (c, name) in enumerate([("grad_last", "Graduate"), ("ug_last", "Undergraduate")]):
            fig.add_trace(go.Bar(y=top.name, x=top[c], name=name, orientation="h", marker_color=series_color(i),
                                 marker_line=dict(color=P["mid"], width=2), text=top[c].astype(int),
                                 textposition="inside", insidetextanchor="middle", hovertemplate="%{x}"))
        fig.add_trace(go.Scatter(y=top.name, x=top.intl_last, mode="text", text=top.intl_last.astype(int),
                                 textposition="middle right", showlegend=False, hoverinfo="skip",
                                 textfont=dict(color=P["ink2"])))
        fig.update_layout(barmode="stack", height=max(400, 26 * len(top) + 140), hovermode="y unified",
                          margin=dict(l=10, r=10, t=40, b=10), title=f"Largest hosts (fall {y1})",
                          xaxis=dict(title="International students",
                                     gridcolor=P["grid"], range=[0, top.intl_last.max() * 1.15]),
                          legend=dict(orientation="h", y=-0.1))
        show(fig, "inst_bar")
        cexp, cnames = county_exposure()
        ctop = cexp.sort_values(ascending=False).head(top_n).rename("per_1000").to_frame()
        ctop["county"] = [cnames.get(i, i) for i in ctop.index]
        county_intl = EXP[(EXP.unit_type == "county") & (EXP.measure == "intl_enrollment")
                          & (EXP.period == f"{y1}-fall")].set_index("unit_id")["value"]
        ctop["intl"] = county_intl.reindex(ctop.index).astype(int)
        fig = px.bar(ctop[::-1], x="per_1000", y="county", orientation="h", text="per_1000",
                     color_discrete_sequence=[series_color(0)], custom_data=["intl"],
                     labels={"per_1000": "International students per 1,000 residents", "county": ""})
        fig.update_traces(marker_line=dict(color=P["mid"], width=2), textposition="outside", cliponaxis=False,
                          texttemplate="%{x:.1f}",
                          hovertemplate="%{y}<br>%{x:.1f} per 1,000 residents<br>%{customdata[0]} international "
                                        "students<extra></extra>")
        fig.update_layout(height=max(400, 26 * len(ctop) + 140), margin=dict(l=10, r=10, t=40, b=10),
                          title=f"Most dependent counties (fall {y1})",
                          xaxis=dict(gridcolor=P["grid"], range=[0, ctop.per_1000.max() * 1.2]))
        show(fig, "county_bar")

        with st.expander("Table"):
            cols = ["name", "state", "sector_name", "enroll_last", "intl_first", "intl_last", "share_last",
                    "grad_last", "ug_last", "county_name"]
            st.dataframe(d[cols].sort_values("intl_last", ascending=False), width="stretch",
                         column_config={"share_last": st.column_config.NumberColumn("Intl share %", format="%.1f")})
            download(d[cols].assign(share_last=d.share_last.round(1)), "institutions_filtered.csv")


# ================================================================= Student flows
with T["Student flows"]:
    if VISA is None or SEVIS is None:
        st.warning("Run fetch_visa_issuances.py, fetch_i94_arrivals.py and fetch_sevis.py first.")
    else:
        country = st.selectbox("Country", list(COUNTRIES), index=1, key="flow_country")
        raw = stage_series(country)

        st.markdown("#### Visa issued → arrival → enrolled")
        fig, n = stage_panels(raw)
        fig.update_layout(height=220 * n + 80, hovermode="x unified", margin=dict(l=10, r=10, t=70, b=10),
                          title=dict(text=f"{country}: students at each stage, by month", font=dict(size=15)))
        show(fig, "flow_funnel")

        st.markdown("#### Visas issued by class")
        cw = class_series(country)
        names = [m for m in VISA_CLASSES if m in cw]
        fig = make_subplots(rows=2, cols=2, shared_xaxes=True, vertical_spacing=0.12, horizontal_spacing=0.08,
                            subplot_titles=[VISA_CLASSES[m] for m in names])
        for k, m in enumerate(names):
            s = cw[m].dropna()
            fig.add_trace(go.Scatter(x=s.index, y=s.values, name=VISA_CLASSES[m], mode="lines+markers",
                                     showlegend=False, line=dict(width=2, color=series_color(0)),
                                     marker=dict(size=4), hovertemplate="%{y:,.0f}"),
                          row=k // 2 + 1, col=k % 2 + 1)
        fig.update_yaxes(gridcolor=P["grid"], zeroline=False, rangemode="tozero")
        fig.update_yaxes(title_text="Visas per month", col=1)
        fig.update_xaxes(showgrid=False)
        fig.update_annotations(font=dict(size=13, color=P["ink2"]))
        fig.update_layout(height=560, hovermode="x unified", margin=dict(l=10, r=10, t=70, b=10),
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
        default = [z for z in ["48104", "61820", "14850", "16801", "47906", "02138"] if z in labels]
        picks = st.multiselect("ZIP codes (up to 8; type a ZIP or city)", options, default=default,
                               format_func=labels.get, max_selections=8)
        if not picks:
            st.info("Pick at least one ZIP code.")
        else:
            short = {z: f"{z} {place.get(z, '')}".strip() for z in picks}
            w = ZW[picks]

            fig = go.Figure()
            for i, z in enumerate(picks):
                s = w[z].dropna()
                unis = unis_hover.get(z)
                listing = (f"<br><br>Universities within {radius} miles:<br>{unis}" if isinstance(unis, str)
                           else f"<br><br>No university with international students within {radius} miles")
                fig.add_trace(go.Scatter(x=s.index, y=s.values, name=short[z], mode="lines",
                                         line=dict(width=2, color=series_color(i)),
                                         hovertemplate=f"<b>{short[z]}</b><br>%{{x|%b %Y}}: $%{{y:,.2f}}"
                                                       f"{listing}<extra></extra>"))
            fig.update_layout(height=460, hovermode="closest", title="Monthly rent (hover a line for the "
                                                                    "universities nearby)",
                              margin=dict(l=10, r=10, t=40, b=70), yaxis=dict(title="Rent ($ per month)",
                                                                              gridcolor=P["grid"]),
                              legend=dict(orientation="h", yanchor="top", y=-0.16, x=0))
            show(fig, "rent_lines")

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
        top_states = (INST.groupby("state").intl_enrollment.sum().sort_values(ascending=False).index.tolist()
                      if INST is not None else [])
        pick = s2.multiselect("States (up to 8)", sorted(sw.columns), max_selections=8,
                              default=[s for s in top_states if s in sw.columns][:6])
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
        by_day = ev.groupby("event_date").apply(lambda g: "<br>".join(f"• {t}: {s[:80]}" for t, s in zip(g.topic, g.title)))
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
            customdata=e.title.str.slice(0, 90), hovertemplate="%{x|%d %b %Y}<br>%{customdata}<extra></extra>"))
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
    st.caption(f"{len(d):,} rows (first 5,000 shown)")
    st.dataframe(d.drop(columns=["date"]).head(5000), width="stretch", hide_index=True)
    download(d.drop(columns=["date"]), f"{name.split(' (')[0].lower().replace(' ', '_')}_filtered.csv")

    st.markdown("""
#### Notes and caveats
- **IPEDS** enrollment is available for fall 2022 and fall 2023 only; fall 2024 and fall 2025 are not
  published yet, so the enrollment decline itself is not visible here. Students on OPT are not counted.
- **County dependence** uses fall 2023: international students per 1,000 residents.
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
- All charts show actual values; none is indexed or compared with a baseline.
""")
