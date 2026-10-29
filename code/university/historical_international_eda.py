"""Build source-linked historical international enrollment data and descriptive charts.

Numbers below are transcribed from the official university tables listed in
SOURCES. They are fall/academic-year stocks of enrolled students, not new
arrivals, visa issuances, or estimates of policy effects.

Run: python3 code/university/historical_international_eda.py
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
import tempfile

os.environ.setdefault("XDG_CACHE_HOME", str(Path(tempfile.gettempdir()) / "grad_research_cache"))
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "grad_research_mpl"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA = PROJECT_ROOT / "data/university/interim/historical_international_enrollment.csv"
OUT = PROJECT_ROOT / "data/university/outputs/historical_international_eda"
YEARS_OHIO = list(range(2019, 2026))
YEARS_MIT = list(range(2016, 2027))
YEARS_HILO = list(range(2011, 2027))
YEARS_MICHIGAN = list(range(2019, 2027))
YEARS_NEW_MEXICO = list(range(2021, 2026))
YEARS_BERKELEY = list(range(2021, 2026))

SOURCES = {
    "ohio_total": "https://www.ohio.edu/iea/student-data/totalint7yearenroll",
    "ohio_ug": "https://www.ohio.edu/iea/student-data/ugrad7yearenroll",
    "ohio_grad": "https://www.ohio.edu/iea/student-data/grad7yearenroll",
    "mit": "https://registrar.mit.edu/stats-reports/international-enrollment/all",
    "hilo": "https://hilo.hawaii.edu/international/YearToYearStatistics.php",
    "hilo_2026": "https://hilo.hawaii.edu/international/statistics.php",
    "dearborn": "https://umdearborn.edu/news/look-fall-2025-enrollment",
    "michigan_2019": "https://obp.umich.edu/wp-content/uploads/pubdata/michiganreports/Section%20245%20Report%20Card%20Fall%202021.pdf",
    "michigan_2020_2022": "https://obp.umich.edu/wp-content/uploads/pubdata/mandatoryreports/Section%20245%20Report%20Card%20Fall%202022.pdf",
    "michigan_2023_2025": "https://obp.umich.edu/wp-content/uploads/pubdata/mandatoryreports/Section_241_Report_Card_Fall_2025.pdf",
    "michigan_2026": "https://obp.umich.edu/wp-content/uploads/pubdata/factsfigures/enrollment_umaa_2026.pdf",
    "uis_2022_2023": "https://www.uis.edu/news/mid-semester-enrollment-retention-management-division-updates",
    "uis_2024": "https://www.uis.edu/news/university-illinois-springfield-enrollment-remains-stable-fall-semester-2024",
    "uis_2025": "https://www.uis.edu/news/uis-sees-growth-freshman-enrollment-fall-2025",
    "unm_2025": "https://global.unm.edu/assets/documents/current-student-house-2025.pdf",
    "unm_2024": "https://global.unm.edu/assets/documents/currentstudentstat2024.pdf",
    "unm_2023": "https://global.unm.edu/assets/documents/2023-current-student-stats.pdf",
    "unm_2022": "https://global.unm.edu/assets/documents/total-international-student-statistics-fall-2022.pdf",
    "unm_2021": "https://global.unm.edu/assets/documents/total-international-student-statistics-fall-2021.pdf",
    "berkeley_2025": "https://internationaloffice.berkeley.edu/sites/default/files/student-stats2025.pdf",
    "berkeley_2024": "https://internationaloffice.berkeley.edu/sites/default/files/student-stats2024.pdf",
    "berkeley_2023": "https://internationaloffice.berkeley.edu/sites/default/files/student-stats2023.pdf",
    "berkeley_2022": "https://internationaloffice.berkeley.edu/sites/default/files/student-stats2022.pdf",
    "berkeley_2021": "https://internationaloffice.berkeley.edu/sites/default/files/student-stats2021.pdf",
}

# Source-table order is chronological. Ohio University: total, UG, graduate,
# and India counts by level. The 2025 source tables have seven fall columns.
OHIO = {
    ("All countries", "All levels"): [1151, 976, 976, 997, 1069, 1110, 1045],
    ("All countries", "Undergraduate"): [378, 341, 275, 228, 223, 229, 210],
    ("All countries", "Graduate"): [773, 635, 701, 769, 846, 881, 835],
    ("India", "All levels"): [100, 86, 87, 93, 97, 110, 93],
    ("India", "Undergraduate"): [20, 17, 24, 21, 29, 35, 26],
    ("India", "Graduate"): [80, 69, 63, 72, 68, 75, 67],
}

MIT = {
    "All levels": [3365, 3413, 3411, 3387, 3274, 3489, 3513, 3505, 3455, 3475, 3364],
    "Undergraduate": [457, 521, 506, 472, 448, 481, 530, 505, 529, 529, 506],
    "Graduate": [2908, 2892, 2905, 2915, 2826, 3008, 2983, 3000, 2926, 2946, 2858],
}

HILO = [278, 263, 281, 274, 269, 251, 256, 247, 256, 198, 219, 220, 231, 227, 229, 234]

# Ann Arbor only. Each year's count comes from the latest of the selected
# official performance report cards; older editions sometimes revise a count.
MICHIGAN = {
    "Undergraduate": [2437, 2392, 2737, 2866, 2801, 2762, 2658, 2778],
    "Graduate": [4804, 4378, 5138, 6014, 6027, 5905, 5478, 4784],
}
MICHIGAN["All levels"] = [sum(MICHIGAN[level][i] for level in ("Undergraduate", "Graduate"))
                          for i in range(len(YEARS_MICHIGAN))]

# UNM's total includes exchange, intensive English, and certificate students;
# those students are not in its undergraduate or graduate rows.
NEW_MEXICO = {
    ("All countries", "All levels"): [1015, 1054, 1106, 1112, 1080],
    ("All countries", "Undergraduate"): [323, 300, 325, 376, 415],
    ("All countries", "Graduate"): [620, 644, 686, 637, 589],
    ("India", "All levels"): [122, 133, 155, 134, 99],
}

# Berkeley's annual report for 2025 repeats the *2023* India count (1,000)
# in its column labeled 2024. Use 896 from the actual Fall 2024 report.
BERKELEY = {
    ("All countries", "All levels"): [7845, 7956, 7835, 7355, 7302],
    ("India", "All levels"): [946, 1000, 1000, 896, 779],
}


def make_rows() -> list[dict]:
    rows = []
    def add(institution, years, values, level, country, url, definition):
        assert len(years) == len(values)
        for year, count in zip(years, values):
            rows.append({
                "institution": institution, "year": year, "period": "Fall",
                "measure": "enrolled_international_students", "academic_level": level,
                "country": country, "count": count, "source_url": url,
                "source_definition": definition,
            })
    for (country, level), values in OHIO.items():
        url = SOURCES["ohio_total"] if level == "All levels" else SOURCES["ohio_ug" if level == "Undergraduate" else "ohio_grad"]
        add("Ohio University", YEARS_OHIO, values, level, country, url,
            "University-published 7-year fall international enrollment; total stock, not new entrants.")
    for level, values in MIT.items():
        add("MIT", YEARS_MIT, values, level, "All countries", SOURCES["mit"],
            "MIT Registrar international enrollment; academic year labeled by its starting fall.")
    for year, count in zip(YEARS_HILO, HILO):
        add("University of Hawaiʻi at Hilo", [year], [count], "All levels", "All countries",
            SOURCES["hilo_2026" if year == 2026 else "hilo"],
            "International Student Services fall international enrollment total.")
    for level, values in MICHIGAN.items():
        for year, count in zip(YEARS_MICHIGAN, values):
            url = (SOURCES["michigan_2019"] if year == 2019 else
                   SOURCES["michigan_2020_2022"] if year <= 2022 else
                   SOURCES["michigan_2023_2025"] if year <= 2025 else
                   SOURCES["michigan_2026"])
            add("University of Michigan–Ann Arbor", [year], [count], level, "All countries", url,
                "Official fall international enrollment, Ann Arbor only; includes continuing students. "
                + ("Graduate includes 4,684 graduate plus 100 professional students."
                   if year == 2026 and level == "Graduate" else ""))
    for year, count in zip((2022, 2023, 2024, 2025), (645, 1005, 957, 715)):
        url = SOURCES["uis_2022_2023"] if year <= 2023 else SOURCES[f"uis_{year}"]
        add("University of Illinois Springfield", [year], [count], "All levels", "All countries", url,
            "Fall international enrollment after the first ten days of classes; "
            "2025 total sums published undergraduate and graduate international counts.")
    for level, values in (("Undergraduate", (82, 77)), ("Graduate", (875, 638))):
        add("University of Illinois Springfield", [2024, 2025], values, level, "All countries",
            SOURCES["uis_2025"],
            "International enrollment by level after the first ten days of fall classes; "
            "university news comparison.")
    for (country, level), values in NEW_MEXICO.items():
        for year, count in zip(YEARS_NEW_MEXICO, values):
            url = SOURCES[f"unm_{year}"] if country == "India" else SOURCES["unm_2025"]
            add("University of New Mexico", [year], [count], level, country, url,
                "UNM Global Education Office fall international enrollment; all-level total also "
                "includes intensive English, exchange/guest, and certificate students; excludes "
                "post-completion practical training.")
    for (country, level), values in BERKELEY.items():
        for year, count in zip(YEARS_BERKELEY, values):
            url = SOURCES[f"berkeley_{year}"] if country == "India" else SOURCES["berkeley_2025"]
            add("UC Berkeley", [year], [count], level, country, url,
                "Berkeley International Office fall enrolled nonimmigrant students, including "
                "undergraduate, graduate, and exchange students; since 2020, includes F-1/J-1 "
                "and other nonimmigrant visa types, not post-completion OPT/AT.")
    return rows


def validate(rows: list[dict]) -> None:
    seen = set()
    index = {}
    for row in rows:
        key = (row["institution"], row["year"], row["country"], row["academic_level"])
        if key in seen or row["count"] < 0:
            raise ValueError(f"Duplicate or invalid row: {key}")
        seen.add(key)
        index[key] = row["count"]
    for school, years, countries in (
        ("Ohio University", YEARS_OHIO, ("All countries", "India")),
        ("MIT", YEARS_MIT, ("All countries",)),
        ("University of Michigan–Ann Arbor", YEARS_MICHIGAN, ("All countries",)),
        ("University of Illinois Springfield", (2024, 2025), ("All countries",)),
    ):
        for year in years:
            for country in countries:
                total = index[(school, year, country, "All levels")]
                parts = sum(index[(school, year, country, level)] for level in ("Undergraduate", "Graduate"))
                if total != parts:
                    raise ValueError(f"Level totals do not reconcile: {school}, {year}, {country}")
    for year in YEARS_NEW_MEXICO:
        school = "University of New Mexico"
        total = index[(school, year, "All countries", "All levels")]
        parts = sum(index[(school, year, "All countries", level)]
                    for level in ("Undergraduate", "Graduate"))
        if parts > total:
            raise ValueError(f"UNM levels exceed total in {year}")
    for school, years in (("University of New Mexico", YEARS_NEW_MEXICO),
                          ("UC Berkeley", YEARS_BERKELEY)):
        for year in years:
            if index[(school, year, "India", "All levels")] > index[(school, year, "All countries", "All levels")]:
                raise ValueError(f"India exceeds total: {school}, {year}")


def series(rows, school, country="All countries", level="All levels"):
    return sorted((r for r in rows if r["institution"] == school and r["country"] == country
                   and r["academic_level"] == level), key=lambda r: r["year"])


def pct(a, b):
    return round(100 * (b / a - 1), 1) if a else None


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_summary(rows):
    selected = [
        ("Ohio University", "All countries", "All levels"),
        ("Ohio University", "India", "All levels"),
        ("Ohio University", "All countries", "Undergraduate"),
        ("Ohio University", "All countries", "Graduate"),
        ("Ohio University", "India", "Undergraduate"),
        ("Ohio University", "India", "Graduate"),
        ("MIT", "All countries", "All levels"),
        ("University of Hawaiʻi at Hilo", "All countries", "All levels"),
        ("University of Michigan–Ann Arbor", "All countries", "All levels"),
        ("University of Michigan–Ann Arbor", "All countries", "Undergraduate"),
        ("University of Michigan–Ann Arbor", "All countries", "Graduate"),
        ("University of Illinois Springfield", "All countries", "All levels"),
        ("University of Illinois Springfield", "All countries", "Undergraduate"),
        ("University of Illinois Springfield", "All countries", "Graduate"),
        ("University of New Mexico", "All countries", "All levels"),
        ("University of New Mexico", "India", "All levels"),
        ("University of New Mexico", "All countries", "Undergraduate"),
        ("University of New Mexico", "All countries", "Graduate"),
        ("UC Berkeley", "All countries", "All levels"),
        ("UC Berkeley", "India", "All levels"),
    ]
    summary = []
    for school, country, level in selected:
        values = {r["year"]: r["count"] for r in series(rows, school, country, level)}
        summary.append({
            "institution": school, "country": country, "academic_level": level,
            "count_2019": values.get(2019), "count_2024": values[2024],
            "count_2025": values[2025], "change_2024_2025": values[2025] - values[2024],
            "percent_change_2024_2025": pct(values[2024], values[2025]),
            "percent_change_2019_2025": pct(values[2019], values[2025]) if 2019 in values else None,
            "source_url": series(rows, school, country, level)[-1]["source_url"],
        })
    write_csv(OUT / "historical_2025_summary.csv", summary)
    return summary


def plot_trends(rows):
    schools = ("Ohio University", "MIT", "University of Hawaiʻi at Hilo",
               "University of Michigan–Ann Arbor", "University of Illinois Springfield",
               "University of New Mexico", "UC Berkeley")
    fig, axes = plt.subplots(len(schools), 1, figsize=(10, 21), sharex=False)
    for ax, school, color in zip(axes, schools,
                                 ("#226f92", "#a04f39", "#4b8068", "#73569a", "#be803d",
                                  "#2d8c83", "#9a5f76")):
        vals = series(rows, school)
        ax.plot([r["year"] for r in vals], [r["count"] for r in vals], marker="o", color=color, linewidth=2)
        ax.set_title(school, loc="left")
        ax.set_ylabel("International students")
        ax.set_ylim(bottom=0)
        ax.grid(axis="y", alpha=.2)
        ax.annotate(str(vals[-1]["count"]), (vals[-1]["year"], vals[-1]["count"]), xytext=(5, 4),
                    textcoords="offset points", fontsize=9)
    fig.suptitle("Fall international enrollment at seven universities", fontsize=15)
    fig.text(.5, .01, "Total enrolled students; definitions and campus sizes differ. Fall 2026 is available for three campuses.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .03, 1, .96))
    fig.savefig(OUT / "historical_trends.png", dpi=180)
    plt.close(fig)


def plot_ohio(rows):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for ax, country, title in zip(axes, ("All countries", "India"),
                                   ("All international students", "Students from India")):
        for level, color in (("Undergraduate", "#3b7897"), ("Graduate", "#b36542")):
            vals = series(rows, "Ohio University", country, level)
            ax.plot([r["year"] for r in vals], [r["count"] for r in vals], marker="o",
                    linewidth=2, label=level, color=color)
        ax.set_title(title, loc="left")
        ax.set_ylabel("Enrolled students")
        ax.grid(axis="y", alpha=.2)
        ax.legend(frameon=False)
    fig.suptitle("Ohio University: undergraduate and graduate international enrollment", fontsize=14)
    fig.text(.5, .01, "Fall enrollment stock by country; India is a subset of all countries, not an additional group.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, .94))
    fig.savefig(OUT / "ohio_levels_and_india.png", dpi=180)
    plt.close(fig)


def plot_indexed(rows):
    fig, ax = plt.subplots(figsize=(10, 5))
    for school, color in (("Ohio University", "#226f92"), ("MIT", "#a04f39"),
                          ("University of Hawaiʻi at Hilo", "#4b8068"),
                          ("University of Michigan–Ann Arbor", "#73569a"),
                          ("University of Illinois Springfield", "#be803d")):
        vals = [r for r in series(rows, school) if r["year"] >= 2019]
        if not vals or vals[0]["year"] != 2019:
            continue
        baseline = vals[0]["count"]
        ax.plot([r["year"] for r in vals], [100 * r["count"] / baseline for r in vals],
                marker="o", linewidth=2, color=color, label=school)
    ax.axhline(100, color="#777777", linewidth=1, linestyle="--")
    ax.set_title("International enrollment relative to each university's Fall 2019 level", loc="left")
    ax.set_ylabel("Index (2019 = 100)")
    ax.set_xticks(list(range(2019, 2027)))
    ax.grid(axis="y", alpha=.2)
    ax.legend(frameon=False)
    fig.text(.5, .015, "Equal baseline aids trend comparison; student counts and source definitions still differ.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, 1))
    fig.savefig(OUT / "indexed_trends_2019.png", dpi=180)
    plt.close(fig)


def plot_india(rows):
    fig, ax = plt.subplots(figsize=(10, 5))
    for school, color in (("Ohio University", "#226f92"),
                          ("University of New Mexico", "#2d8c83"),
                          ("UC Berkeley", "#9a5f76")):
        vals = [r for r in series(rows, school, country="India") if r["year"] >= 2021]
        ax.plot([r["year"] for r in vals], [r["count"] for r in vals],
                marker="o", linewidth=2, color=color, label=school)
    ax.set_title("Students from India enrolled in fall, 2021–2025", loc="left")
    ax.set_ylabel("Enrolled students")
    ax.set_xticks(list(range(2021, 2026)))
    ax.grid(axis="y", alpha=.2)
    ax.legend(frameon=False)
    fig.text(.5, .01, "Country series are subsets of each university's international total; definitions differ.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, 1))
    fig.savefig(OUT / "india_trends.png", dpi=180)
    plt.close(fig)


def write_report(summary):
    d = {(r["institution"], r["country"], r["academic_level"]): r for r in summary}
    ohio = d[("Ohio University", "All countries", "All levels")]
    india = d[("Ohio University", "India", "All levels")]
    mit = d[("MIT", "All countries", "All levels")]
    hilo = d[("University of Hawaiʻi at Hilo", "All countries", "All levels")]
    michigan = d[("University of Michigan–Ann Arbor", "All countries", "All levels")]
    michigan_grad = d[("University of Michigan–Ann Arbor", "All countries", "Graduate")]
    uis = d[("University of Illinois Springfield", "All countries", "All levels")]
    uis_grad = d[("University of Illinois Springfield", "All countries", "Graduate")]
    unm = d[("University of New Mexico", "All countries", "All levels")]
    unm_india = d[("University of New Mexico", "India", "All levels")]
    berkeley = d[("UC Berkeley", "All countries", "All levels")]
    berkeley_india = d[("UC Berkeley", "India", "All levels")]
    text = f"""# Historical international-student enrollment: descriptive EDA

