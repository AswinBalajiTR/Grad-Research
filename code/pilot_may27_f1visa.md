# May 27, 2025 r/f1visa search pilot

This is a **URL discovery pilot**, not a collected Reddit corpus. It used the four phrases in [`config/policies.may27.f1visa.json`](config/policies.may27.f1visa.json), with Tavily basic search, a Reddit domain filter, and May 27–June 3, 2025 as the intended post window. Tavily's dashboard showed **4 of 1,000 monthly credits used** afterward. No paid usage was enabled.

Tavily returned results from other subreddits even when the query contained `site:reddit.com/r/f1visa/comments/`. The collector now checks the subreddit in each URL itself. After that filter and deduplication, the pilot yielded these **six candidate URLs**:

| Reddit post | Initial screening from search title only |
| --- | --- |
| [Visa Appointment Freeze for F, M, and J Visas](https://www.reddit.com/r/f1visa/comments/1kx90h6/visa_appointment_freeze_for_f_m_and_j_visas_what) | Likely directly relevant |
| [Do I fill in DS-160 now during pause on consulate appointments?](https://www.reddit.com/r/f1visa/comments/1kyfizw/do_i_fill_in_ds160_now_during_pause_on_consulate) | Likely relevant; inspect post text |
| [How can I view my interview date?](https://www.reddit.com/r/f1visa/comments/1l24pgh/how_can_i_view_my_interview_date) | Unclear; inspect post text |
| [F1 Visa Interview Experience – US Embassy, Chennai](https://www.reddit.com/r/f1visa/comments/1ky0r42/f1_visa_interview_experience_us_embassy_chennai) | Likely an interview experience rather than a policy reaction |
| [Intense visa interview (Mumbai Consular)](https://www.reddit.com/r/f1visa/comments/1kz286l/intense_visa_interview_mumbai_consular) | Likely an interview experience rather than a policy reaction |
| [Chennai Consulate F1 Visa Experience](https://www.reddit.com/r/f1visa/comments/1kzuk58/chennai_consulate_f1_visa_experience) | Likely an interview experience rather than a policy reaction |

**Verification limit:** Reddit's `.json` endpoint returned a network-security block in this environment. Therefore the post creation timestamps, full post text, and comments have **not** been verified or downloaded. The table's judgments are provisional and come from Tavily titles/snippets. Search-index coverage is incomplete, so these six URLs are not a census of r/f1visa posts in the window.

The ignored raw pilot files are in [`data/raw/reddit/pilot_may27_f1visa/`](data/raw/reddit/pilot_may27_f1visa/). Once Reddit access works in a permitted environment, run the collector with this pilot policy or feed its `candidate_urls.csv` to `--candidate-file` for a verification pass.
