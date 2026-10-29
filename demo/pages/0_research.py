"""Research question page: the project framing from the proposal
(proposal/Proposal_initial_draft.docx), with work beyond the proposal marked as extended.
Run: streamlit run demo/app.py
"""

import streamlit as st

st.markdown("""
<style>
  .block-container {padding-top: 3.5rem; max-width: 1150px;}
  .kicker {letter-spacing: .08em; text-transform: uppercase; font-size: .78rem; opacity: .65; margin: 1.6rem 0 -.6rem;}
  .question {font-size: 1.35rem; line-height: 1.5; border-left: 4px solid #2a78d6; padding: .6rem 1.1rem;
             background: rgba(42,120,214,.07); border-radius: 0 8px 8px 0; margin: .4rem 0 1.2rem;}
  .tag {display: inline-block; font-size: .72rem; letter-spacing: .06em; text-transform: uppercase;
        padding: .1rem .5rem; border-radius: 999px; background: rgba(235,104,52,.15); color: #c4501f;
        margin-left: .4rem; vertical-align: middle;}
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="kicker">International Student Policy and Economic Indicators</p>', unsafe_allow_html=True)
st.title("Research question", help="From the project proposal. The proposal is an initial framework: questions, "
                                   "data sources, policy events, and methods may change with data availability "
                                   "and exploratory findings.")

st.markdown('<div class="question">How have recent U.S. policy changes affecting international students altered '
            "the topics, concerns, and educational intentions expressed in online discussions, particularly among "
            "<b>Indian students</b>?</div>", unsafe_allow_html=True)

st.subheader("Questions we may answer", help="Subject to change, as in the proposal.")
st.markdown("""
- Which concerns become more prominent around major policy announcements?
- How do online narratives change before and after specific policy events?
- Do students increasingly discuss delaying study, reconsidering the U.S., or choosing other destinations?
- Do changes in online discourse correspond with trends in enrollment or visa activity?
- Do these patterns differ for Indian students compared with international students overall?
""")

# Supporting detail stays closed until the viewer opens it.
details = st.expander("Policy areas, approach, data, and extensions")
policy_tab, approach_tab, data_tab, extended_tab = details.tabs(["Policy areas", "Approach", "Data", "Extended"])

with policy_tab:
    st.markdown("""
- Student visa restrictions
- Travel and entry restrictions
- Duration of stay (D/S)
- Visa processing and screening (social-media vetting, fewer appointments)
- CPT, OPT, STEM OPT, and H-1B
""")
    st.caption("Scope: U.S. policy developments affecting international students during 2025–2026.")

with approach_tab:
    st.markdown("""
- **Policy timeline** of major announcements, then online discussion collected around each event.
- **What students discuss**, not only whether it is positive or negative: visa uncertainty, travel and entry,
  OPT and jobs, finances and careers, long-term stability, other destinations, and plans to continue, delay,
  or reconsider.
- **Mobility as a second layer:** check whether rising concerns occur alongside or before changes in
  enrollment and student flows, allowing for time lags. Associations, not causal effects.
""")
    st.caption("Methods may include keyword analysis, topic discovery, text embeddings, clustering, sentiment or "
               "emotion analysis, and classification of concerns and intentions. Each policy event is analyzed in "
               "four windows: baseline (30 days before the first report), anticipation (first report to "
               "announcement), immediate (announcement + 7 days), and extended (to the study's end, 1 Oct 2026).")

with data_tab:
    st.markdown("""
| Proposal data | Sources | Dashboard page |
|---|---|---|
| Policy data | Proclamations, rules, State Department notices | Economy & policy › Policy events |
| Online discourse | Reddit | Reddit |
| Mobility | University enrollment reports; State Department visas, I-94 arrivals, SEVIS | Enrollment; Economy & policy › Student flows |
| Post-study work | H-1B data | H-1B |
| Economic indicators | IPEDS and Census, Zillow ZORI, BLS | Economy & policy |
""")

with extended_tab:
    st.markdown('Work beyond the original proposal <span class="tag">Extended</span>', unsafe_allow_html=True)
    st.markdown("""
- **Longer enrollment history:** campus counts from Fall 2011, so Fall 2025 can be judged against earlier
  years rather than 2025–2026 alone.
- **Pre-policy baseline for indicators:** visas, arrivals, rents, and jobs from 2022; county dependence
  from Fall 2021.
- **Recent-trend view of rents:** rent direction over a chosen recent window (3 to 24 months) alongside
  the whole-period trend.
""")
