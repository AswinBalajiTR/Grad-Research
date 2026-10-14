"""BEA education-related travel exports (spending by foreign students in the
US, including tuition), from 2022.
Source: BEA API, https://apps.bea.gov/API/signup/ (free key, emailed on signup)

Two datasets:
  ITA           International Transactions: national totals, quarterly
                (seasonally adjusted and not) and annual
  IntlServTrade International Services: annual, by country of the student

"""

import argparse
import json
import os
from datetime import date

import requests

from common import OUT, RAW, START_YEAR, write_long

BEA_API = "https://apps.bea.gov/api/data"


def bea(key, method, **params):
    resp = requests.get(BEA_API, params={"UserID": key, "method": method, "ResultFormat": "json", **params},
                        timeout=300)
    resp.raise_for_status()
    results = resp.json()["BEAAPI"].get("Results", {})
    # Errors come back with HTTP 200, either at the top or inside Results.
    error = results.get("Error") or resp.json()["BEAAPI"].get("Error")
    if error:
        raise SystemExit(f"BEA API error for {method} {params}: {error}")
    return results


def education_values(key, dataset, parameter):
    """[(code, description)] of the parameter values whose description mentions education."""
    values = bea(key, "GetParameterValues", datasetname=dataset, ParameterName=parameter)["ParamValue"]
    matches = []
    for v in values:
        code = v.get("Key") or v.get("key")
        desc = v.get("Desc") or v.get("desc") or ""
        if "educat" in desc.lower():
            matches.append((code, desc))
    print(f"{dataset} {parameter} values about education:")
    for code, desc in matches:
        print(f"  {code}: {desc}")
    if not matches:
        raise SystemExit(f"no {dataset} {parameter} mentions education; check the parameter list")
    return matches


def to_millions(r):
    """DataValue in millions of dollars; UNIT_MULT is the power of ten of the unit."""
    value = (r.get("DataValue") or "").replace(",", "").strip()
    if not value or not value.lstrip("-").replace(".", "").isdigit():
        return None  # "(D)" suppressed, "n.a.", etc.
    return round(float(value) * 10 ** (int(r.get("UNIT_MULT") or 6) - 6), 3)


def period_of(r):
    """2024Q3 -> 2024-Q3; annual stays 2024."""
    p = r["TimePeriod"]
    return f"{p[:4]}-{p[4:]}" if "Q" in p else p


def save_raw(name, data):
    path = RAW / "bea" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--key", default=os.environ.get("BEA_API_KEY"), help="BEA API key (or set BEA_API_KEY)")
    args = parser.parse_args()
    if not args.key:
        raise SystemExit("A BEA API key is needed: sign up at https://apps.bea.gov/API/signup/ "
                         "and pass --key or set BEA_API_KEY")
    years = ",".join(str(y) for y in range(START_YEAR, date.today().year + 1))
    rows = []

    # National totals, quarterly and annual.
    for code, desc in education_values(args.key, "ITA", "Indicator"):
        if not desc.lower().startswith("export"):
            continue  # education imports (US students abroad) are a different question
        data = bea(args.key, "GetData", datasetname="ITA", Indicator=code, AreaOrCountry="AllCountries",
                   Frequency="A,QSA,QNSA", Year=years)["Data"]
        save_raw(f"ita_{code}.json", data)
        for r in data:
            value = to_millions(r)
            if value is None:
                continue
            adj = {"QSA": "_sa", "QNSA": "_nsa"}.get(r.get("Frequency"), "")
            rows.append(dict(unit_type="national", unit_id="US", unit_name="United States",
                             period=period_of(r), measure=f"{code}_usd_millions{adj}", value=value,
                             source=f"BEA ITA: {desc}"))

    # Annual by partner country.
    for code, desc in education_values(args.key, "IntlServTrade", "TypeOfService"):
        data = bea(args.key, "GetData", datasetname="IntlServTrade", TypeOfService=code,
                   TradeDirection="Exports", Affiliation="AllAffiliations", AreaOrCountry="All",
                   Year=years)["Data"]
        save_raw(f"intlservtrade_{code}.json", data)
        for r in data:
            value = to_millions(r)
            if value is None:
                continue
            rows.append(dict(unit_type="country", unit_id=r.get("AreaOrCountry", ""),
                             unit_name=r.get("AreaOrCountry", ""), period=period_of(r),
                             measure=f"{code}_exports_usd_millions", value=value,
                             source=f"BEA International Services: {desc}"))
    write_long(rows, OUT / "bea_education.csv")


if __name__ == "__main__":
    main()
