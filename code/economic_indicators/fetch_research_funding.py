"""Federal research grant obligations to research universities
Source: USAspending.gov API, https://api.usaspending.gov/ (no key)

"""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from build_exposure import IPEDS, latest_release
from common import OUT, RAW, START_YEAR, STOP_DATE, read_csv_in_zip, write_long

API = "https://api.usaspending.gov/api/v2/search/spending_over_time/"
GRANTS = ["02", "03", "04", "05"]  # block, formula, project grants, cooperative agreements
NIH = {"type": "awarding", "tier": "subtier", "name": "National Institutes of Health"}
NSF = {"type": "awarding", "tier": "toptier", "name": "National Science Foundation"}
OTHER = [{"type": "awarding", "tier": "toptier", "name": n} for n in
         ("Department of Defense", "Department of Energy", "National Aeronautics and Space Administration")]
GROUPS = {"nih": [NIH], "nsf": [NSF], "research": [NIH, NSF] + OTHER}
RESEARCH_CARNEGIE = {"15": "R1", "16": "R2"}


def research_universities():
    _, path = latest_release(lambda y: IPEDS.format(f"HD{y}"), lambda y: f"ipeds/HD{y}.zip", START_YEAR)
    # Some institutions list several UEIs, separated by "|"; all of them are searched.
    return [{"unitid": r["UNITID"], "name": r["INSTNM"], "ueis": [u.strip() for u in r["UEIS"].split("|") if u.strip()],
             "carnegie": RESEARCH_CARNEGIE[r["C21BASIC"]]}
            for r in read_csv_in_zip(path) if r["C21BASIC"] in RESEARCH_CARNEGIE and r["UEIS"].strip()]


def monthly(ueis, group, start, stop, refresh):
    """[(YYYY-MM, amount)] for one university and agency group, cached in data/raw."""
    cache = RAW / "usaspending" / f"{'-'.join(ueis)}_{group}_{start}_{stop}.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))
    body = {"group": "month", "filters": {
        "time_period": [{"start_date": start, "end_date": stop}], "award_type_codes": GRANTS,
        "recipient_search_text": ueis, "agencies": GROUPS[group]}}
    # The API rate-limits and sometimes drops connections under load; back off and retry.
    for attempt in range(6):
        try:
            resp = requests.post(API, json=body, timeout=180)
        except requests.ConnectionError:
            if attempt == 5:
                raise
            time.sleep(5 * 2 ** attempt)
            continue
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(5 * 2 ** attempt)
    resp.raise_for_status()
    out = []
    for r in resp.json()["results"]:
        # USAspending months are fiscal: month 1 is October of the previous calendar year.
        fy, fm = int(r["time_period"]["fiscal_year"]), int(r["time_period"]["month"])
        year, month = (fy - 1, fm + 9) if fm <= 3 else (fy, fm - 3)
        out.append((f"{year}-{month:02d}", r["aggregated_amount"]))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out), encoding="utf-8")
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--refresh", action="store_true", help="ignore cached responses (to get new months)")
    parser.add_argument("--stop", default=STOP_DATE, help="last date of the study (YYYY-MM-DD)")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()

    unis = research_universities()
    print(f"{len(unis)} R1/R2 universities x {len(GROUPS)} agency groups")
    start = f"{START_YEAR}-01-01"
    jobs = {(u["unitid"], g): u for u in unis for g in GROUPS}
    rows, failed, failed_keys = [], [], set()
    with ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(monthly, u["ueis"], g, start, args.stop, args.refresh): (u, g) for (_, g), u in jobs.items()}
        for i, f in enumerate(as_completed(futures), 1):
            u, g = futures[f]
            try:
                series = f.result()
            except Exception as e:
                failed.append(f'{u["name"]} ({g}): {e}')
                failed_keys.add((u["unitid"], g))
                continue
            for period, amount in series:
                if period + "-01" < args.stop:  # a month starting on the stop date would hold one day
                    rows.append(dict(unit_type="institution", unit_id=u["unitid"], unit_name=u["name"],
                                     period=period, measure=f"{g}_grant_obligations_usd", value=round(amount, 2),
                                     source=f"USAspending ({u['carnegie']}, UEI {' '.join(u['ueis'])})"))
            if i % 100 == 0:
                print(f"  {i}/{len(futures)} done")
    # USAspending leaves out months with no awards; write those as zero, up to the
    # last month any university has data for.
    last = max(r["period"] for r in rows)
    months = [f"{y}-{m:02d}" for y in range(START_YEAR, int(last[:4]) + 1) for m in range(1, 13)
              if f"{y}-{m:02d}" <= last]
    have = {(r["unit_id"], r["measure"], r["period"]) for r in rows}
    for u in unis:
        for g in GROUPS:
            if (u["unitid"], g) in failed_keys:
                continue  # unknown, not zero
            measure = f"{g}_grant_obligations_usd"
            for p in months:
                if (u["unitid"], measure, p) not in have:
                    rows.append(dict(unit_type="institution", unit_id=u["unitid"], unit_name=u["name"], period=p,
                                     measure=measure, value=0.0,
                                     source=f"USAspending ({u['carnegie']}, UEI {' '.join(u['ueis'])})"))
    rows.sort(key=lambda r: (r["unit_id"], r["measure"], r["period"]))
    write_long(rows, OUT / "research_funding.csv")
    if failed:
        print(f"{len(failed)} requests failed (rerun to retry); first ones:")
        for f in failed[:5]:
            print("  ", f[:200])


if __name__ == "__main__":
    main()
