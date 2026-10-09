# Analysis windows

Windows are set per event. Comments are collected with the event's topic keywords in every window, and each comment is flagged when it mentions the specific policy.

## 1. Windows

- **s (earliest signal):** the first concrete public report of the specific policy: the official text, or a news report. News reports in the 60 days before a are found automatically (GDELT, confirmed by the LLM) and listed with their URL for checking.
- **a (announcement):** signing date for proclamations and executive orders, publication date for rules, release date for State Department notices.
- **Stop date:** the fixed end of the study (2026-10-01).

| Window | Start | End |
|---|---|---|
| Baseline | s − 30 days | s − 1 day |
| Anticipation | s | a − 1 day (empty when s = a) |
| Immediate | a | a + 7 days |
| Extended | a + 8 days | stop date |


## 2. Topics and keywords

| Topic | Keywords | Events |
|---|---|---|
| H-1B / work after graduation | H-1B, H1B, lottery, cap, work visa, prevailing wage, grace period, OPT to H-1B | $100k H-1B proclamation and its extension, weighted lottery, prevailing wage rule, H-1B petition fee, grace period, H-1B program integrity order |
| Visa interviews | visa interview, slot, appointment, dropbox, interview waiver, consulate, third country, VFS | interview waiver updates, country of nationality or residence rule |
| Vetting and social media | social media, public profile, vetting, online presence, 221(g) | expanded screening and vetting for students (June 2025), for H-1B (Dec 2025), and for other categories (Mar 2026) |
| Student status | duration of status, D/S, I-20, SEVIS, status, grace period | duration of status rule (proposed and final), J-1 program termination rule |
| Travel and entry bans | travel ban, proclamation, entry ban, names of listed countries | travel ban (June 2025) and its expansion (Dec 2025) |
| Universities | Harvard, SEVP certification, transfer | Harvard proclamation, Harvard exchange visitor investigation |
| Visa revocations | visa revoked, revocation, deport | revocation of Chinese student visas |