## What the university data show

| University / group | Fall 2024 | Fall 2025 | Change |
|---|---:|---:|---:|
| Ohio University, all international | {ohio['count_2024']:,} | {ohio['count_2025']:,} | {ohio['percent_change_2024_2025']:+.1f}% |
| Ohio University, India | {india['count_2024']:,} | {india['count_2025']:,} | {india['percent_change_2024_2025']:+.1f}% |
| MIT, all international | {mit['count_2024']:,} | {mit['count_2025']:,} | {mit['percent_change_2024_2025']:+.1f}% |
| UH Hilo, all international | {hilo['count_2024']:,} | {hilo['count_2025']:,} | {hilo['percent_change_2024_2025']:+.1f}% |
| U-M Ann Arbor, all international | {michigan['count_2024']:,} | {michigan['count_2025']:,} | {michigan['percent_change_2024_2025']:+.1f}% |
| U-M Ann Arbor, graduate | {michigan_grad['count_2024']:,} | {michigan_grad['count_2025']:,} | {michigan_grad['percent_change_2024_2025']:+.1f}% |
| Illinois Springfield, all international | {uis['count_2024']:,} | {uis['count_2025']:,} | {uis['percent_change_2024_2025']:+.1f}% |
| Illinois Springfield, international graduate | {uis_grad['count_2024']:,} | {uis_grad['count_2025']:,} | {uis_grad['percent_change_2024_2025']:+.1f}% |
| New Mexico, all international | {unm['count_2024']:,} | {unm['count_2025']:,} | {unm['percent_change_2024_2025']:+.1f}% |
| New Mexico, India | {unm_india['count_2024']:,} | {unm_india['count_2025']:,} | {unm_india['percent_change_2024_2025']:+.1f}% |
| UC Berkeley, all international | {berkeley['count_2024']:,} | {berkeley['count_2025']:,} | {berkeley['percent_change_2024_2025']:+.1f}% |
| UC Berkeley, India | {berkeley_india['count_2024']:,} | {berkeley_india['count_2025']:,} | {berkeley_india['percent_change_2024_2025']:+.1f}% |

