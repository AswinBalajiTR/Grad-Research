#!/usr/bin/env python3
"""Prepare H-1B records from January 2025 through the latest DOL release."""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests


DATA_ROOT = Path(__file__).resolve().parents[2] / "data/h1b"
PERFORMANCE_URL = "https://www.dol.gov/agencies/eta/foreign-labor/performance"
STATE_PATH = DATA_ROOT / "processed/refresh_state.json"
CHECK_INTERVAL = timedelta(hours=24)


class DownloadLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def discover_dol_files() -> list[tuple[int, str, list[str]]]:
    """Use the newest cumulative LCA disclosure for each fiscal year."""
    response = requests.get(PERFORMANCE_URL, timeout=30)
    response.raise_for_status()
    links = DownloadLinks()
    links.feed(response.text)
    latest: dict[int, tuple[int, str, str]] = {}
    for href in links.hrefs:
        url = urljoin(PERFORMANCE_URL, href)
        if urlparse(url).hostname not in {"dol.gov", "www.dol.gov"}:
            continue
        filename = Path(urlparse(url).path).name
        # DOL's FY2026 link has a published spelling error: "Dislclosure".
        match = re.fullmatch(r"LCA_Di[a-z]*closure_Data_FY(\d{4})_Q([1-4])\.xlsx", filename, re.I)
        if not match:
            continue
        year, quarter = map(int, match.groups())
        if year < 2025:
            continue
        if year not in latest or quarter > latest[year][0]:
            latest[year] = (quarter, filename, url)
    if not latest or 2025 not in latest:
        raise RuntimeError("Could not find current LCA disclosure links on the DOL performance page")
    return [(year, filename, [url]) for year, (_, filename, url) in sorted(latest.items())]

