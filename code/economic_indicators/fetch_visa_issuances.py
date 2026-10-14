"""Monthly nonimmigrant visas issued by the State Department, by nationality and visa class, 
Source: State Department, "NIV Issuances by Nationality and Visa Class" (monthly PDF),
  https://travel.state.gov/content/travel/en/legal/visa-law0/visa-statistics/nonimmigrant-visa-statistics/monthly-nonimmigrant-visa-issuances.html

"""

import argparse
import re
from collections import defaultdict
from datetime import date

import pdfplumber
import requests

from common import OUT, START_YEAR, STOP_DATE, download, write_long

PATH = ("/content/dam/visas/Statistics/Non-Immigrant-Statistics/MonthlyNIVIssuances/"
        "{month}%20{year}%20-%20NIV%20Issuances%20by%20Nationality%20and%20Visa%20Class.pdf")
HOSTS = ["https://travel.state.gov", "https://adoption.state.gov"]
CLASSES = "F1,F2,M1,J1,H1B,B1/B2"
# A table line is "<nationality> <visa class> <count>"; nationalities may contain spaces.
LINE = re.compile(r"^(.+) (\S+) ([\d,]+)$")
GRAND_TOTAL = re.compile(r"^GRAND TOTAL ([\d,]+)$")


def fetch_pdf(year, month, refresh):
    """Local path of one month's PDF, or None when no host has it."""
    name = date(year, month, 1).strftime("%B").upper()
    for host in HOSTS:
        try:
            path = download(host + PATH.format(month=name, year=year), f"visa_issuances/{year}-{month:02d}.pdf",
                            refresh=refresh)
        except requests.HTTPError:
            continue  # blocked; try the next host
        if path:
            return path
    return None


def parse(path):
    """{(nationality, visa class): issuances}, checked against the file's grand total."""
    counts, total = {}, None
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").splitlines():
                if m := GRAND_TOTAL.match(line):
                    total = int(m.group(1).replace(",", ""))
                elif (m := LINE.match(line)) and not line.startswith("Page "):
                    counts[(m.group(1), m.group(2))] = int(m.group(3).replace(",", ""))
    if total is not None and sum(counts.values()) != total:
        print(f"  {path.name}: rows sum to {sum(counts.values()):,} but the grand total is {total:,}")
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--classes", default=CLASSES, help="comma-separated visa classes to keep")
    parser.add_argument("--refresh", action="store_true", help="download the PDFs again")
    parser.add_argument("--stop", default=STOP_DATE, help="last date of the study (YYYY-MM-DD)")
    args = parser.parse_args()
    keep = {c.strip().upper() for c in args.classes.split(",")}
    stop = date.fromisoformat(args.stop)

    rows, missing = [], []
    for year in range(START_YEAR, stop.year + 1):
        for month in range(1, 13):
            if date(year, month, 1) > stop:
                break
            path = fetch_pdf(year, month, args.refresh)
            if path is None:
                missing.append(f"{year}-{month:02d}")
                continue
            period = f"{year}-{month:02d}"
            by_nationality = defaultdict(int)
            for (nationality, cls), n in parse(path).items():
                by_nationality[nationality] += n
                if cls.upper() in keep:
                    rows.append(dict(unit_type="nationality", unit_id=nationality, unit_name=nationality,
                                     period=period, measure=f"{cls.lower().replace('/', '_')}_issuances", value=n,
                                     source=f"State Department NIV issuances by nationality and visa class ({cls})"))
            rows += [dict(unit_type="nationality", unit_id=nat, unit_name=nat, period=period,
                          measure="all_classes_issuances", value=n,
                          source="State Department NIV issuances by nationality and visa class (all classes)")
                     for nat, n in by_nationality.items()]
    write_long(rows, OUT / "visa_issuances.csv")
    if missing:
        print(f"not found on any host (not yet posted?): {', '.join(missing)}")


if __name__ == "__main__":
    main()