Ohio, U-M Ann Arbor, Illinois Springfield, New Mexico, and UC Berkeley had falling international totals in 2025, though the size of the declines varied. MIT and UH Hilo were approximately flat. India counts fell faster than all-country totals at Ohio, New Mexico, and Berkeley. These are contrasting institutional patterns, not a national estimate.

## Newly available Fall 2026 counts

| University | Fall 2025 | Fall 2026 | Change |
|---|---:|---:|---:|
| MIT | 3,475 | 3,364 | -111 (-3.2%) |
| UH Hilo | 229 | 234 | +5 (+2.2%) |
| U-M Ann Arbor | 8,136 | 7,562 | -574 (-7.1%) |

MIT's registrar publishes 506 undergraduate and 2,858 graduate international students for 2026–27. UH Hilo's International Student Services reports 234 in Fall 2026. U-M Ann Arbor's 2026 enrollment report counts 2,778 international undergraduates, 4,684 graduate students, and 100 professional students. This dataset combines the latter two as 4,784 to match the earlier Ann Arbor graduate series. Ohio, Illinois Springfield, New Mexico, and Berkeley do not yet have a comparable published 2026 international headcount in the sources reviewed here, so their 2026 series remain blank.

## How to read this for the project

- These series count *all enrolled international students* in fall, including continuing students. They do not measure new student arrivals or individual visa outcomes.
- Ohio, New Mexico, and Berkeley now have India-specific historical series. Ohio also has an India undergraduate/graduate split.
- The [Michigan–Dearborn fall 2025 announcement]({SOURCES['dearborn']}) reports a 44% decline in **new** international enrollment and 144 expected international students unable to enroll. This is a different measure and is excluded from the total-enrollment trend chart.
- U-M Ann Arbor's official performance report cards supply a 2019–2025 series, extended with the 2026 enrollment report. The 2025 report card counts 8,136 international students; the [International Center annual report](https://internationalcenter.umich.edu/sites/default/files/info/2025_Annual_Report.pdf) gives 8,091. This dataset uses the report-card series and matching enrollment categories consistently.
- Illinois Springfield's all-level series runs from 2022–2025. Its 2025 total of 715 is derived from the university's published 638 international graduate and 77 international undergraduate students. The 2024 components also reconcile to its published total of 957.
- New Mexico's all-level series includes exchange/guest, intensive English, and certificate students, while its undergraduate and graduate rows do not. Its 2025 report's India change column says -56 for 2024–2025, but the annual country tables show 134 in 2024 and 99 in 2025, a change of -35. This dataset uses the annual counts.
- Berkeley's 2025 report repeats the **2023** India count of 1,000 in its column labeled 2024. Its actual 2024 report shows 896. This dataset uses 896 for 2024 and 779 for 2025. Berkeley includes other nonimmigrant visa types as well as F-1/J-1 students.
- A 2025 change is temporally consistent with several possible causes, including policy, student choice, and university-specific conditions. These data alone cannot identify a policy effect.
- Definitions differ across universities. Compare each institution with its own prior years; do not sum the institutions or treat the seven-school average as representative of the U.S.

