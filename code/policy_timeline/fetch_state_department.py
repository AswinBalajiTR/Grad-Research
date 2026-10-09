"""Collect and screen State Department pages that may affect international students.
"""

import re
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from fetch_federal_register import PATTERNS

CDX_URL = "https://web.archive.org/cdx/search/cdx"
ARCHIVE_URL = "https://web.archive.org/web/{timestamp}id_/{url}"

# Words that must appear in a state.gov press release URL. Most releases are
# unrelated diplomacy, so this keeps the list to a reviewable size.
RELEASE_URL_KEYWORDS = ["visa", "student", "vetting", "consular", "interview", "exchange-visitor",
                        "h-1b", "universit", "harvard", "academic", "entry", "immigra"]
SD_SOURCES = {
    "state.gov press release": {
        "cdx_url": "state.gov/releases/*",
        "url_filter": ".*(" + "|".join(RELEASE_URL_KEYWORDS) + ").*",
        # e.g. /releases/office-of-the-spokesperson/2025/06/<slug>/
        "slug": re.compile(r"state\.gov/releases/(?:[^/]+/)?\d{4}/\d{2}/([a-z0-9-]+)"),
    },
    "travel.state.gov visa news": {
        "cdx_url": "travel.state.gov/content/travel/en/News/visas-news/*",
        "url_filter": None,  # every visa news item is potentially relevant
        "slug": re.compile(r"visas-news/([a-z0-9-]+)\.html"),
    },
}
DATE_PATTERN = re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December)"
                          r"\s+(\d{1,2}),\s+(20\d\d)")
SLUG_DATE_PATTERN = re.compile(r"(jan|feb|mar|apr|may|jun|jul|aug|sept?|oct|nov|dec)[a-z]*-(\d{1,2})-(20\d\d)")
# Releases announcing visa bans on named officials or groups (sanctions).
TARGETED_RESTRICTION = re.compile(r"visa-restrictions?-(?:on|for|of|policy)|restriction-polic|restriction-targets|"
                                  r"targeted-visa|revokes-visas-of|revoking-visa-from|sanction")


def wb_get(url, params=None, retries=5):
    """GET with backoff; the Wayback Machine is slow and sometimes refuses."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=300)
            if resp.status_code not in (429, 502, 503, 504):
                resp.raise_for_status()
                return resp
        except requests.ConnectionError:
            pass
        wait = 10 * 2 ** attempt
        print(f"  archive busy; waiting {wait}s")
        time.sleep(wait)
    raise RuntimeError(f"giving up on {url}")


def list_archived_pages(source, start):
    """Return {slug: {"url", "first_archived"}} for one source."""
    cfg = SD_SOURCES[source]
    params = [("url", cfg["cdx_url"]), ("from", start.replace("-", "")), ("output", "json"),
              ("fl", "timestamp,original"), ("collapse", "urlkey"), ("filter", "statuscode:200")]
    if cfg["url_filter"]:
        params.append(("filter", "original:" + cfg["url_filter"]))
    pages = {}
    for timestamp, original in wb_get(CDX_URL, params).json()[1:]:  # first row is the header
        m = cfg["slug"].search(original)
        if not m or m.group(1) == "archive":  # "archive" is the news index page
            continue
        # Keep the earliest capture, and a clean URL without query strings.
        clean = original.split("?")[0].split("#")[0]
        page = pages.setdefault(m.group(1), {"url": clean, "first_archived": timestamp})
        page["first_archived"] = min(page["first_archived"], timestamp)
        if "%" in page["url"] and "%" not in clean:
            page["url"] = clean
    # The archive also holds truncated URLs (e.g. "new-visa-polici"); drop any
    # slug that is a prefix of a longer one.
    slugs = sorted(pages)
    return {s: pages[s] for s in slugs if not any(o != s and o.startswith(s) for o in slugs)}


def archived_html(page):
    """Download a page's archived copy; b"" if no usable copy."""
    # Some captures are broken on the archive's side; fall back to the most
    # recent capture before giving up.
    for timestamp in (page["first_archived"], datetime.now().strftime("%Y%m%d")):
        try:
            content = wb_get(ARCHIVE_URL.format(timestamp=timestamp, url=page["url"]), retries=3).content
        except (requests.HTTPError, RuntimeError) as err:
            print(f"  could not download {page['slug'][:60]} ({timestamp}): {err}")
            continue
        time.sleep(1)  # be polite to the archive
        # The archive sometimes captured state.gov's bot-block page instead.
        if b"<title>Technical Difficulties</title>" in content[:5000]:
            print(f"  archived copy of {page['slug'][:60]} ({timestamp}) is an error page")
            continue
        return content
    return b""


