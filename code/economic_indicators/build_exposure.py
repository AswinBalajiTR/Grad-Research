"""International-student exposure by institution, county, and ZIP, plus the
crosswalk that links institutions to places.

Sources:
  IPEDS Fall Enrollment part A (EFyyyyA) and Institutional Characteristics (HDyyyy):
    https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx
  Census county population estimates (PEP):
    https://www2.census.gov/programs-surveys/popest/datasets/
  Census ZCTA Gazetteer (ZIP centroids):
    https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html

Outputs (data/processed/economic_indicators/):
  institutions.csv  one row per institution: location and international share in --exposure-year
  campus_zips.csv   ZIPs (ZCTAs) whose centroid is within --radius miles of a campus
  exposure.csv      long format, every fall from 2022 to --stop: institution, county, and ZIP measures

"""

import argparse
import math
import zipfile
from collections import defaultdict
from datetime import date

from common import OUT, START_YEAR, STOP_DATE, download, read_csv_bytes, read_csv_in_zip, write_long, write_table

IPEDS = "https://nces.ed.gov/ipeds/datacenter/data/{}.zip"
PEP_COUNTIES = ("https://www2.census.gov/programs-surveys/popest/datasets/"
                "2020-{y}/counties/totals/co-est{y}-alldata.csv")
GAZETTEER_ZCTA = ("https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
                  "{y}_Gazetteer/{y}_Gaz_zcta_national.zip")

# EFALEVEL rows of the Fall Enrollment file used here.
LEVELS = {"1": "total", "2": "undergrad", "12": "grad"}
# IPEDS sector 0 is an administrative unit (a system office), not a campus.
ADMIN_SECTOR = "0"
EARTH_RADIUS_MI = 3958.8


def latest_release(make_url, name, first_year):
    """Download the newest yearly release, trying from this year backwards.
    Returns (year, path)."""
    for year in range(date.today().year, first_year - 1, -1):
        path = download(make_url(year), name(year))
        if path:
            return year, path
    raise SystemExit(f"no release found for {name(first_year)}")


def fall_enrollment(year):
    """{unitid: {"total": n, "intl": n, "undergrad_intl": n, "grad_intl": n}}, or None
    if IPEDS has not published that fall yet."""
    path = download(IPEDS.format(f"EF{year}A"), f"ipeds/EF{year}A.zip")
    if not path:
        return None
    out = defaultdict(dict)
    for r in read_csv_in_zip(path):
        level = LEVELS.get(r["EFALEVEL"].strip())
        if level == "total":
            out[r["UNITID"]]["total"] = int(r["EFTOTLT"] or 0)
            out[r["UNITID"]]["intl"] = int(r["EFNRALT"] or 0)
        elif level:
            out[r["UNITID"]][f"{level}_intl"] = int(r["EFNRALT"] or 0)
    return out


def institutions():
    """Location of each institution, from the newest IPEDS directory file."""
    year, path = latest_release(lambda y: IPEDS.format(f"HD{y}"), lambda y: f"ipeds/HD{y}.zip", START_YEAR)
    print(f"IPEDS directory: HD{year}")
    out = {}
    for r in read_csv_in_zip(path):
        if r["SECTOR"] == ADMIN_SECTOR:
            continue
        county = r["COUNTYCD"].strip()
        out[r["UNITID"]] = {
            "unitid": r["UNITID"],
            "name": r["INSTNM"],
            "state": r["STABBR"],
            "sector": r["SECTOR"],
            "county_fips": county.zfill(5) if county.isdigit() else "",  # -2 means not applicable
            "county_name": r["COUNTYNM"],
            "zip5": r["ZIP"][:5],
            "cbsa": r["CBSA"] if r["CBSA"].isdigit() else "",
            "latitude": float(r["LATITUDE"]) if r["LATITUDE"].strip() else None,
            "longitude": float(r["LONGITUD"]) if r["LONGITUD"].strip() else None,
        }
    return out


def county_population():
    """{(county_fips, year): population} from the newest Census county estimates."""
    _, path = latest_release(lambda y: PEP_COUNTIES.format(y=y), lambda y: f"census/co-est{y}-alldata.csv", 2024)
    pop = {}
    for r in read_csv_bytes(path.read_bytes()):
        if r["SUMLEV"] != "050":  # counties only
            continue
        fips = r["STATE"] + r["COUNTY"]
        for col, value in r.items():
            if col.startswith("POPESTIMATE") and col[11:].isdigit():
                pop[(fips, int(col[11:]))] = int(value)
    return pop


def zcta_centroids():
    """{zcta: (lat, lon)} from the newest Census ZCTA Gazetteer file."""
    _, path = latest_release(lambda y: GAZETTEER_ZCTA.format(y=y), lambda y: f"census/{y}_Gaz_zcta_national.zip", 2024)
    with zipfile.ZipFile(path) as z:
        lines = z.read(z.namelist()[0]).decode("utf-8-sig").splitlines()
    # Tab-delimited through 2025, pipe-delimited from 2026 (which also adds GEOIDFQ).
    sep = "|" if "|" in lines[0] else "\t"
    header = [h.strip() for h in lines[0].split(sep)]
    lat, lon = header.index("INTPTLAT"), header.index("INTPTLONG")
    out = {}
    for line in lines[1:]:
        f = line.split(sep)
        out[f[0]] = (float(f[lat]), float(f[lon]))
    return out


def miles(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(h))