## Source tables

- [Ohio University, seven-year international total and country]({SOURCES['ohio_total']})
- [Ohio University, undergraduate]({SOURCES['ohio_ug']}) and [graduate]({SOURCES['ohio_grad']})
- [MIT Registrar, international enrollment by level]({SOURCES['mit']})
- [UH Hilo, year-to-year international enrollment]({SOURCES['hilo']}) and [Fall 2026 statistics]({SOURCES['hilo_2026']})
- [U-M Ann Arbor report cards for 2019]({SOURCES['michigan_2019']}), [2020–2022]({SOURCES['michigan_2020_2022']}), [2023–2025]({SOURCES['michigan_2023_2025']}), and [2026 enrollment report]({SOURCES['michigan_2026']}). Older report cards occasionally give different numbers for the same year; this series uses the selected report listed in each CSV row.
- [Illinois Springfield, 2022–2023 totals]({SOURCES['uis_2022_2023']}), [2024 total]({SOURCES['uis_2024']}), and [2024–2025 level comparison]({SOURCES['uis_2025']})
- [New Mexico, 2025 report with five-year enrollment and level tables]({SOURCES['unm_2025']}) and [2024 country table]({SOURCES['unm_2024']})
- [Berkeley, 2025 report with historical enrollment trend]({SOURCES['berkeley_2025']}) and [2024 country table]({SOURCES['berkeley_2024']})

