"""H-1B filing analysis adapted from Aswin's dashboard."""
from __future__ import annotations
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import streamlit as st
from dashboard_common import DATA_ROOT, H1B_PATH, load_data, find_col, compact_number, annualized_wage
from h1b_refresh import refresh_manager

POLICY_EVENTS_PATH = DATA_ROOT / "policy_timeline/policy_events_to_verify.csv"

st.title("H-1B filings")
st.caption("Employer filings · 2025 onward")
manager = refresh_manager()
manager.ensure_started()
loaded_mtime = H1B_PATH.stat().st_mtime_ns if H1B_PATH.exists() else None


@st.fragment(run_every="30s")
def refresh_notice() -> None:
    manager.ensure_started()
    if H1B_PATH.exists() and H1B_PATH.stat().st_mtime_ns != loaded_mtime:
        st.rerun(scope="app")
    running, error = manager.status()
    if running and loaded_mtime is None:
        st.info("Preparing the latest DOL H-1B data automatically. This first download may take a few minutes.")
    elif error and loaded_mtime is None:
        st.warning("The DOL download is temporarily unavailable. The app will try again automatically.")


refresh_notice()
h1b = load_data(H1B_PATH)
if h1b.empty:
    if not manager.status()[1]:
        st.info("H-1B data will appear here when the first download finishes.")
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

    with st.expander("Filters"):
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
        certification_rate = status_upper.eq("CERTIFIED").sum() / decided.sum() if decided.sum() else 0
        m4.metric("Certified LCA share", f"{certification_rate:.1%}")
    else:
        m4.metric("Filtered rows", compact_number(len(view)))
    annual_wages = annualized_wage(view)
    plausible_wages = annual_wages.loc[annual_wages.between(10_000, 2_000_000)]
    m5.metric("Median wage", f"${plausible_wages.median():,.0f}" if len(plausible_wages) else "n.a.")
    if status_col and not (approval_col and denial_col):
        st.caption("Certified LCA share excludes withdrawn cases. A DOL certification is not a USCIS H-1B petition or visa approval.")

    chart_tabs = st.tabs(["Filings", "States", "Occupations", "Wages"])

    if decision_col:
        monthly = (
            view.dropna(subset=[decision_col])
            .assign(month=lambda data: data[decision_col].dt.to_period("M").dt.to_timestamp(), _filings=weights)
            .groupby("month", as_index=False)["_filings"]
            .sum()
        )
        with chart_tabs[0]:
            st.caption("Monthly LCA decisions · dashed lines mark all policy timeline events (unverified)")
            fig = px.line(monthly, x="month", y="_filings", markers=True, labels={"_filings": "Filings"})
            if POLICY_EVENTS_PATH.exists() and not monthly.empty:
                events = pd.read_csv(POLICY_EVENTS_PATH, encoding="utf-8-sig")
                events["event_date"] = pd.to_datetime(events["event_date"], errors="coerce")
                events = events.dropna(subset=["event_date"])
                top = max(float(monthly["_filings"].max()) * 1.05, 1)
                for day, day_events in events.groupby("event_date"):
                    titles = "<br>".join(
                        f"{row.topic if pd.notna(row.topic) else 'Other / unassigned'}: {row.title if pd.notna(row.title) else 'Policy event'}"
                        for row in day_events.itertuples()
                    )
                    fig.add_trace(go.Scatter(
                        x=[day] * 25,
                        y=[top * step / 24 for step in range(25)],
                        mode="lines",
                        name="Policy event",
                        showlegend=False,
                        line=dict(color="rgba(255, 184, 46, 0.75)", width=1.5, dash="dash"),
                        hovertemplate=f"<b>{day:%d %b %Y}</b><br>{titles}<extra></extra>",
                    ))
                fig.update_yaxes(range=[0, top])
                if not events.empty:
                    fig.update_xaxes(range=[
                        min(pd.Timestamp(monthly["month"].min()), pd.Timestamp(events["event_date"].min())),
                        max(
                            pd.Timestamp(monthly["month"].max()) + pd.offsets.MonthEnd(1),
                            pd.Timestamp(events["event_date"].max()) + pd.Timedelta(days=7),
                        ),
                    ])
            st.plotly_chart(
                fig,
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
        with chart_tabs[1]:
            st.caption(f"Top five states · {top_five_share:.1%} of filings")
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
        with chart_tabs[2]:
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
        with chart_tabs[3]:
            st.caption("Dots = median wage · lines = middle 50%")
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

    with st.expander("H-1B records"):
        st.dataframe(view.head(10000), hide_index=True, use_container_width=True)
        st.download_button(
            "Download filtered CSV",
            view.to_csv(index=False).encode("utf-8"),
            file_name="h1b_filtered.csv",
            mime="text/csv",
        )
