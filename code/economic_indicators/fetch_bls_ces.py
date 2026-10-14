"""BLS Current Employment Statistics (CES)
Source: BLS Public Data API v2, https://www.bls.gov/developers/

Series (employment, thousands of jobs):
  national  private colleges and universities (NAICS 6113), state-government
            education, leisure and hospitality, total nonfarm; seasonally
            adjusted (_sa) and not (_nsa)
  state     private colleges and universities, state-government education,
            total nonfarm (not seasonally adjusted)
  metro     state government (in a college town, mostly the public university),
            government, leisure and hospitality, retail trade, total nonfarm
            (not seasonally adjusted), for the college-town metros picked below

"""

import argparse
import csv
import hashlib
import json
import os
import time
from datetime import date

import requests

from common import OUT, RAW, START_YEAR, STOP_DATE, download, read_csv_bytes, write_long

BLS_API = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
QCEW_AREA_TITLES = "https://data.bls.gov/cew/doc/titles/area/area_titles.csv"
SOURCE = "BLS CES"

# Industry code (8 digits) -> measure name
NATIONAL = {"65611300": "private_colleges", "90921611": "state_govt_education",
            "70000000": "leisure_hospitality", "00000000": "total_nonfarm"}
STATE = {"65611300": "private_colleges", "90921611": "state_govt_education", "00000000": "total_nonfarm"}
METRO = {"90920000": "state_govt", "90000000": "government", "70000000": "leisure_hospitality",
         "42000000": "retail", "00000000": "total_nonfarm"}

STATE_NAMES = {
    "01": "Alabama", "02": "Alaska", "04": "Arizona", "05": "Arkansas", "06": "California", "08": "Colorado",
    "09": "Connecticut", "10": "Delaware", "11": "District of Columbia", "12": "Florida", "13": "Georgia",
    "15": "Hawaii", "16": "Idaho", "17": "Illinois", "18": "Indiana", "19": "Iowa", "20": "Kansas",
    "21": "Kentucky", "22": "Louisiana", "23": "Maine", "24": "Maryland", "25": "Massachusetts",
    "26": "Michigan", "27": "Minnesota", "28": "Mississippi", "29": "Missouri", "30": "Montana",
    "31": "Nebraska", "32": "Nevada", "33": "New Hampshire", "34": "New Jersey", "35": "New Mexico",
    "36": "New York", "37": "North Carolina", "38": "North Dakota", "39": "Ohio", "40": "Oklahoma",
    "41": "Oregon", "42": "Pennsylvania", "44": "Rhode Island", "45": "South Carolina", "46": "South Dakota",
    "47": "Tennessee", "48": "Texas", "49": "Utah", "50": "Vermont", "51": "Virginia", "53": "Washington",
    "54": "West Virginia", "55": "Wisconsin", "56": "Wyoming",
}
ABBR_TO_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08", "CT": "09", "DE": "10", "DC": "11",
    "FL": "12", "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21",
    "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29", "MT": "30",
    "NE": "31", "NV": "32", "NH": "33", "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49",
    "VT": "50", "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56",
}


def read_rows(name):
    path = OUT / name
    if not path.exists():
        raise SystemExit(f"{path} not found; run build_exposure.py first")
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def metro_titles():
    """{cbsa: official metro name} from the QCEW area titles, where metros are
    coded "C" + the first four digits of the CBSA code."""
    path = download(QCEW_AREA_TITLES, "qcew/area_titles.csv")
    return {r["area_fips"][1:] + "0": r["area_title"] for r in read_csv_bytes(path.read_bytes())
            if r["area_fips"].startswith("C") and r["area_fips"][1:].isdigit()}


