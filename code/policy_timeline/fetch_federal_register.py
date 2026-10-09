"""Collect and screen Federal Register documents that may affect international students.
API docs: https://www.federalregister.gov/developers/documentation/api/v1
"""

import re
import time

import requests

FR_API = "https://www.federalregister.gov/api/v1/documents.json"

# Agencies whose rules touch student visas, status, or work authorization.
FR_AGENCIES = [
    "homeland-security-department",
    "u-s-citizenship-and-immigration-services",
    "u-s-immigration-and-customs-enforcement",
    "state-department",
    "labor-department",
]
# Each term is searched separately; results are merged and de-duplicated.
FR_SEARCH_TERMS = ["nonimmigrant student", "F-1", "J-1 exchange visitor", "duration of status",
                   "optional practical training", "H-1B", "student and exchange visitor", "visa"]
# Presidential documents (EOs, proclamations) are searched with broader terms.
FR_PRESIDENTIAL_TERMS = ["visa", "entry of aliens", "foreign students", "H-1B", "vetting", "Harvard"]
# Regulations that govern students and their work pathways, as (title, part).
FR_CFR_PARTS = [
    (8, 214),   # nonimmigrant classes: F-1, J-1, OPT, H-1B
    (8, 274),   # employment authorization (274a)
    (22, 41),   # State Dept nonimmigrant visas
    (22, 62),   # J exchange visitor program
    (20, 655),  # DOL labor conditions for H-1B
]
FR_FIELDS = ["document_number", "title", "type", "subtype", "abstract", "publication_date", "signing_date",
             "html_url", "raw_text_url"]

# A document must mention immigration in its title/abstract (or be a presidential
# document) before its full text is downloaded.
IMMIGRATION_HINT = re.compile(r"alien|visa|nonimmigrant|immigra|entry|student|universit|h-1b|"
                              r"employment authorization|foreign national|exchange visitor", re.I)

# Full-text patterns counted for each document (Federal Register and State Department).
PATTERNS = {
    "student_hits": r"\bstudents?\b",
    # Avoids bare "(f)"/"(j)", which are usually paragraph markers.
    "fj_visa_hits": r"\b[fjm]-1\b|\b[fj] visas?\b|\bf, m,? (?:and|or) j\b|\bf (?:and|or) j\b|"
                    r"\b[fjm] (?:nonimmigrants?|classifications?|status)\b",
    "opt_sevis_hits": r"practical training|\bsevis\b|\bsevp\b|duration of status|exchange visitor",
    "h1b_hits": r"\bh-1b\b",
    # "entry" is left out because customs rules use it for merchandise.
    "visa_entry_hits": r"\bvisas?\b|\bnonimmigrants?\b",
}


def fr_get(url, params=None, retries=5):
    """GET with backoff when the API rate-limits us (HTTP 429)."""
    for attempt in range(retries):
        resp = requests.get(url, params=params, timeout=120)
        if resp.status_code != 429:
            resp.raise_for_status()
            return resp
        wait = int(resp.headers.get("Retry-After", 10 * 2 ** attempt))
        print(f"  rate limited; waiting {wait}s")
        time.sleep(wait)
    resp.raise_for_status()


def fr_search(start, end, doc_types, term=None, agencies=None, cfr=None):
    """Return all documents matching one query, following pagination."""
    params = {
        "conditions[publication_date][gte]": start,
        "conditions[publication_date][lte]": end,
        "conditions[type][]": doc_types,
        "fields[]": FR_FIELDS,
        "per_page": 100,
        "order": "oldest",
    }
    if term:
        params["conditions[term]"] = term
    if agencies:
        params["conditions[agencies][]"] = agencies
    if cfr:
        params["conditions[cfr][title]"], params["conditions[cfr][part]"] = cfr
    results, page = [], 1
    while True:
        params["page"] = page
        data = fr_get(FR_API, params).json()
        results.extend(data.get("results", []))
        if page >= data.get("total_pages", 0):
            break
        page += 1
        time.sleep(0.5)  # be polite to the API
    return results


def fr_screen(doc):
    """Return (tier, reason, counts, full text). Tier is core, context, or
    exclude. The full text is downloaded only for plausible documents."""
    title = doc.get("title") or ""
    counts = dict.fromkeys(PATTERNS, 0)
    if doc["document_number"].startswith("C") or "; Correction" in title:
        return "exclude", "correction to another document", counts, ""
    if doc.get("type") != "Presidential Document" and not IMMIGRATION_HINT.search(f"{title} {doc.get('abstract') or ''}"):
        return "exclude", "no immigration terms in title/abstract", counts, ""
    text = ""
    if doc.get("raw_text_url"):
        text = fr_get(doc["raw_text_url"]).text
        time.sleep(1)  # be polite to the API
    lower = text.lower()
    counts = {k: len(re.findall(p, lower)) for k, p in PATTERNS.items()}
    student = counts["student_hits"] + counts["fj_visa_hits"] + counts["opt_sevis_hits"]
    if student >= 10:
        return "core", "frequent student / F-J / OPT references", counts, text
    # H-1B-focused documents mention it 20+ times; fee schedules mention it ~10.
    if counts["h1b_hits"] >= 20:
        return "core", "frequent H-1B references (post-study work pathway)", counts, text
    if counts["visa_entry_hits"] >= 10:
        return "context", "general visa/entry rule; few student references", counts, text
    return "exclude", "few student or visa references in full text", counts, text


def fr_stage(doc):
    if doc.get("type") == "Presidential Document":
        return doc.get("subtype") or "Presidential Document"
    return {"Rule": "Final rule", "Proposed Rule": "Proposed rule"}.get(doc.get("type"), doc.get("type"))


def fetch_federal_register(start, end):
    """Collect and screen Federal Register documents; return one row per document."""
    queries = [dict(doc_types=["RULE", "PRORULE"], term=t, agencies=FR_AGENCIES) for t in FR_SEARCH_TERMS]
    queries += [dict(doc_types=["PRESDOCU"], term=t) for t in FR_PRESIDENTIAL_TERMS]
    queries += [dict(doc_types=["RULE", "PRORULE"], cfr=c) for c in FR_CFR_PARTS]
    docs = {}
    for q in queries:
        for doc in fr_search(start, end, **q):
            docs[doc["document_number"]] = doc
    print(f"Screening {len(docs)} Federal Register documents")

    rows = []
    for doc in docs.values():
        tier, reason, counts, text = fr_screen(doc)
        signed = doc.get("signing_date")
        rows.append({
            # Presidential documents are announced when signed; rules when published.
            "event_date": signed or doc.get("publication_date"),
            "source": "Federal Register",
            "doc_type": fr_stage(doc),
            "title": doc.get("title"),
            "auto_tier": tier,
            "auto_reason": reason,
            **counts,
            "summary": doc.get("abstract") or "",
            "text": text,
            "url": doc.get("html_url"),
            "source_id": doc["document_number"],
        })
    return rows
