"""BLS QCEW employment and wages
Source: QCEW open data, https://www.bls.gov/cew/additional-resources/open-data/
"""

import argparse
from collections import defaultdict
from datetime import date

from common import OUT, START_YEAR, STOP_DATE, download, read_csv_bytes, write_long

QCEW = "https://data.bls.gov/cew/data/api/{year}/{qtr}/industry/{industry}.csv"
AREA_TITLES = "https://data.bls.gov/cew/doc/titles/area/area_titles.csv"
OWNERS = {"0": "all_owners", "1": "federal_govt", "2": "state_govt", "3": "local_govt", "5": "private"}
# QCEW industry code -> (name, {aggregation level code: unit type})
INDUSTRIES = {
    "6113": ("colleges", {"16": "national", "56": "state", "76": "county"}),
    "10": ("all_industries", {"70": "county", "71": "county"}),  # 70 = total, 71 = by ownership
}
# Kept for all industries, so the output stays under Excel's row limit.
ALL_INDUSTRIES_MEASURES = {"employment", "total_wages"}


def quarter_measures(r):
    emp = (int(r["month1_emplvl"]) + int(r["month2_emplvl"]) + int(r["month3_emplvl"])) / 3
    return {"employment": round(emp, 1), "total_wages": int(r["total_qtrly_wages"]),
            "avg_weekly_wage": int(r["avg_wkly_wage"]), "establishments": int(r["qtrly_estabs"])}


def quarter_rows(path, industry, levels, period, titles):
    """Long rows for one industry file and quarter."""
    # (unit type, area) -> ownership -> measures; None marks a suppressed cell
    areas = defaultdict(dict)
    for r in read_csv_bytes(path.read_bytes()):
        level, owner = levels.get(r["agglvl_code"]), OWNERS.get(r["own_code"])
        if level and owner:
            areas[(level, r["area_fips"])][owner] = None if r["disclosure_code"] == "N" else quarter_measures(r)
    rows = []
    for (level, fips), owners in areas.items():
        base = dict(unit_type=level, unit_id=fips, unit_name=titles.get(fips, ""), period=period,
                    source=f"BLS QCEW, {'NAICS 6113' if industry == 'colleges' else 'all industries'}")
        if "all_owners" not in owners and all(owners.values()):
            owners["all_owners"] = {
                "employment": round(sum(m["employment"] for m in owners.values()), 1),
                "total_wages": sum(m["total_wages"] for m in owners.values()),
            }
        for owner, m in owners.items():
            for name, value in (m or {}).items():
                if industry == "all_industries" and name not in ALL_INDUSTRIES_MEASURES:
                    continue
                rows.append({**base, "measure": f"{industry}_{name}_{owner}", "value": value})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--refresh", action="store_true",
                        help="download the last two years again (BLS revises recent quarters)")
    parser.add_argument("--stop", default=STOP_DATE, help="last date of the study (YYYY-MM-DD)")
    args = parser.parse_args()
    stop = date.fromisoformat(args.stop)

    titles = {r["area_fips"]: r["area_title"]
              for r in read_csv_bytes(download(AREA_TITLES, "qcew/area_titles.csv").read_bytes())}
    rows = []
    # Quarters that begin on or before the stop date.
    quarters = [(y, q) for y in range(START_YEAR, stop.year + 1) for q in range(1, 5)
                if date(y, 3 * q - 2, 1) <= stop]
    for year, qtr in quarters:
        refresh = args.refresh and year >= date.today().year - 1
        paths = {code: download(QCEW.format(year=year, qtr=qtr, industry=code),
                                f"qcew/{year}q{qtr}_{code}.csv", refresh=refresh)
                 for code in INDUSTRIES}
        if not all(paths.values()):
            print(f"QCEW {year} Q{qtr} not published yet; stopping at the previous quarter")
            break
        for code, (industry, levels) in INDUSTRIES.items():
            rows += quarter_rows(paths[code], industry, levels, f"{year}-Q{qtr}", titles)
    write_long(rows, OUT / "qcew.csv")


if __name__ == "__main__":
    main()