def campus_zips(insts, zctas, radius):
    """[(unitid, zcta, distance)] for ZCTA centroids within `radius` miles of each campus.
    ZCTAs are bucketed by whole degree so each campus is compared only with nearby ones."""
    buckets = defaultdict(list)
    for z, pt in zctas.items():
        buckets[(math.floor(pt[0]), math.floor(pt[1]))].append((z, pt))
    reach = math.ceil(radius / 40) + 1  # a degree is at least ~40 miles across within the US
    out = []
    for inst in insts.values():
        if inst["latitude"] is None:
            continue
        pt = (inst["latitude"], inst["longitude"])
        lat0, lon0 = math.floor(pt[0]), math.floor(pt[1])
        for dlat in range(-reach, reach + 1):
            for dlon in range(-reach, reach + 1):
                for z, zpt in buckets.get((lat0 + dlat, lon0 + dlon), ()):
                    d = miles(pt, zpt)
                    if d <= radius:
                        out.append((inst["unitid"], z, d))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--exposure-year", type=int, default=2023,
                        help="fall used for the fixed exposure measure (before the 2025 policies)")
    parser.add_argument("--radius", type=float, default=5.0, help="miles from campus for 'near campus' ZIPs")
    parser.add_argument("--stop", default=STOP_DATE, help="last date of the study (YYYY-MM-DD)")
    args = parser.parse_args()
    stop = date.fromisoformat(args.stop)

    insts = institutions()
    enroll = {}
    # IPEDS fall enrollment is counted as of October 15 (or the school's official fall date).
    falls = [y for y in range(START_YEAR, stop.year + 1) if date(y, 10, 15) <= stop]
    for year in falls:
        data = fall_enrollment(year)
        if data is None:
            print(f"IPEDS fall {year} enrollment not published yet; stopping at fall {year - 1}")
            break
        enroll[year] = data
    if args.exposure_year not in enroll:
        raise SystemExit(f"fall {args.exposure_year} enrollment is not available; pick one of {sorted(enroll)}")
    pop = county_population()

    # Institution table with the fixed exposure measure.
    base = enroll[args.exposure_year]
    for uid, inst in insts.items():
        e = base.get(uid, {})
        inst["enrollment"] = e.get("total", "")
        inst["intl_enrollment"] = e.get("intl", "")
        inst["intl_share"] = e["intl"] / e["total"] if e.get("total") else ""
    write_table(sorted(insts.values(), key=lambda r: r["unitid"]),
                ["unitid", "name", "state", "sector", "county_fips", "county_name", "zip5", "cbsa",
                 "latitude", "longitude", "enrollment", "intl_enrollment", "intl_share"],
                OUT / "institutions.csv")

    # Only campuses with international students are linked to ZIPs.
    with_intl = {u: i for u, i in insts.items() if i["intl_enrollment"]}
    links = campus_zips(with_intl, zcta_centroids(), args.radius)
    write_table([{"unitid": u, "name": insts[u]["name"], "zcta": z, "distance_mi": d} for u, z, d in links],
                ["unitid", "name", "zcta", "distance_mi"], OUT / "campus_zips.csv")

    rows = []
    src_ipeds = "IPEDS Fall Enrollment"
    county_names = {i["county_fips"]: f'{i["county_name"]}, {i["state"]}' for i in insts.values()}
    for year, data in enroll.items():
        period = f"{year}-fall"
        county_intl, county_total = defaultdict(int), defaultdict(int)
        zip_intl = defaultdict(int)
        for uid, e in data.items():
            inst = insts.get(uid)
            if not inst:
                continue
            name = inst["name"]
            rows.append(dict(unit_type="institution", unit_id=uid, unit_name=name, period=period,
                             measure="enrollment", value=e.get("total", 0), source=src_ipeds))
            for key in ("intl", "undergrad_intl", "grad_intl"):
                rows.append(dict(unit_type="institution", unit_id=uid, unit_name=name, period=period,
                                 measure=f"{key}_enrollment", value=e.get(key, 0), source=src_ipeds))
            if e.get("total"):
                rows.append(dict(unit_type="institution", unit_id=uid, unit_name=name, period=period,
                                 measure="intl_share", value=e.get("intl", 0) / e["total"],
                                 source=src_ipeds))
            if inst["county_fips"]:
                county_intl[inst["county_fips"]] += e.get("intl", 0)
                county_total[inst["county_fips"]] += e.get("total", 0)
        for uid, z, _ in links:
            zip_intl[z] += data.get(uid, {}).get("intl", 0)
        for fips, intl in county_intl.items():
            name = county_names.get(fips, "")
            rows.append(dict(unit_type="county", unit_id=fips, unit_name=name, period=period,
                             measure="intl_enrollment", value=intl, source=src_ipeds))
            rows.append(dict(unit_type="county", unit_id=fips, unit_name=name, period=period,
                             measure="enrollment", value=county_total[fips], source=src_ipeds))
            p = pop.get((fips, year))
            if p:
                rows.append(dict(unit_type="county", unit_id=fips, unit_name=name, period=period,
                                 measure="intl_per_1000_residents", value=1000 * intl / p,
                                 source=f"{src_ipeds}; Census population estimates"))
        for z, intl in zip_intl.items():
            rows.append(dict(unit_type="zcta", unit_id=z, period=period,
                             measure=f"intl_enrollment_within_{args.radius:g}mi", value=intl, source=src_ipeds))
    write_long(rows, OUT / "exposure.csv")


if __name__ == "__main__":
    main()