USCIS_FY2025_URL = (
    "https://www.uscis.gov/sites/default/files/document/data/"
    "h1b_datahubexport-2025.csv"
)
DOL_FY2025_URL = (
    "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/"
    "LCA_Disclosure_Data_FY2025_Q4.xlsx"
)
DOL_FY2025_Q2_URL = (
    "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/"
    "LCA_Disclosure_Data_FY2025_Q2.xlsx"
)
DOL_FY2025_Q3_URL = (
    "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/"
    "LCA_Disclosure_Data_FY2025_Q3.xlsx"
)
DOL_FY2026_Q3_URL = (
    "https://www.dol.gov/media/LCA_Disclosure_Data_FY2026_Q3.xlsx"
)
DOL_LATEST_FILES = [
    (
        2025,
        "LCA_Disclosure_Data_FY2025_Q2.xlsx",
        [DOL_FY2025_Q2_URL, "https://www.dol.gov/media/LCA_Disclosure_Data_FY2025_Q2.xlsx"],
    ),
    (
        2025,
        "LCA_Disclosure_Data_FY2025_Q3.xlsx",
        [DOL_FY2025_Q3_URL, "https://www.dol.gov/media/LCA_Disclosure_Data_FY2025_Q3.xlsx"],
    ),
    (
        2025,
        "LCA_Disclosure_Data_FY2025_Q4.xlsx",
        [DOL_FY2025_URL, "https://www.dol.gov/media/LCA_Disclosure_Data_FY2025_Q4.xlsx"],
    ),
    (
        2026,
        "LCA_Disclosure_Data_FY2026_Q3.xlsx",
        [DOL_FY2026_Q3_URL],
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["uscis", "dol"], default="uscis")
    parser.add_argument("--input", help="Local CSV/XLSX exported from the official source")
    parser.add_argument("--source-url", help="Override the official download URL")
    parser.add_argument("--output", default=str(DATA_ROOT / "processed/h1b_filings_2025_to_latest.csv"))
    parser.add_argument("--auto", action="store_true", help="Check DOL once daily and rebuild only for a new release")
    return parser.parse_args()


def canonical(name: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def read_source(path: str | None, url: str, excel: bool) -> pd.DataFrame:
    if path:
        source = Path(path)
        if not source.exists():
            raise FileNotFoundError(source)
        return pd.read_excel(source) if source.suffix.lower() in {".xlsx", ".xls"} else pd.read_csv(source, low_memory=False)

    response = requests.get(url, timeout=180)
    if response.status_code == 404:
        raise RuntimeError(f"Official file was not found at {url}")
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "html" in content_type or response.content.lstrip().startswith(b"<"):
        raise RuntimeError("The source returned a web page instead of a data file")
    buffer = io.BytesIO(response.content)
    return pd.read_excel(buffer) if excel else pd.read_csv(buffer, low_memory=False)


def read_dol_file(filename: str, urls: list[str]) -> pd.DataFrame:
    """Reuse a local raw download, otherwise try each current official DOL URL."""
    raw_path = DATA_ROOT / "raw" / filename
    if raw_path.exists() and raw_path.stat().st_size > 0:
        return pd.read_excel(raw_path)

    errors: list[str] = []
    for url in urls:
        try:
            response = requests.get(url, timeout=180)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "html" in content_type or response.content.lstrip().startswith(b"<"):
                raise RuntimeError("server returned HTML instead of an Excel file")
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_bytes(response.content)
            return pd.read_excel(io.BytesIO(response.content))
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("No working official DOL download URL. " + " | ".join(errors))


def find_column(frame: pd.DataFrame, *candidates: str) -> str | None:
    by_key = {canonical(column): column for column in frame.columns}
    for candidate in candidates:
        if canonical(candidate) in by_key:
            return by_key[canonical(candidate)]
    return None


def numeric(frame: pd.DataFrame, column: str | None) -> pd.Series:
    if column is None:
        return pd.Series(0, index=frame.index, dtype="int64")
    return pd.to_numeric(frame[column], errors="coerce").fillna(0).astype("int64")


def text(frame: pd.DataFrame, column: str | None) -> pd.Series:
    if column is None:
        return pd.Series("", index=frame.index, dtype="string")
    return frame[column].fillna("").astype("string").str.strip()


def normalize_uscis(frame: pd.DataFrame) -> pd.DataFrame:
    fy_col = find_column(frame, "Fiscal Year", "FY", "fiscal_year")
    if fy_col:
        fiscal = pd.to_numeric(frame[fy_col].astype(str).str.extract(r"(\d{4})")[0], errors="coerce")
        frame = frame.loc[fiscal.eq(2025)].copy()
    employer = find_column(frame, "Employer", "Employer Name", "Petitioner Name")
    state = find_column(frame, "State", "Employer State")
    if employer is None or state is None:
        raise ValueError(
            "This does not look like a USCIS Employer Data Hub export: employer and state columns are required."
        )

    initial_approvals = numeric(frame, find_column(frame, "Initial Approval", "Initial Approvals"))
    initial_denials = numeric(frame, find_column(frame, "Initial Denial", "Initial Denials"))
    continuing_approvals = numeric(frame, find_column(frame, "Continuing Approval", "Continuing Approvals"))
    continuing_denials = numeric(frame, find_column(frame, "Continuing Denial", "Continuing Denials"))

    result = pd.DataFrame(
        {
            "fiscal_year": 2025,
            "employer_name": text(frame, employer),
            "employer_state": text(frame, state).str.upper(),
            "employer_city": text(frame, find_column(frame, "City", "Employer City")),
            "employer_zip": text(frame, find_column(frame, "ZIP", "Zip Code", "Employer Postal Code")),
            "naics_code": text(frame, find_column(frame, "NAICS", "NAICS Code")),
            "initial_approvals": initial_approvals,
            "initial_denials": initial_denials,
            "continuing_approvals": continuing_approvals,
            "continuing_denials": continuing_denials,
        }
    )
    result["total_approvals"] = result["initial_approvals"] + result["continuing_approvals"]
    result["total_denials"] = result["initial_denials"] + result["continuing_denials"]
    result["total_filings"] = result["total_approvals"] + result["total_denials"]
    result["source"] = "USCIS H-1B Employer Data Hub FY2025"
    return result.sort_values(["employer_state", "total_filings"], ascending=[True, False])


def normalize_dol(frame: pd.DataFrame, fiscal_year: int = 2025) -> pd.DataFrame:
    frame.columns = [canonical(column) for column in frame.columns]
    visa_col = "visa_class" if "visa_class" in frame.columns else None
    if visa_col is None:
        raise ValueError("DOL disclosure file is missing VISA_CLASS")
    frame = frame.loc[frame[visa_col].astype(str).str.upper().eq("H-1B")].copy()

    wanted = {
        "case_number": "case_number",
        "case_status": "case_status",
        "decision_date": "decision_date",
        "employer_name": "employer_name",
        "employer_city": "employer_city",
        "employer_state": "employer_state",
        "employer_postal_code": "employer_zip",
        "job_title": "job_title",
        "soc_code": "soc_code",
        "soc_title": "soc_title",
        "naics_code": "naics_code",
        "worksite_city": "worksite_city",
        "worksite_state": "worksite_state",
        "wage_rate_of_pay_from": "wage_from",
        "wage_rate_of_pay_to": "wage_to",
        "wage_unit_of_pay": "wage_unit",
        "full_time_position": "full_time_position",
    }
    existing = {source: target for source, target in wanted.items() if source in frame.columns}
    result = frame[list(existing)].rename(columns=existing)
    result.insert(0, "fiscal_year", fiscal_year)
    result["filing_count"] = 1
    result["source"] = f"U.S. Department of Labor FY{fiscal_year} H-1B LCA disclosure"
    for column in ["employer_state", "worksite_state"]:
        if column in result:
            result[column] = result[column].fillna("").astype(str).str.strip().str.upper()
    return result


def main() -> int:
    args = parse_args()
    output = Path(args.output)
    selected_files = DOL_LATEST_FILES
    try:
        if args.source == "dol" and not args.input and not args.source_url:
            state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
            checked = datetime.fromisoformat(state["checked_at"]) if state.get("checked_at") else None
            if args.auto and output.exists() and checked and datetime.now(timezone.utc) - checked < CHECK_INTERVAL:
                print("H-1B data already checked within the last 24 hours")
                return 0
            selected_files = discover_dol_files()
            filenames = [filename for _, filename, _ in selected_files]
            if args.auto and output.exists() and filenames == state.get("files"):
                STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
                STATE_PATH.write_text(json.dumps({"checked_at": datetime.now(timezone.utc).isoformat(), "files": filenames}))
                print("No new DOL LCA disclosure files")
                return 0
        if args.source == "uscis":
            frame = read_source(args.input, args.source_url or USCIS_FY2025_URL, excel=False)
            result = normalize_uscis(frame)
        else:
            if args.input or args.source_url:
                frame = read_source(args.input, args.source_url or DOL_FY2025_URL, excel=True)
                result = normalize_dol(frame, 2025)
            else:
                yearly = []
                for fiscal_year, filename, source_urls in selected_files:
                    frame = read_dol_file(filename, source_urls)
                    yearly.append(normalize_dol(frame, fiscal_year))
                result = pd.concat(yearly, ignore_index=True, sort=False)
                if "case_number" in result.columns:
                    result = result.drop_duplicates(subset=["case_number"], keep="last")
            if "decision_date" in result.columns:
                decision_dates = pd.to_datetime(result["decision_date"], errors="coerce")
                result = result.loc[decision_dates.ge(pd.Timestamp("2025-01-01"))].copy()
    except Exception as exc:
        print(f"Could not prepare {args.source.upper()} data: {exc}", file=sys.stderr)
        if args.source == "uscis" and not args.input:
            print(
                "Export FY2025 as CSV from the USCIS H-1B Employer Data Hub, save it under "
                f"{DATA_ROOT / 'raw'}/ and rerun with --input PATH.",
                file=sys.stderr,
            )
        return 2

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", dir=output.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        result.to_csv(temporary_path, index=False)
        os.replace(temporary_path, output)
    finally:
        temporary_path.unlink(missing_ok=True)
    if args.source == "dol" and not args.input and not args.source_url:
        STATE_PATH.write_text(json.dumps({
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "files": [filename for _, filename, _ in selected_files],
        }))
    print(f"Saved {len(result):,} {args.source.upper()} rows from 2025 through the latest available period to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
