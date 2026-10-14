import importlib.util
from pathlib import Path

import pandas as pd


def load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


h1b = load_module("collect_h1b", "scripts/collect_h1b.py")
youtube = load_module("collect_youtube", "scripts/collect_youtube.py")


def test_normalize_uscis_filters_fy2025_and_calculates_totals():
    frame = pd.DataFrame(
        {
            "Fiscal Year": [2024, 2025],
            "Employer": ["Old Co", "New Co"],
            "State": ["CA", "ny"],
            "City": ["Los Angeles", "New York"],
            "Initial Approval": [1, 3],
            "Initial Denial": [0, 1],
            "Continuing Approval": [2, 4],
            "Continuing Denial": [0, 2],
        }
    )
    result = h1b.normalize_uscis(frame)
    assert len(result) == 1
    assert result.iloc[0]["employer_name"] == "New Co"
    assert result.iloc[0]["employer_state"] == "NY"
    assert result.iloc[0]["total_filings"] == 10


def test_normalize_dol_keeps_only_h1b():
    frame = pd.DataFrame(
        {
            "VISA_CLASS": ["H-1B", "E-3"],
            "CASE_NUMBER": ["A", "B"],
            "EMPLOYER_NAME": ["One", "Two"],
            "EMPLOYER_STATE": ["CA", "TX"],
        }
    )
    result = h1b.normalize_dol(frame)
    assert result["case_number"].tolist() == ["A"]
    assert result["filing_count"].tolist() == [1]


def test_date_bounds_are_utc():
    value = youtube.utc_bound("2025-01-20")
    assert value.isoformat() == "2025-01-20T00:00:00+00:00"
