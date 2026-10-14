"""Zillow Observed Rent Index (ZORI) by ZIP code, monthly.
Source: https://www.zillow.com/research/data/ (Rentals > ZORI, all homes plus
multifamily, smoothed). Values are typical asking rents in dollars.
"""

import argparse
import csv

from common import OUT, START_YEAR, STOP_DATE, download, read_csv_bytes, write_long, write_table

ZORI_ZIP = "https://files.zillowstatic.com/research/public_csvs/zori/Zip_zori_uc_sfrcondomfr_sm_month.csv"


def near_campus_zips():
    """{zcta: number of campuses within the radius}, empty if build_exposure.py has not run."""
    path = OUT / "campus_zips.csv"
    if not path.exists():
        print("campus_zips.csv not found; run build_exposure.py to fill the near_campus column")
        return {}
    counts = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            counts[r["zcta"]] = counts.get(r["zcta"], 0) + 1
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--refresh", action="store_true", help="download a fresh copy (Zillow updates monthly)")
    parser.add_argument("--stop", default=STOP_DATE, help="last date of the study (YYYY-MM-DD)")
    args = parser.parse_args()

    path = download(ZORI_ZIP, "zillow/Zip_zori_uc_sfrcondomfr_sm_month.csv", refresh=args.refresh)
    data = read_csv_bytes(path.read_bytes())
    # Month columns are month-end dates (YYYY-MM-DD); keep months from START_YEAR
    # that begin on or before the stop date.
    months = [c for c in data[0] if c[:4].isdigit() and int(c[:4]) >= START_YEAR and c[:7] + "-01" <= args.stop]
    print(f"ZORI: {len(data)} ZIPs, {months[0][:7]} to {months[-1][:7]}")

    campuses = near_campus_zips()
    rows, lookup = [], []
    for r in data:
        z = r["RegionName"].zfill(5)
        lookup.append({"zip": z, "city": r["City"], "county": r["CountyName"], "state": r["State"],
                       "metro": r["Metro"], "near_campus": int(z in campuses),
                       "campuses_nearby": campuses.get(z, 0)})
        for m in months:
            if r[m]:
                rows.append(dict(unit_type="zcta", unit_id=z, unit_name=f'{r["City"]}, {r["State"]}',
                                 period=m[:7], measure="rent_index_usd", value=round(float(r[m]), 2),
                                 source="Zillow ZORI (all homes + multifamily, smoothed)"))
    write_long(rows, OUT / "zori.csv")
    write_table(lookup, ["zip", "city", "county", "state", "metro", "near_campus", "campuses_nearby"],
                OUT / "zori_zips.csv")
    print(f"{sum(r['near_campus'] for r in lookup)} of {len(lookup)} ZORI ZIPs are near a campus")


if __name__ == "__main__":
    main()
