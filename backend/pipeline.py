"""
Orchestration layer that wraps the existing four agents
(ResourceFinder -> ExtractionAgent -> NormalisingAgent -> Output)
into a single, crash-proof function that can be called once per
row of the uploaded spreadsheet.
"""
import os
import traceback
from typing import Any, Dict, List, Optional

from ExtractionAgent import process_product
from NormalisingAgent import run_normalizer_agent
from Output import run_output_agent, load_expected_columns

EXPECTED_OUTPUT_FILE = os.getenv(
    "EXPECTED_OUTPUT_FILE",
    os.path.join(
        os.path.dirname(__file__),
        "schema",
        "Unihack_ Expected Output - Delivery Format.csv",
    ),
)

IDENTITY_PART_NUM_KEYS = [
    "Mfg_Part_Num", "Manufacturer Part Number", "MPN",
    "Part Number", "Part_Number", "mfg_part_num",
]
IDENTITY_BRAND_KEYS = [
    "E1_Brand", "Unilog_Brand", "DIB_Brand", "Part_Manuf",
    "Brand", "Manufacturer",
]
IDENTITY_DESC_KEYS = [
    "Part_Desc", "Product Name", "Description",
]


def get_expected_columns() -> List[str]:
    if os.path.exists(EXPECTED_OUTPUT_FILE):
        return load_expected_columns(EXPECTED_OUTPUT_FILE)
    return []


def _looks_like_placeholder(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if stripped.startswith("--") and stripped.endswith("--"):
        return True
    if stripped.lower() in {"unbranded", "no brand", "n/a", "na", "none", "--", "nan"}:
        return True
    return False


def _first_present(row: Dict[str, Any], keys: List[str]) -> str:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text or _looks_like_placeholder(text):
            continue
        return text
    return ""


def extract_identity(row: Dict[str, Any]) -> Dict[str, str]:
    return {
        "part_num": _first_present(row, IDENTITY_PART_NUM_KEYS),
        "brand": _first_present(row, IDENTITY_BRAND_KEYS),
        "description": _first_present(row, IDENTITY_DESC_KEYS),
    }


def process_single_row(row: Dict[str, Any]) -> Dict[str, Any]:
    identity = extract_identity(row)
    brand = identity["brand"]
    part_num = identity["part_num"]
    description = identity["description"]

    result: Dict[str, Any] = {
        "brand": brand,
        "part_num": part_num,
        "product_name": description or part_num or "Unknown product",
        "status": "error",
        "error": None,
        "csv_row": None,
        "anomalies": {},
        "citations": {},
        "sources_found": 0,
    }

    if not part_num:
        result["error"] = "Row is missing a manufacturer part number."
        return result

    try:
        raw_data = process_product(brand, part_num, description=description)
        if not raw_data:
            result["error"] = "No usable sources were found for this product."
            return result

        result["sources_found"] = max(len(raw_data) - 2, 1)

        normalised_data = run_normalizer_agent(brand, part_num, raw_data)

        output = run_output_agent(
            target_brand=brand,
            target_part_num=part_num,
            normalised_data=normalised_data,
            input_row=row,
            expected_output_file=EXPECTED_OUTPUT_FILE,
        )

        csv_row = output.get("csv_row", {}) or {}
        result["status"] = "success"
        result["csv_row"] = csv_row
        result["anomalies"] = output.get("anomalies", {}) or {}
        result["citations"] = output.get("citations", {}) or {}
        result["product_name"] = csv_row.get("Product Name") or result["product_name"]
        return result

    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
        return result