def parse_date(text):
    m = DATE_PATTERN.search(text or "")
    return datetime.strptime(" ".join(m.groups()), "%B %d %Y").date().isoformat() if m else ""


def parse_page(page):
    """Return title, page date, how the date was found, and body text."""
    first = datetime.strptime(page["first_archived"][:8], "%Y%m%d").date().isoformat()
    html = archived_html(page)
    if not html:
        return page["slug"].replace("-", " "), first, "first archived", ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    updated = None
    if page["source"].startswith("state.gov"):
        headline, meta, body = (soup.select_one(s) for s in (".featured-content__headline", ".article-meta", ".entry-content"))
        title = headline.get_text(" ", strip=True) if headline else ""
        date_text = meta.get_text(" ", strip=True) if meta else ""
        text = body.get_text(" ", strip=True) if body else ""
    else:
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        text = " ".join(el.get_text(" ", strip=True) for el in soup.select(".tsg-rwd-text"))
        date_text = title  # many notices carry their date in the title
        updated = soup.select_one(".custom_dateselect")  # "Last Updated: <date>"
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)
    title = re.sub(r"\s+-\s+United States Department of State$", "", title)
    if not text and soup.body:
        text = soup.body.get_text(" ", strip=True)

    date_, basis = parse_date(date_text), "page"
    if not date_:
        m = SLUG_DATE_PATTERN.search(page["slug"])
        if m:
            date_ = datetime.strptime(f"{m.group(1)[:3]} {m.group(2)} {m.group(3)}", "%b %d %Y").date().isoformat()
            basis = "url"
    if not date_ and updated:
        date_, basis = parse_date(updated.get_text(" ", strip=True)), "last updated"
    if not date_:
        date_, basis = first, "first archived"
    return title, date_, basis, text


def sd_screen(page, text):
    """Return (tier, reason, counts). Thresholds are lower than for the
    Federal Register because press releases are short."""
    counts = {k: len(re.findall(p, text.lower())) for k, p in PATTERNS.items()}
    student = counts["student_hits"] + counts["fj_visa_hits"] + counts["opt_sevis_hits"]
    if not text:
        return "review", "archived page could not be downloaded or parsed; check by hand", counts
    if student >= 1:
        return "core", "mentions students / F-J / exchange visitors", counts
    if counts["h1b_hits"] >= 1:
        return "core", "mentions H-1B (post-study work pathway)", counts
    if TARGETED_RESTRICTION.search(page["slug"]):
        return "exclude", "visa restrictions targeting named officials or groups", counts
    if counts["visa_entry_hits"] >= 3:
        return "context", "general visa policy; no student references", counts
    return "exclude", "few student or visa references", counts


def fetch_state_department(start, end):
    """Collect and screen State Department pages; return one row per page.
    The archive listing is not cut at `end` (a page is often first captured
    after it was published); rows are filtered on the page's own date."""
    pages = [{"source": s, "slug": slug, **info} for s in SD_SOURCES for slug, info in list_archived_pages(s, start).items()]
    print(f"Screening {len(pages)} archived State Department pages")
    parsed = [parse_page(p) for p in pages]
    # Archive errors are often temporary: try the pages that failed once more.
    failed = [i for i, (_, _, _, text) in enumerate(parsed) if not text]
    if failed:
        print(f"Retrying {len(failed)} pages that could not be downloaded, in 30s")
        time.sleep(30)
        for i in failed:
            parsed[i] = parse_page(pages[i])

    rows = []
    for page, (title, date_, basis, text) in zip(pages, parsed):
        if not start <= date_ <= end:
            continue
        tier, reason, counts = sd_screen(page, text)
        rows.append({
            "event_date": date_,
            "source": page["source"],
            "doc_type": "Press release" if page["source"].startswith("state.gov") else "Visa news",
            "title": title,
            "auto_tier": tier,
            "auto_reason": reason,
            **counts,
            "summary": text[:6000],
            "text": text,
            "url": page["url"],
            "source_id": page["url"],
        })
    return rows
