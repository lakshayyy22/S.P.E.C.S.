import os
import re
import json
from functools import lru_cache
from typing import Any, Dict, List, Optional
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
DEFAULT_EXPECTED_OUTPUT_FILE = os.path.join(
    os.path.dirname(__file__),
    "schema",
    "Unihack_ Expected Output - Delivery Format.csv"
)


@lru_cache(maxsize=8)
def load_expected_columns(expected_output_file: str = DEFAULT_EXPECTED_OUTPUT_FILE) -> list:
    if not os.path.exists(expected_output_file):
        return []
    df = pd.read_csv(expected_output_file, nrows=0)
    return df.columns.tolist()


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


ATTRIBUTE_LABEL_COLUMNS = [f"ATTRIBUTE_LABEL {i}" for i in range(1, 51)]
ATTRIBUTE_VALUE_COLUMNS = [f"ATTRIBUTE_VALUE {i}" for i in range(1, 51)]
ATTRIBUTE_UOM_COLUMNS = [f"ATTRIBUTE_UOM {i}" for i in range(1, 51)]


def extract_provenance_urls(correct_values: Dict[str, Any], anomalies: Dict[str, Any], brand: str) -> tuple[str, List[str]]:
    """Extracts unique source URLs and determines the primary manufacturer link and reference links."""
    collected_urls = []

    # 1. Collect URLs from canonical extracted features
    for info in correct_values.values():
        if isinstance(info, dict):
            url = info.get("the_url_from_which_the_value_is_taken") or info.get("source_url") or ""
            if url and url.startswith("http") and url not in collected_urls:
                collected_urls.append(url)

    # 2. Collect URLs from recorded anomalies
    for conflict_list in anomalies.values():
        if isinstance(conflict_list, list):
            for entry in conflict_list:
                if isinstance(entry, dict):
                    url = entry.get("Url") or entry.get("url") or ""
                    if url and url.startswith("http") and url not in collected_urls:
                        collected_urls.append(url)

    if not collected_urls:
        return "", []

    # Identify brand/manufacturer URL as primary MFR URL
    clean_brand = re.sub(r"[^a-z0-9]", "", str(brand).lower())
    mfr_url = ""
    ref_urls = []

    for url in collected_urls:
        url_lower = url.lower()
        if clean_brand and clean_brand in url_lower and not mfr_url:
            mfr_url = url
        else:
            ref_urls.append(url)

    # If no specific brand domain matched, use the first cited URL as MFR URL
    if not mfr_url and collected_urls:
        mfr_url = collected_urls[0]
        ref_urls = collected_urls[1:]

    return mfr_url, ref_urls


def run_output_agent(
    target_brand: str,
    target_part_num: str,
    normalised_data: Dict[str, Any],
    input_row: Optional[Dict[str, Any]] = None,
    expected_output_file: str = DEFAULT_EXPECTED_OUTPUT_FILE,
) -> Dict[str, Any]:
    input_row = input_row or {}
    headers = load_expected_columns(expected_output_file)
    csv_row: Dict[str, Any] = {header: "" for header in headers} if headers else {}
    citations: Dict[str, str] = {}

    # Copy identity values from input dataset
    for key in ["Mfg_Part_Num", "Part_Desc", "E1_Brand", "Unilog_Brand", "DIB_Brand", "Part_Manuf"]:
        if key in input_row:
            csv_row[key] = str(input_row[key] or "")

    csv_row["Mfg_Part_Num"] = csv_row.get("Mfg_Part_Num") or target_part_num
    if "MANUFACTURER_PART_NUMBER" in csv_row:
        csv_row["MANUFACTURER_PART_NUMBER"] = target_part_num
    if "BRAND_NAME" in csv_row:
        csv_row["BRAND_NAME"] = target_brand

    correct_values = normalised_data.get("Correct_values", {})
    anomalies = normalised_data.get("Anomaly", {})

    # Populate primary and reference URLs across the delivery columns
    mfr_url, ref_urls = extract_provenance_urls(correct_values, anomalies, target_brand)
    if "MFR URL" in csv_row:
        csv_row["MFR URL"] = mfr_url

    for idx, ref_url in enumerate(ref_urls[:5], start=1):
        col_name = f"Ref URL {idx}"
        if col_name in csv_row:
            csv_row[col_name] = ref_url

    # Populate item specification attributes (1 to 50)
    slot = 0
    for key, info in correct_values.items():
        if key in {"Brand", "Manufacturer", "Manufacturer Name", "Manufacturer Part Number", "MPN", "Part Number"}:
            continue
        if slot >= 50 or not isinstance(info, dict):
            break
        val = info.get("value")
        url = info.get("the_url_from_which_the_value_is_taken", "")
        if val:
            csv_row[ATTRIBUTE_LABEL_COLUMNS[slot]] = clean_text(key)
            csv_row[ATTRIBUTE_VALUE_COLUMNS[slot]] = clean_text(val)
            if url:
                citations[clean_text(key)] = url
            slot += 1

    desc = clean_text(input_row.get("Part_Desc", "")) or f"{target_brand} {target_part_num}"
    csv_row["SHORT_DESC"] = desc
    csv_row["LONG_DESC1"] = desc
    csv_row["MOBILE_DESC"] = desc[:150]

    return {
        "csv_row": csv_row,
        "anomalies": anomalies,
        "citations": citations,
    }