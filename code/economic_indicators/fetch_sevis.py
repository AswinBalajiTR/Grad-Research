"""Active F-1 and M-1 students in SEVIS each month, by country of citizenship

Source: SEVIS Data Mapping Tool, Study in the States (DHS/SEVP),
  https://studyinthestates.dhs.gov/sevis-data-mapping-tool (no key)

"""

import argparse
import json
import re
from datetime import datetime

import requests

from common import HEADERS, OUT, START_YEAR, STOP_DATE, download, write_long

PAGE = "https://studyinthestates.dhs.gov/sevis-data-mapping-tool"
SITE = "https://studyinthestates.dhs.gov"
SOURCE = "SEVIS Data Mapping Tool (DHS/SEVP)"
LEVELS = ["associate", "bachelors", "masters", "doctorate", "flight_school", "high_school", "language_training",
          "other", "other_vocational_school", "primary", "secondary"]
STATE = re.compile(r"^[A-Z]{2}$")  # state columns are keyed by postal code


def data_file(refresh):
    """Path of the current JSON file, found from the page's data-json attribute."""
    html = requests.get(PAGE, headers=HEADERS, timeout=120).text
    href = re.search(r'data-json="([^"]+\.json)"', html)
    if not href:
        raise SystemExit(f"no data-json link on {PAGE}; the page layout has changed")
    print(f"data file: {href.group(1)}")
    return download(SITE + href.group(1), "sevis/" + href.group(1).rsplit("/", 1)[1], refresh=refresh)


def number(v):
    return int(float(v or 0))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--countries", default="IN,CN", help="countries (codes) to break down by US state")
    parser.add_argument("--refresh", action="store_true", help="download the data file again")
    parser.add_argument("--stop", default=STOP_DATE, help="last date of the study (YYYY-MM-DD)")
    args = parser.parse_args()
    by_state = [c.strip().upper() for c in args.countries.split(",")]

    data = json.loads(data_file(args.refresh).read_text(encoding="utf-8-sig"))
    rows = []
    for label in data["reporting_periods"]:
        period = datetime.strptime(label, "%B %Y").strftime("%Y-%m")
        if not f"{START_YEAR}-01" <= period <= args.stop[:7]:
            continue
        p = data[label]
        states = [k for k in p if STATE.match(k)]
        state_totals = dict.fromkeys(states, 0)
        for i, code in enumerate(p["codes"]):
            name = p["coc"][i]
            values = {"active_students": number(p["active_students"][i]),
                      "stem_students": number(p["stem_male"][i]) + number(p["stem_female"][i])}
            for level in LEVELS:
                if level in p:
                    values[f"{level}_students"] = number(p[level][i])
                    values[f"stem_{level}_students"] = number(p.get(f"stem_{level}", [0] * len(p["codes"]))[i])
            rows += [dict(unit_type="country", unit_id=code, unit_name=name, period=period, measure=m,
                          value=v, source=SOURCE) for m, v in values.items()]
            for s in states:
                state_totals[s] += number(p[s][i])
                if code in by_state:
                    rows.append(dict(unit_type="state", unit_id=s, unit_name=s, period=period,
                                     measure=f"active_students_from_{code}", value=number(p[s][i]), source=SOURCE))
        rows += [dict(unit_type="state", unit_id=s, unit_name=s, period=period, measure="active_students",
                      value=n, source=SOURCE) for s, n in state_totals.items()]
    write_long(rows, OUT / "sevis.csv")


if __name__ == "__main__":
    main()
