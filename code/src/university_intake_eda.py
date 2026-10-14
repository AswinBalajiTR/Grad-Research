"""Descriptive EDA for the project's verified university intake observations.

Run from the repository root or any directory:
    python3 code/src/university_intake_eda.py

Requires matplotlib. Outputs are descriptive and do not estimate policy effects.
"""

from __future__ import annotations

import argparse
import csv
import os
from dataclasses import dataclass
from pathlib import Path
import tempfile

os.environ.setdefault("XDG_CACHE_HOME", str(Path(tempfile.gettempdir()) / "grad_research_cache"))
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "grad_research_mpl"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


CODE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = CODE_DIR / "data/interim/university_intake/intake_observations.csv"
DEFAULT_OUTPUT = CODE_DIR / "outputs/university_intake_eda"
REQUIRED_COLUMNS = {
    "source_id", "institution", "reporting_year", "period", "cohort",
    "academic_level", "country", "metric", "value", "source_url", "quality_flag",
}


@dataclass(frozen=True)
class Series:
    source_id: str
    metric: str
    level: str
    label: str
    cohort_group: str


# Explicit source/metric selection avoids counting both subtotals and totals.
SERIES = (
    Series("S08", "enrolled", "Undergraduate first-year", "Bucknell", "First-year"),
    Series("S14", "new_enrolled", "Undergraduate first-year", "Kennesaw State", "First-year"),
    Series("S12", "new_enrolled", "Undergraduate first-year", "Michigan Ann Arbor", "First-year"),
    Series("S16", "new_enrolled", "Undergraduate first-year", "USC", "First-year"),
    Series("S15", "enrolled", "Undergraduate first-year", "Washington College", "First-year"),
    Series("S13", "new_transfer_enrolled", "Undergraduate transfer", "Michigan Ann Arbor", "Transfer"),
    Series("S03", "new_registered", "All levels", "Cincinnati", "All new / registered"),
    Series("S01", "registered", "All levels", "New Mexico", "All new / registered"),
    Series("S09", "new_or_transfer_enrolled", "All levels", "Washburn", "New + transfer"),
    Series("S02", "new_enrolled", "All levels", "Duke", "All new / registered"),
    Series("S17", "new_enrolled", "All levels", "South Carolina", "All new / registered"),
    Series("S18", "new_enrolled", "Undergraduate first-year", "Augustana", "First-year"),
)


