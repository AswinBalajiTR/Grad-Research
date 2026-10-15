"""Shared paths, collection helpers, and transparent topic tagging for dashboard pages."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODE_ROOT = PROJECT_ROOT / "code"
DATA_ROOT = PROJECT_ROOT / "data"
YOUTUBE_PATH = DATA_ROOT / "youtube/processed/youtube_comments.csv"
H1B_PATH = DATA_ROOT / "h1b/processed/h1b_filings_2025_to_latest.csv"
REDDIT_THEMES_PATH = DATA_ROOT / "reddit/processed/reddit_theme_counts.csv"

sys.path.insert(0, str(CODE_ROOT / "reddit"))
from concern_themes import THEME_PATTERNS, comment_themes  # noqa: E402


@st.cache_data(show_spinner=False)
def read_csv_path(path: str, modified_ns: int) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def load_data(path: Path) -> pd.DataFrame:
    if path.exists() and path.stat().st_size:
        return read_csv_path(str(path), path.stat().st_mtime_ns)
    return pd.DataFrame()


def run_collector(arguments: list[str], timeout: int = 7200) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [sys.executable, *arguments], cwd=PROJECT_ROOT, text=True,
            capture_output=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "Collector timed out."
    message = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    return result.returncode == 0, message[-2500:]


def compact_number(value: float | int) -> str:
    value = float(value)
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:,.0f}"


def find_col(frame: pd.DataFrame, names: list[str]) -> str | None:
    keys = {re.sub(r"[^a-z0-9]+", "_", str(c).lower()).strip("_"): c for c in frame.columns}
    for name in names:
        key = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        if key in keys:
            return keys[key]
    return None


def annualized_wage(frame: pd.DataFrame) -> pd.Series:
    wage_col = find_col(frame, ["wage_from", "wage_rate_of_pay_from"])
    unit_col = find_col(frame, ["wage_unit", "wage_unit_of_pay"])
    if not wage_col or not unit_col:
        return pd.Series(float("nan"), index=frame.index)
    wage = pd.to_numeric(frame[wage_col], errors="coerce")
    units = frame[unit_col].fillna("").astype(str).str.lower().str.strip()
    return wage * units.map({"year": 1, "month": 12, "bi-weekly": 26, "biweekly": 26, "week": 52, "hour": 2080})
