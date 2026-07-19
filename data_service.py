from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests

BASE_DIR = Path(__file__).resolve().parent
EXCEL_FILE = os.getenv("EXCEL_FILE", "Stokvel_20260719.xlsx").strip()
SHEET_NAME = os.getenv("SHEET_NAME", "Sheet1").strip() or "Sheet1"
DATA_URL = os.getenv(
    "DATA_URL",
    "https://raw.githubusercontent.com/leko94/ARISE_DASH_DASHBOARD/main/Stokvel_20260719.xlsx",
).strip()
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "20"))

MONTH_ORDER = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

INCOME_LABELS = ("profit", "interest", "income", "dividend", "other income")
SUMMARY_LABELS = ("total", "grand total", "overall total")


@dataclass
class SourceResult:
    dataframe: pd.DataFrame
    source_label: str
    warning: str | None = None


def _read_excel(source: str | Path | BytesIO) -> pd.DataFrame:
    """Read the configured worksheet and fall back to the first sheet if needed."""
    try:
        return pd.read_excel(source, sheet_name=SHEET_NAME, engine="openpyxl")
    except ValueError:
        if hasattr(source, "seek"):
            source.seek(0)
        return pd.read_excel(source, sheet_name=0, engine="openpyxl")


def _load_remote() -> SourceResult:
    cache_buster = int(time.time())
    separator = "&" if "?" in DATA_URL else "?"
    url = f"{DATA_URL}{separator}_refresh={cache_buster}"
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": "Ekhishini-Lamajita/1.0",
        },
    )
    response.raise_for_status()
    if not response.content:
        raise ValueError("The remote Excel file was empty.")
    return SourceResult(
        dataframe=_read_excel(BytesIO(response.content)),
        source_label=f"GitHub live data: {DATA_URL}",
    )


def _load_local(warning: str | None = None) -> SourceResult:
    path = BASE_DIR / EXCEL_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"Local Excel file not found: {path}. Set EXCEL_FILE or DATA_URL correctly."
        )
    return SourceResult(
        dataframe=_read_excel(path),
        source_label=f"Local file: {EXCEL_FILE}",
        warning=warning,
    )


def load_source() -> SourceResult:
    """Prefer the live GitHub file; use the bundled spreadsheet if GitHub is unavailable."""
    if DATA_URL:
        try:
            return _load_remote()
        except Exception as exc:  # noqa: BLE001 - fallback is intentional
            return _load_local(
                warning=f"GitHub could not be reached; showing local fallback data. {exc}"
            )
    return _load_local()


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    cleaned.columns = [str(column).strip() for column in cleaned.columns]
    return cleaned


def _find_name_column(columns: list[str]) -> str:
    preferred = {"name", "names", "member", "members", "member name"}
    for column in columns:
        if column.casefold() in preferred:
            return column
    if not columns:
        raise ValueError("The worksheet has no columns.")
    return columns[0]


def prepare_dashboard_data(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Clean the workbook and recalculate totals from available month columns."""
    if raw_df.empty:
        raise ValueError("The worksheet contains no data.")

    df = _normalise_columns(raw_df)
    name_column = _find_name_column(df.columns.tolist())
    df = df.rename(columns={name_column: "Name"})

    df["Name"] = df["Name"].where(df["Name"].notna(), "").astype(str).str.strip()
    df = df[df["Name"].ne("") & df["Name"].str.casefold().ne("nan")]
    df = df[~df["Name"].str.casefold().isin(SUMMARY_LABELS)]

    column_lookup = {column.casefold(): column for column in df.columns}
    month_columns: list[str] = []
    rename_map: dict[str, str] = {}
    for month in MONTH_ORDER:
        original = column_lookup.get(month.casefold())
        if original is not None:
            month_columns.append(month)
            if original != month:
                rename_map[original] = month

    if rename_map:
        df = df.rename(columns=rename_map)

    if not month_columns:
        excluded = {"name", "total", "type"}
        month_columns = [
            column
            for column in df.columns
            if column.casefold() not in excluded
            and pd.to_numeric(df[column], errors="coerce").notna().any()
        ]

    if not month_columns:
        raise ValueError("No monthly contribution columns were found in the worksheet.")

    for column in month_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)

    # Recalculate totals rather than relying on possibly stale Excel formula caches.
    df["Total"] = df[month_columns].sum(axis=1)
    df["Type"] = df["Name"].apply(
        lambda value: "Income"
        if any(label in value.casefold() for label in INCOME_LABELS)
        else "Member"
    )

    ordered_columns = ["Name", "Type", *month_columns, "Total"]
    df = df[ordered_columns].reset_index(drop=True)
    return df, month_columns


def load_dashboard_payload() -> dict[str, Any]:
    loaded_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    try:
        result = load_source()
        df, month_columns = prepare_dashboard_data(result.dataframe)
        return {
            "ok": True,
            "records": df.to_dict("records"),
            "months": month_columns,
            "meta": {
                "source": result.source_label,
                "warning": result.warning,
                "loaded_at": loaded_at,
                "rows": int(len(df)),
            },
        }
    except Exception as exc:  # noqa: BLE001 - returned to the dashboard status panel
        return {
            "ok": False,
            "records": [],
            "months": [],
            "meta": {
                "source": "Unavailable",
                "warning": None,
                "loaded_at": loaded_at,
                "rows": 0,
                "error": str(exc),
            },
        }