def read_rows(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f"Input not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"Input is missing columns: {', '.join(sorted(missing))}")
        rows = []
        for line, row in enumerate(reader, start=2):
            try:
                row["reporting_year"] = int(row["reporting_year"])
                row["value"] = int(row["value"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid year or count on CSV line {line}") from exc
            if row["value"] < 0:
                raise ValueError(f"Negative count on CSV line {line}")
            rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def lookup(rows: list[dict], source_id: str, year: int, metric: str, level: str,
           country: str = "All countries") -> dict | None:
    found = [r for r in rows if r["source_id"] == source_id
             and r["reporting_year"] == year and r["metric"] == metric
             and r["academic_level"] == level and r["country"] == country]
    if len(found) > 1:
        raise ValueError(f"Duplicate observation: {source_id}, {year}, {metric}, {level}, {country}")
    return found[0] if found else None


def pct_change(old: int, new: int) -> float | None:
    return round((new / old - 1) * 100, 1) if old else None


def selected_series(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    annual, changes = [], []
    for spec in SERIES:
        by_year = {}
        for year in range(2021, 2026):
            row = lookup(rows, spec.source_id, year, spec.metric, spec.level)
            if row is None:
                continue
            by_year[year] = row["value"]
            annual.append({
                "university": spec.label, "source_id": spec.source_id,
                "population_scope": "International students (source-defined)",
                "country_scope": row["country"],
                "cohort_group": spec.cohort_group, "academic_level": spec.level,
                "metric": spec.metric, "year": year, "count": row["value"],
                "period": row["period"], "source_cohort": row["cohort"],
                "definition_note": row["definition_note"],
                "quality_flag": row["quality_flag"], "source_url": row["source_url"],
            })
        if not by_year:
            raise ValueError(f"No observations for configured series {spec.source_id}")
        for year in sorted(by_year):
            if year - 1 not in by_year:
                continue
            previous = by_year[year - 1]
            changes.append({
                "university": spec.label, "source_id": spec.source_id,
                "population_scope": "International students (source-defined)",
                "country_scope": "All countries",
                "cohort_group": spec.cohort_group, "metric": spec.metric,
                "from_year": year - 1, "to_year": year,
                "from_count": previous, "to_count": by_year[year],
                "absolute_change": by_year[year] - previous,
                "percent_change": pct_change(previous, by_year[year]),
                "small_2024_base": "yes" if year == 2025 and previous < 30 else "no",
            })
    return annual, changes


def snapshot_2025(annual: list[dict]) -> list[dict]:
    """One source-linked row per available 2025 international-student series."""
    prior = {r["source_id"]: r for r in annual if r["year"] == 2024}
    snapshot = []
    for row in (r for r in annual if r["year"] == 2025):
        old = prior.get(row["source_id"])
        old_count = old["count"] if old else None
        snapshot.append({
            "university": row["university"], "source_id": row["source_id"],
            "population_scope": row["population_scope"],
            "country_scope": row["country_scope"],
            "cohort_group": row["cohort_group"],
            "academic_level": row["academic_level"], "source_cohort": row["source_cohort"],
            "metric": row["metric"], "period_2025": row["period"],
            "count_2024": old_count, "count_2025": row["count"],
            "absolute_change": row["count"] - old_count if old_count is not None else None,
            "percent_change": pct_change(old_count, row["count"]) if old_count is not None else None,
            "definition_note": row["definition_note"], "quality_flag": row["quality_flag"],
            "source_url": row["source_url"],
        })
    return snapshot


def funnel_tables(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    funnels = []
    for source_id, name, admit_metric in (
        ("S08", "Bucknell", "admitted"),
        ("S15", "Washington College", "accepted"),
    ):
        for year in range(2021, 2026):
            applied = lookup(rows, source_id, year, "applied", "Undergraduate first-year")
            admitted = lookup(rows, source_id, year, admit_metric, "Undergraduate first-year")
            enrolled = lookup(rows, source_id, year, "enrolled", "Undergraduate first-year")
            if not all((applied, admitted, enrolled)):
                continue
            a, b, c = applied["value"], admitted["value"], enrolled["value"]
            funnels.append({
                "university": name, "year": year, "applied": a, "admitted": b,
                "population_scope": "International students (source-defined)",
                "country_scope": "All countries",
                "enrolled": c, "admit_rate_pct": round(100 * b / a, 1) if a else None,
                "yield_pct": round(100 * c / b, 1) if b else None,
                "enrolled_per_applicant_pct": round(100 * c / a, 1) if a else None,
                "source_url": applied["source_url"],
            })
    # UNM's denominator is admitted AND issued immigration documents, not all admits.
    document_conversion = []
    for year in range(2021, 2026):
        issued = lookup(rows, "S01", year, "admitted_issued_documents", "All levels")
        registered = lookup(rows, "S01", year, "registered", "All levels")
        if issued and registered:
            a, b = issued["value"], registered["value"]
            document_conversion.append({
                "university": "New Mexico", "year": year,
                "population_scope": "International students (source-defined)",
                "country_scope": "All countries",
                "admitted_issued_documents": a, "registered": b,
                "registered_per_documents_pct": round(100 * b / a, 1) if a else None,
                "source_url": issued["source_url"],
            })
    return funnels, document_conversion


def level_changes(rows: list[dict]) -> list[dict]:
    groups = (
        ("S03", "Cincinnati", "new_registered", ("Undergraduate", "Graduate")),
        ("S01", "New Mexico", "registered", ("Bachelor", "Master", "Doctorate")),
    )
    result = []
    for source_id, name, metric, levels in groups:
        for level in levels:
            before = lookup(rows, source_id, 2024, metric, level)
            after = lookup(rows, source_id, 2025, metric, level)
            if before and after:
                result.append({
                    "university": name, "academic_level": level, "metric": metric,
                    "population_scope": "International students (source-defined)",
                    "country_scope": "All countries",
                    "count_2024": before["value"], "count_2025": after["value"],
                    "absolute_change": after["value"] - before["value"],
                    "percent_change": pct_change(before["value"], after["value"]),
                    "source_url": after["source_url"],
                })
    return result


def plot_trends(annual: list[dict], output: Path) -> None:
    complete = []
    for spec in SERIES:
        points = [r for r in annual if r["source_id"] == spec.source_id]
        if len(points) >= 4:
            complete.append((spec, sorted(points, key=lambda r: r["year"])))
    fig, axes = plt.subplots(3, 3, figsize=(13, 10), sharex=True)
    for ax, (spec, points) in zip(axes.flat, complete):
        years = [p["year"] for p in points]
        counts = [p["count"] for p in points]
        ax.plot(years, counts, color="#35698c", marker="o", linewidth=2)
        ax.scatter([years[-1]], [counts[-1]], color="#c34c33", s=52, zorder=3)
        ax.set_title(f"{spec.label} · {spec.cohort_group}", loc="left", fontsize=10)
        ax.set_ylim(bottom=0)
        ax.margins(x=0.1, y=0.16)
        ax.grid(axis="y", alpha=0.25)
        ax.annotate(str(counts[-1]), (years[-1], counts[-1]), xytext=(4, 5),
                    textcoords="offset points", fontsize=8)
        ax.set_xticks(years)
    for ax in axes.flat[len(complete):]:
        ax.axis("off")
    fig.suptitle("International student intake: published counts, 2021–2025", fontsize=15)
    fig.text(0.5, 0.015,
             "Each panel uses its university's definition. Cincinnati labels years without specifying fall.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_2025_changes(changes: list[dict], output: Path) -> None:
    items = sorted((r for r in changes if r["to_year"] == 2025
                    and r["percent_change"] is not None),
                   key=lambda r: r["percent_change"])
    labels = [f"{r['university']} · {r['cohort_group']}" for r in items]
    values = [r["percent_change"] for r in items]
    colors = ["#b84b42" if v < 0 else "#3f806b" for v in values]
    fig, ax = plt.subplots(figsize=(11, max(5, len(items) * 0.58 + 1)))
    bars = ax.barh(labels, values, color=colors)
    ax.axvline(0, color="#333333", linewidth=1)
    ax.bar_label(bars, labels=[f"{v:+.1f}%" for v in values], padding=4, fontsize=9)
    ax.set_xlim(min(-60, min(values) - 15), max(70, max(values) + 15))
    ax.set_xlabel("Change in international student count, 2024 to 2025 (%)")
    ax.set_title("International student intake varies by university and cohort", loc="left", fontsize=14)
    ax.grid(axis="x", alpha=0.2)
    fig.text(0.5, 0.012,
             "Within-university descriptive changes only; cohorts and reporting periods differ.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_yield(funnels: list[dict], output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharex=True)
    for ax, name in zip(axes, ("Bucknell", "Washington College")):
        points = sorted((r for r in funnels if r["university"] == name),
                        key=lambda r: r["year"])
        ax.plot([p["year"] for p in points], [p["yield_pct"] for p in points],
                marker="o", color="#35698c", linewidth=2)
        ax.set_title(name, loc="left")
        ax.set_ylim(bottom=0)
        ax.set_xticks([p["year"] for p in points])
        ax.grid(axis="y", alpha=0.25)
        ax.set_ylabel("Enrolled / admitted (%)")
        if points:
            ax.annotate(f"{points[-1]['yield_pct']:.1f}%", (points[-1]["year"], points[-1]["yield_pct"]),
                        xytext=(5, 5), textcoords="offset points", fontsize=9)
    fig.suptitle("International first-year admission yield", fontsize=14)
    fig.text(0.5, 0.01,
             "Washington College enrolls very small numbers; yield changes cannot identify why students did not enroll.",
             ha="center", fontsize=8)
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_levels(levels: list[dict], output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for ax, name in zip(axes, ("Cincinnati", "New Mexico")):
        part = [r for r in levels if r["university"] == name]
        positions = list(range(len(part)))
        ax.bar([x - 0.18 for x in positions], [r["count_2024"] for r in part],
               width=0.36, label="2024", color="#9eb4c2")
        ax.bar([x + 0.18 for x in positions], [r["count_2025"] for r in part],
               width=0.36, label="2025", color="#35698c")
        ax.set_xticks(positions, [r["academic_level"] for r in part])
        ax.set_title(name, loc="left")
        ax.set_ylabel("New registrations")
        ax.grid(axis="y", alpha=0.2)
        ax.legend(frameon=False)
    fig.suptitle("International student intake by academic level", fontsize=14)
    fig.text(0.5, 0.01,
             "Cincinnati's source identifies years but does not explicitly label them as fall terms.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, 0.06, 1, 0.94))
    fig.savefig(output, dpi=180)
    plt.close(fig)


def write_report(path: Path, rows: list[dict], changes: list[dict],
                 funnels: list[dict], levels: list[dict]) -> None:
    current = {r["source_id"]: r for r in changes if r["to_year"] == 2025}
    funnel = {(r["university"], r["year"]): r for r in funnels}
    level = {(r["university"], r["academic_level"]): r for r in levels}
    def change(source_id: str) -> str:
        r = current[source_id]
        return f"{r['from_count']} → {r['to_count']} ({r['percent_change']:+.1f}%)"
    def level_text(name: str, academic_level: str) -> str:
        r = level[(name, academic_level)]
        return f"{r['count_2024']} → {r['count_2025']} ({r['percent_change']:+.1f}%)"
    bucknell_2024 = funnel[("Bucknell", 2024)]["yield_pct"]
    bucknell_2025 = funnel[("Bucknell", 2025)]["yield_pct"]
    flagged = sum(bool(r["quality_flag"]) for r in rows)
    lines = [
        "# International student intake: descriptive findings",
        "",
        "These findings describe published institutional counts of international students, using each source's definition. They do not estimate the causal effect of a policy.",
        "The main comparison is 2024 to 2025, with 2021–2024 shown for historical context.",
        "Every observation in the current input covers all countries combined. No India-specific intake result can be calculated from this table.",
        "",
        "## Patterns worth presenting",
        "",
        f"- The direction is mixed. Michigan Ann Arbor first-years: {change('S12')}; its new transfers: {change('S13')}. These are separate cohorts.",
        f"- Cincinnati's new registrations: {change('S03')}. Graduate registrations changed {level_text('Cincinnati', 'Graduate')}; undergraduate registrations changed {level_text('Cincinnati', 'Undergraduate')}. Cincinnati does not specify a fall term on this page.",
        f"- New Mexico's total new registrations: {change('S01')}. Master's registrations changed {level_text('New Mexico', 'Master')}, while bachelor's registrations changed {level_text('New Mexico', 'Bachelor')}.",
        f"- Bucknell international first-year admission yield fell from {bucknell_2024:.1f}% to {bucknell_2025:.1f}% ({bucknell_2025-bucknell_2024:+.1f} percentage points), despite more admissions. This is an enrollment conversion pattern, not an identified visa effect.",
        "",
        "## Interpretation limits",
        "",
        "- The present data cannot show how many students came from India or how Indian students' intake changed. That requires institution-level counts broken out by country and year.",
        "- Do not sum universities or mix first-year, transfer, and all-new cohorts into one intake total.",
        "- A change in enrollment cannot identify whether a student was denied a visa, deferred, enrolled elsewhere, or changed plans.",
        "- 2024 and 2025 are single annual observations; other recruitment and institutional changes may explain differences.",
        "- Washington College's 2024 first-year international base was 11 students, so its percentage change is unstable.",
        f"- {flagged} input rows have source quality flags. UNM's reported no-shows do not reconcile with its admitted/document-issued minus registered counts for some groups. The script excludes no-shows from funnel calculations.",
        "",
        "## Files",
        "",
        "- `international_2025_snapshot.csv`: one 2025 international-student row per selected university cohort, with 2024 comparison where available and explicit country scope.",
        "- `annual_intake_series.csv`: selected nonduplicative intake series and source URLs.",
        "- `year_over_year_changes.csv`: within-series annual changes and small-base marker.",
        "- `first_year_funnels.csv`: applications, admissions, enrollment, and yield at Bucknell and Washington College.",
        "- `unm_document_conversion.csv`: registration relative to document-issued admits, kept separate from admission yield.",
        "- `level_changes.csv`: 2024/2025 changes within Cincinnati and UNM.",
        "- `quality_flags.csv`: every source row that requires review.",
        "- PNG charts: `intake_trends.png`, `intake_change_2025.png`, `admission_yield.png`, and `level_changes.png`.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    rows = read_rows(args.input)
    args.out.mkdir(parents=True, exist_ok=True)
    annual, changes = selected_series(rows)
    snapshot = snapshot_2025(annual)
    funnels, document_conversion = funnel_tables(rows)
    levels = level_changes(rows)
    quality = [{key: row[key] for key in (
        "institution", "reporting_year", "academic_level", "country", "metric", "value",
        "quality_flag", "definition_note", "source_url")}
        for row in rows if row["quality_flag"]]
    write_csv(args.out / "annual_intake_series.csv", annual, list(annual[0]))
    write_csv(args.out / "international_2025_snapshot.csv", snapshot, list(snapshot[0]))
    write_csv(args.out / "year_over_year_changes.csv", changes, list(changes[0]))
    write_csv(args.out / "first_year_funnels.csv", funnels, list(funnels[0]))
    write_csv(args.out / "unm_document_conversion.csv", document_conversion, list(document_conversion[0]))
    write_csv(args.out / "level_changes.csv", levels, list(levels[0]))
    write_csv(args.out / "quality_flags.csv", quality, list(quality[0]))
    plot_trends(annual, args.out / "intake_trends.png")
    plot_2025_changes(changes, args.out / "intake_change_2025.png")
    plot_yield(funnels, args.out / "admission_yield.png")
    plot_levels(levels, args.out / "level_changes.png")
    write_report(args.out / "insights.md", rows, changes, funnels, levels)
    print(f"Wrote university intake EDA to {args.out}")


if __name__ == "__main__":
    main()
