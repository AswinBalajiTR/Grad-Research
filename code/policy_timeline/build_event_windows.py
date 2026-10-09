"""Analysis windows (proposal/analysis_windows.md) for each policy in the list.
Usage:
    python build_event_windows.py --stop 2026-10-01
"""

import argparse
import csv
import re
from datetime import date, datetime, timedelta
from pathlib import Path

BASELINE_DAYS = 30
IMMEDIATE_DAYS = 7

# Checked in order; the first matching title pattern sets the topic.
TOPICS = [
    ("Vetting and social media", r"screening and vetting|social media|vetting",
     "social media, public profile, vetting, online presence, 221(g)"),
    ("H-1B / work after graduation", r"h-1b|nonimmigrant workers|wage protections|grace period",
     "H-1B, H1B, lottery, cap, work visa, prevailing wage, grace period, OPT to H-1B"),
    ("Travel and entry bans", r"entry of foreign nationals|suspension of visa issuance",
     "travel ban, proclamation, entry ban, names of listed countries"),
    ("Universities", r"harvard|universit",
     "Harvard, SEVP certification, transfer"),
    ("Visa interviews", r"interview|country of (?:nationality or )?residence",
     "visa interview, slot, appointment, dropbox, interview waiver, consulate, third country, VFS"),
    ("Student status", r"duration of status|fixed time period of admission|exchange visitor program|sevis",
     "duration of status, D/S, I-20, SEVIS, status, grace period"),
    ("Visa revocations", r"revok|revocation|america first, not china",
     "visa revoked, revocation, deport"),
]
KEYWORDS = {name: keywords for name, _, keywords in TOPICS}  # for the comment extraction step

# Columns of the list to verify (written by build_review_list.py).
LIST_COLUMNS = [
    "event_date", "source", "doc_type", "title", "topic", "india_relevance",
    "why_listed", "llm_reason", "verified", "notes", "earliest_signal", "signal_source",
    # analysis windows; event_date is the announcement
    "baseline_start", "baseline_end", "anticipation_start", "anticipation_end",
    "immediate_start", "immediate_end", "extended_start", "extended_end",
    "url", "source_id",
]
# Columns written by earlier versions of the pipeline; dropped when the list is rewritten.
OBSOLETE_COLUMNS = {"date_basis", "group", "related", "keywords", "effective_on", "comments_close_on", "archived_url"}


def to_date(value):
    """Accept ISO dates and the M/D/YYYY format Excel writes when it saves."""
    value = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def topic_of(title):
    for name, pattern, _ in TOPICS:
        if re.search(pattern, title, re.I):
            return name
    return ""  # no match: assign by hand


def window_columns(r, stop):
    """Topic and the four windows for one policy. s is
    `earliest_signal` when filled in (and earlier than a), else a."""
    one = timedelta(days=1)
    a = to_date(r["event_date"])
    s = min(to_date(r.get("earliest_signal")) or a, a)
    topic = (r.get("topic") or "").strip() or topic_of(r["title"])
    extended_start = a + timedelta(days=IMMEDIATE_DAYS + 1)
    has_extended = extended_start <= stop
    iso = lambda d: d.isoformat() if d else ""
    return {
        "topic": topic,
        "baseline_start": iso(s - timedelta(days=BASELINE_DAYS)), "baseline_end": iso(s - one),
        "anticipation_start": iso(s if s < a else None), "anticipation_end": iso(a - one if s < a else None),
        "immediate_start": iso(a), "immediate_end": iso(a + timedelta(days=IMMEDIATE_DAYS)),
        "extended_start": iso(extended_start if has_extended else None),
        "extended_end": iso(stop if has_extended else None),
    }


def recompute_windows(path, stop):
    """Recompute the window dates in the list at `path`, in place, from its
    current event_date, earliest_signal, and topic. Other values are kept."""
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        found, rows = list(reader.fieldnames), list(reader)
    # The list's columns in order, plus any column added by hand.
    columns = LIST_COLUMNS + [c for c in found if c not in LIST_COLUMNS and c not in OBSOLETE_COLUMNS]
    for r in rows:
        r.update(window_columns(r, stop))
    with path.open("w", newline="", encoding="utf-8-sig") as f:  # -sig so Excel reads UTF-8
        w = csv.DictWriter(f, fieldnames=columns, restval="", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    untopiced = sum(not r["topic"] for r in rows)
    print(f"window dates updated for {len(rows)} policies in {path}"
          + (f" ({untopiced} with no topic; fill in `topic` and rerun)" if untopiced else ""))


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", default=str(root / "data" / "processed" / "policy_events_to_verify.csv"))
    parser.add_argument("--stop", default="2026-10-01", help="stop date (YYYY-MM-DD)")
    args = parser.parse_args()
    recompute_windows(args.list, date.fromisoformat(args.stop))


if __name__ == "__main__":
    main()