def college_metros(n):
    """[(cbsa, state fips, name)] for up to n college-town metros: half from the
    counties most dependent on international students, half from the metros with
    the most international students."""
    insts = read_rows("institutions.csv")
    exposure = read_rows("exposure.csv")
    latest = max(r["period"] for r in exposure if r["unit_type"] == "county")
    per_1000 = {r["unit_id"]: float(r["value"]) for r in exposure
                if r["unit_type"] == "county" and r["period"] == latest and r["measure"] == "intl_per_1000_residents"}
    by_cbsa, county_cbsa, county_intl, names = {}, {}, {}, {}
    for r in insts:
        if not r["cbsa"] or not r["intl_enrollment"]:
            continue
        intl = float(r["intl_enrollment"])
        county_intl[r["county_fips"]] = county_intl.get(r["county_fips"], 0) + intl
        c = by_cbsa.setdefault(r["cbsa"], {"intl": 0, "states": {}})
        c["intl"] += intl
        c["states"][r["state"]] = c["states"].get(r["state"], 0) + intl
        county_cbsa[r["county_fips"]] = r["cbsa"]
        names.setdefault(r["cbsa"], f'{r["county_name"]}, {r["state"]} area')
    names.update(metro_titles())
    # Counties with at least 1,000 international students, most dependent first.
    dependent = sorted((f for f in per_1000 if f in county_cbsa and county_intl[f] >= 1000),
                       key=lambda f: -per_1000[f])
    picks = []
    for f in dependent:
        if county_cbsa[f] not in picks:
            picks.append(county_cbsa[f])
        if len(picks) >= n // 2:
            break
    for cbsa in sorted(by_cbsa, key=lambda c: -by_cbsa[c]["intl"]):
        if len(picks) >= n:
            break
        if cbsa not in picks:
            picks.append(cbsa)
    out = []
    for cbsa in picks:
        # BLS files a metro under one state; use the state with most of its international students.
        state = max(by_cbsa[cbsa]["states"], key=by_cbsa[cbsa]["states"].get)
        if state in ABBR_TO_FIPS:
            out.append((cbsa, ABBR_TO_FIPS[state], names[cbsa]))
    return out


def series_list(metros):
    """{series id: (unit_type, unit_id, unit_name, measure)}"""
    s = {}
    for code, name in NATIONAL.items():
        s[f"CES{code}01"] = ("national", "US", "United States", f"{name}_sa")
        s[f"CEU{code}01"] = ("national", "US", "United States", f"{name}_nsa")
    for fips, state in STATE_NAMES.items():
        for code, name in STATE.items():
            s[f"SMU{fips}00000{code}01"] = ("state", fips, state, f"{name}_nsa")
    for cbsa, fips, label in metros:
        for code, name in METRO.items():
            s[f"SMU{fips}{cbsa}{code}01"] = ("metro", cbsa, label, f"{name}_nsa")
    return s


def fetch(ids, start, end, key, refresh):
    """BLS response for a batch of series, cached by the request contents."""
    body = {"seriesid": ids, "startyear": str(start), "endyear": str(end)}
    if key:
        body["registrationkey"] = key
    tag = hashlib.md5(json.dumps({k: v for k, v in body.items() if k != "registrationkey"},
                                 sort_keys=True).encode()).hexdigest()[:16]
    cache = RAW / "bls" / f"{tag}.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))
    resp = requests.post(BLS_API, json=body, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "REQUEST_SUCCEEDED":
        raise SystemExit(f"BLS API: {data.get('status')} {data.get('message')}")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data), encoding="utf-8")
    time.sleep(1)  # be polite to the API
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--key", default=os.environ.get("BLS_API_KEY"), help="BLS key (optional; or set BLS_API_KEY)")
    parser.add_argument("--metros", type=int, default=40, help="number of college-town metros")
    parser.add_argument("--refresh", action="store_true", help="ignore cached responses (to get new months)")
    parser.add_argument("--stop", default=STOP_DATE, help="last date of the study (YYYY-MM-DD)")
    args = parser.parse_args()
    stop = date.fromisoformat(args.stop)

    metros = college_metros(args.metros)
    series = series_list(metros)
    batch = 50 if args.key else 25
    ids = list(series)
    print(f"{len(ids)} series in {-(-len(ids) // batch)} requests ({len(metros)} metros)")

    rows, missing = [], []
    for i in range(0, len(ids), batch):
        data = fetch(ids[i:i + batch], START_YEAR, stop.year, args.key, args.refresh)
        for s in data["Results"]["series"]:
            unit_type, unit_id, unit_name, measure = series[s["seriesID"]]
            if not s["data"]:
                missing.append(s["seriesID"])
                continue
            for x in s["data"]:
                if not x["period"].startswith("M") or x["period"] == "M13":  # M13 is the annual average
                    continue
                period = f'{x["year"]}-{x["period"][1:]}'
                if period + "-01" > args.stop or x["value"] in ("-", ""):
                    continue
                rows.append(dict(unit_type=unit_type, unit_id=unit_id, unit_name=unit_name, period=period,
                                 measure=f"{measure.rsplit('_', 1)[0]}_employment_thousands_{measure.rsplit('_', 1)[1]}",
                                 value=float(x["value"]), source=SOURCE))
    rows.sort(key=lambda r: (r["unit_type"], r["unit_id"], r["measure"], r["period"]))
    write_long(rows, OUT / "bls_ces.csv")
    if missing:
        print(f"{len(missing)} series not published by BLS (skipped), e.g. {', '.join(missing[:5])}")


if __name__ == "__main__":
    main()
