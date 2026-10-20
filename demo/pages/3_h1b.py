"""H-1B filing analysis adapted from Aswin's dashboard."""
from __future__ import annotations
import plotly.express as px
import pandas as pd
import streamlit as st
from dashboard_common import H1B_PATH, load_data, run_collector, find_col, compact_number, annualized_wage

st.title("H-1B filings")
st.caption("Employer filings · 2025 onward")
with st.sidebar:
    refresh = st.button("Refresh H-1B data", use_container_width=True)
    st.caption("Manual refresh · may take minutes")
if refresh:
    with st.spinner("Downloading and preparing H-1B disclosures..."):
        ok, message = run_collector(["code/h1b/collect_h1b.py", "--source", "dol"], timeout=7200)
    (st.success if ok else st.error)("H-1B refresh completed" if ok else "H-1B refresh failed")
    if message:
        st.code(message)
h1b = load_data(H1B_PATH)
if h1b.empty:
    st.warning("No H-1B data are loaded.")
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
        earliest_decision = view[decision_col].min()
        if pd.notna(earliest_decision) and earliest_decision > pd.Timestamp("2025-01-31"):
            st.warning(
                f"Current H-1B file begins {earliest_decision.date()}. Click Refresh H-1B data to add the corrected FY2025 Q2 and Q3 files."
            )

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
        certification_rate = status_upper.str.contains("CERTIFIED").sum() / decided.sum() if decided.sum() else 0
        m4.metric("Certification share", f"{certification_rate:.1%}")
    else:
        m4.metric("Filtered rows", compact_number(len(view)))
    annual_wages = annualized_wage(view)
    plausible_wages = annual_wages.loc[annual_wages.between(10_000, 2_000_000)]
    m5.metric("Median wage", f"${plausible_wages.median():,.0f}" if len(plausible_wages) else "n.a.")

    chart_tabs = st.tabs(["Filings", "Outcomes", "States", "Occupations", "Wages"])

    if decision_col:
        monthly = (
            view.dropna(subset=[decision_col])
            .assign(month=lambda data: data[decision_col].dt.to_period("M").dt.to_timestamp(), _filings=weights)
            .groupby("month", as_index=False)["_filings"]
            .sum()
        )
        with chart_tabs[0]:
            st.caption("Monthly LCA decisions · not student hires")
            st.plotly_chart(
                px.line(monthly, x="month", y="_filings", markers=True, labels={"_filings": "Filings"}),
                use_container_width=True,
            )

    if decision_col and status_col:
        status_values = view[status_col].fillna("").astype(str).str.upper()
        status_group = pd.Series("Other", index=view.index)
        status_group.loc[status_values.str.contains("CERTIFIED")] = "Certified"
        status_group.loc[status_values.str.contains("DENIED")] = "Denied"
        status_group.loc[status_values.str.contains("WITHDRAWN") & ~status_values.str.contains("CERTIFIED")] = "Withdrawn"
        outcome_month = (
            view.assign(
                month=view[decision_col].dt.to_period("M").dt.to_timestamp(),
                outcome=status_group,
                _filings=weights,
            )
            .dropna(subset=["month"])
            .groupby(["month", "outcome"], as_index=False)["_filings"]
            .sum()
        )
        outcome_month["share"] = outcome_month["_filings"] / outcome_month.groupby("month")["_filings"].transform("sum")
        with chart_tabs[1]:
            st.caption("Certified · denied · withdrawn")
            st.plotly_chart(
                px.area(
                    outcome_month,
                    x="month",
                    y="share",
                    color="outcome",
                    groupnorm=None,
                    range_y=[0, 1],
                    color_discrete_map={"Certified": "#238B45", "Denied": "#C0392B", "Withdrawn": "#D4A017", "Other": "#7F8C8D"},
                    labels={"share": "Share of monthly filings"},
                ),
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
        with chart_tabs[2]:
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
        with chart_tabs[3]:
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
        with chart_tabs[4]:
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