## Additional verified university sources for expansion

- [University of Illinois Urbana-Champaign international statistics](https://isss.illinois.edu/about/statistics/) has annual reports through Fall 2025 and an archive back to Fall 2011. Its dashboard explicitly covers full-time, in-person students, so it needs a separate definition label.
- [University of Toledo fall enrollment reports](https://www.utoledo.edu/offices/institutional-research/home/enrollments.html) list annual reports from Fall 2011 through Fall 2025. Extract the international/nonresident category consistently before adding it to this panel.
- [Salisbury University FactBook](https://www.salisbury.edu/administration/university-analysis-reporting-and-assessment/reporting/factbook-pages.aspx) publishes 2025 international counts by country of origin and historical institutional demographics.
- [IPEDS complete data files](https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx) offer downloadable cross-institution Fall Enrollment CSVs; the latest Fall Enrollment year shown there is 2024, so they cannot yet supply the 2025 comparison in this report.

The CSV contains each year, campus, level, country scope, original count, definition, and source URL. `historical_2025_summary.csv` contains the within-series changes. Charts: `historical_trends.png`, `indexed_trends_2019.png` (schools with a 2019 baseline), `ohio_levels_and_india.png`, and `india_trends.png`.
"""
    (OUT / "findings.md").write_text(text, encoding="utf-8")


def main():
    rows = make_rows()
    validate(rows)
    DATA.parent.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    write_csv(DATA, rows)
    summary = write_summary(rows)
    plot_trends(rows)
    plot_indexed(rows)
    plot_ohio(rows)
    plot_india(rows)
    write_report(summary)
    print(f"Wrote {len(rows)} source-linked observations to {DATA} and EDA to {OUT}")


if __name__ == "__main__":
    main()
