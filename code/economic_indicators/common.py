"""Shared paths, downloads, and the long output format for the economic indicators."""

import csv
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "economic_indicators"
OUT = ROOT / "data" / "economic_indicators"  # where the dashboard reads them
START_YEAR = 2022
STOP_DATE = "2026-10-01"  # end of the study, as in proposal/analysis_windows.md

# One row per unit, period, and measure; every fetch script writes this layout.
LONG_COLUMNS = ["unit_type", "unit_id", "unit_name", "period", "measure", "value", "source"]

# Some government sites refuse requests without a browser-like user agent.
HEADERS = {"User-Agent": "Mozilla/5.0 (Grad-Research economic indicators)"}


def download(url, name, refresh=False):
    """Download `url` to RAW/name once and return the path; reuse it on later runs.
    Returns None when the file does not exist (HTTP 404), e.g. a release not yet published."""
    path = RAW / name
    if path.exists() and not refresh:
        return path
    resp = requests.get(url, headers=HEADERS, timeout=300)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(resp.content)
    print(f"  downloaded {url}")
    return path


def read_csv_bytes(data):
    """Rows of a CSV given as bytes. Government files are UTF-8 (often with a BOM)
    or Windows-1252, so try both."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252").lstrip("﻿\xef\xbb\xbf")
    return list(csv.DictReader(io.StringIO(text)))


def read_csv_in_zip(path):
    """Rows of the first CSV inside a zip. IPEDS zips sometimes hold a revised
    file (`*_rv.csv`) next to the original; the revised one is preferred."""
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if n.lower().endswith(".csv"))
        name = next((n for n in names if n.lower().endswith("_rv.csv")), names[0])
        return read_csv_bytes(z.read(name))


XLSX_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
           "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def read_xlsx(path):
    """{sheet name: [{column letter: text}]} for every sheet of an .xlsx, read with the
    standard library (an .xlsx is a zip of XML files), so no Excel package is needed."""
    m = "{%s}" % XLSX_NS["m"]
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            shared = ["".join(t.text or "" for t in si.iter(m + "t"))
                      for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", XLSX_NS)]
        rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        sheets = {}
        for s in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", XLSX_NS):
            target = rels[s.get("{%s}id" % XLSX_NS["r"])].lstrip("/")
            target = target if target.startswith("xl/") else "xl/" + target
            rows = []
            for row in ET.fromstring(z.read(target)).iter(m + "row"):
                cells = {}
                for c in row.findall("m:c", XLSX_NS):
                    v = c.find("m:v", XLSX_NS)
                    if c.get("t") == "s" and v is not None:
                        text = shared[int(v.text)]
                    elif c.get("t") == "inlineStr":
                        text = "".join(t.text or "" for t in c.iter(m + "t"))
                    else:
                        text = v.text if v is not None else ""
                    cells[re.match(r"[A-Z]+", c.get("r")).group()] = text
                rows.append(cells)
            sheets[s.get("name")] = rows
    return sheets


def write_long(rows, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:  # -sig so Excel reads UTF-8
        w = csv.DictWriter(f, fieldnames=LONG_COLUMNS, restval="", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} rows written to {path}")


def write_table(rows, columns, path):
    """Write a plain (wide) table, such as a crosswalk or lookup."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns, restval="", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} rows written to {path}")
