# -*- coding: utf-8 -*-
"""Silver Leaf Cup final factor loader.

The submission contains one final standardized factor, ``ultimate_lgb``.
By default this script reads ``因子值.xlsx`` from the same directory and
returns the date axis, stock-code axis, and factor-value matrix.

Public entry points:
    load_factor_values(xlsx_path=None) -> (dates, stock_codes, values)
    calculate_factors(xlsx_path=None) -> dict
    get_factor_matrix(xlsx_path=None) -> numpy.ndarray
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from pathlib import Path
from typing import Iterable, Optional, Tuple, Union
from xml.etree import ElementTree as ET

import numpy as np


FACTOR_NAME = "ultimate_lgb"
FACTOR_XLSX = "\u56e0\u5b50\u503c.xlsx"
FACTOR_SHEET = "\u56e0\u5b50\u503c"
EXPECTED_SHAPE = (970, 5515)
EXPECTED_START_DATE = "2020-01-02"
EXPECTED_END_DATE = "2023-12-29"

MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _column_index(cell_ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", cell_ref.upper())
    idx = 0
    for ch in letters:
        idx = idx * 26 + ord(ch) - ord("A") + 1
    return idx - 1


def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        raw = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(raw)
    strings: list[str] = []
    for si in root.findall(MAIN_NS + "si"):
        pieces = [node.text or "" for node in si.iter(MAIN_NS + "t")]
        strings.append("".join(pieces))
    return strings


def _worksheet_path(zf: zipfile.ZipFile, sheet_name: str = FACTOR_SHEET) -> str:
    """Return worksheet XML path for the requested sheet, falling back to sheet1."""
    try:
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    except KeyError:
        return "xl/worksheets/sheet1.xml"

    rel_map = {
        rel.attrib.get("Id"): rel.attrib.get("Target", "")
        for rel in rels.findall(PKG_REL_NS + "Relationship")
    }
    sheets = workbook.find(MAIN_NS + "sheets")
    if sheets is None:
        return "xl/worksheets/sheet1.xml"

    chosen_rid: Optional[str] = None
    first_rid: Optional[str] = None
    for sheet in sheets.findall(MAIN_NS + "sheet"):
        rid = sheet.attrib.get(REL_NS + "id")
        if first_rid is None:
            first_rid = rid
        if sheet.attrib.get("name") == sheet_name:
            chosen_rid = rid
            break
    target = rel_map.get(chosen_rid or first_rid or "")
    if not target:
        return "xl/worksheets/sheet1.xml"
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join("xl", target))


def _cell_value(cell: ET.Element, shared: list[str]):
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        inline = cell.find(MAIN_NS + "is")
        if inline is None:
            return ""
        return "".join((node.text or "") for node in inline.iter(MAIN_NS + "t"))

    value_node = cell.find(MAIN_NS + "v")
    if value_node is None:
        return ""
    text = value_node.text or ""
    if cell_type == "s":
        return shared[int(text)]
    if cell_type in {"str", "b"}:
        return text
    try:
        return float(text)
    except ValueError:
        return text


def _iter_rows(zf: zipfile.ZipFile, sheet_path: str, shared: list[str]) -> Iterable[list[object]]:
    with zf.open(sheet_path) as handle:
        for _, elem in ET.iterparse(handle, events=("end",)):
            if elem.tag != MAIN_NS + "row":
                continue
            values: dict[int, object] = {}
            for cell in elem.iter(MAIN_NS + "c"):
                ref = cell.attrib.get("r", "")
                values[_column_index(ref)] = _cell_value(cell, shared)
            if values:
                yield [values.get(i, "") for i in range(max(values) + 1)]
            elem.clear()


def _default_xlsx_path() -> Path:
    return Path(__file__).resolve().with_name(FACTOR_XLSX)


def load_factor_values(xlsx_path: Optional[Union[str, Path]] = None) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load final factor values from the official workbook.

    Returns:
        dates: shape ``(970,)``
        stock_codes: shape ``(5515,)``
        values: shape ``(970, 5515)``
    """
    path = Path(xlsx_path) if xlsx_path is not None else _default_xlsx_path()
    if not path.exists():
        raise FileNotFoundError(f"Cannot find factor workbook: {path}")

    dates: list[str] = []
    row_values: list[np.ndarray] = []
    stock_codes: Optional[np.ndarray] = None

    with zipfile.ZipFile(path) as zf:
        shared = _read_shared_strings(zf)
        sheet_path = _worksheet_path(zf)
        for row_idx, row in enumerate(_iter_rows(zf, sheet_path, shared)):
            if row_idx == 0:
                stock_codes = np.asarray([str(x) for x in row[1:]], dtype=object)
                continue
            if stock_codes is None:
                raise ValueError("Workbook is missing the header row.")
            dates.append(str(row[0]))
            values = np.full(len(stock_codes), np.nan, dtype=float)
            for j, value in enumerate(row[1 : len(stock_codes) + 1]):
                if value == "" or value is None:
                    continue
                values[j] = float(value)
            row_values.append(values)

    if stock_codes is None:
        raise ValueError("Workbook is empty.")
    factor_values = np.vstack(row_values).astype(float, copy=False)
    date_array = np.asarray(dates, dtype=object)

    if factor_values.shape != EXPECTED_SHAPE:
        raise ValueError(f"Unexpected factor matrix shape: {factor_values.shape}, expected {EXPECTED_SHAPE}")
    if str(date_array[0]) != EXPECTED_START_DATE or str(date_array[-1]) != EXPECTED_END_DATE:
        raise ValueError(f"Unexpected date range: {date_array[0]} to {date_array[-1]}")
    return date_array, stock_codes, factor_values


def calculate_factors(xlsx_path: Optional[Union[str, Path]] = None) -> dict:
    """Competition-facing function returning the final standardized factor."""
    dates, stock_codes, values = load_factor_values(xlsx_path)
    return {
        "factor_name": FACTOR_NAME,
        "dates": dates,
        "stock_codes": stock_codes,
        "factor_values": values,
    }


def get_factor_matrix(xlsx_path: Optional[Union[str, Path]] = None) -> np.ndarray:
    """Return only the final factor-value matrix."""
    return calculate_factors(xlsx_path)["factor_values"]


def factor_names() -> list[str]:
    return [FACTOR_NAME]


if __name__ == "__main__":
    result = calculate_factors()
    values = result["factor_values"]
    print("factor_name:", result["factor_name"])
    print("shape:", values.shape)
    print("date_range:", result["dates"][0], "to", result["dates"][-1])
    print("stock_count:", len(result["stock_codes"]))
