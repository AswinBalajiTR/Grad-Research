"""Monthly arrivals in the US on student visas, by country and world region of residence
Source: https://www.trade.gov/i-94-arrivals-historical-data (no key)
"""

import argparse
import re
from datetime import datetime

import requests

from common import HEADERS, OUT, START_YEAR, STOP_DATE, download, read_xlsx, write_long

PAGE = "https://www.trade.gov/i-94-arrivals-historical-data"
SITE = "https://www.trade.gov/"
# Column group in Table D's header -> measure. "Tourism" is the 2026 label for pleasure visas.
GROUPS = [("student", "student_visa_arrivals"), ("business", "business_visa_arrivals"),
          ("pleasure", "pleasure_visa_arrivals"), ("tourism", "pleasure_visa_arrivals"),
          ("total", "total_arrivals")]
# Rows are nested by indentation: world regions, then their countries, then summary totals.
LEVELS = {4: "region", 6: "country"}


def list_files():
    """{YYYY-MM: workbook URL} from the month selector on the download page."""
    html = requests.get(PAGE, headers=HEADERS, timeout=120).text
    files = {}
    for href, label in re.findall(r'<option value="([^"]+\.xlsx)">\s*([A-Za-z]+ \d{4})', html):
        month = datetime.strptime(label, "%B %Y").strftime("%Y-%m")
        files[month] = href if href.startswith("http") else SITE + href.lstrip("/")
    return files


def count_columns(header):
    """{column letter: measure} for the Count column of each visa group (the first column of the group)."""
    columns = {}
    for col in sorted(header, key=lambda c: (len(c), c)):
        text = header[col].lower()
        for word, measure in GROUPS:
            if word in text and measure not in columns.values():
                columns[col] = measure
    return columns


def parse_table_d(path, month):
    rows = read_xlsx(path)["Table D"]
    start = next(i for i, r in enumerate(rows) if any("student" in v.lower() for v in r.values()))
    columns = count_columns(rows[start])
    out = []
    for r in rows[start + 2:]:  # skip the group header and the Count / % Change header
        raw = r.get("A", "")
        name = raw.strip(" \xa0")
        if not name:
            continue
        unit_type = LEVELS.get(len(raw) - len(raw.lstrip(" \xa0")), "summary")
        for col, measure in columns.items():
            value = r.get(col, "").strip()
            if value:
                out.append(dict(unit_type=unit_type, unit_id=name, unit_name=name, period=month,
                                measure=measure, value=int(float(value)),
                                source="NTTO I-94 Arrivals, Table D (country of residence and type of visa)"))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--refresh", action="store_true", help="download the workbooks again")
    parser.add_argument("--stop", default=STOP_DATE, help="last date of the study (YYYY-MM-DD)")
    args = parser.parse_args()

    files = {m: u for m, u in list_files().items() if f"{START_YEAR}-01" <= m <= args.stop[:7]}
    rows, seen = [], set()
    for month, url in sorted(files.items()):
        path = download(url, f"i94/{month}.xlsx", refresh=args.refresh)
        for r in parse_table_d(path, month):
            key = (r["unit_type"], r["unit_id"], r["period"], r["measure"])
            if key not in seen:  # Total Overseas and Grand Total appear twice in Table D
                seen.add(key)
                rows.append(r)
    write_long(rows, OUT / "i94_arrivals.csv")
    print(f"months {min(files)} to {max(files)}; NTTO has not yet published later months")


if __name__ == "__main__":
    main()
