import os
import json
import re
from typing import Any, Dict
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "openai/gpt-oss-20b"

NORMALIZER_SYSTEM_PROMPT = r"""
You are the Normaliser & Anomaly Auditor for an industrial product catalog enrichment pipeline.
You receive structured specifications extracted from web sources.

RULES:
1. Extract accepted canonical values into "Correct_values".
2. Format strictly: {"Correct_values": {"<Feature>": {"value": "<val>", "the_url_from_which_the_value_is_taken": "<url>"}}, "Anomaly": {}}
3. Convert fractions or units cleanly (e.g. '1/2 x 18 inches'). Do NOT use literal unescaped double quotes inside strings.
4. Return raw JSON only.
"""


def extract_json_block(text: str) -> dict:
    if not text:
        return {}
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        res = json.loads(cleaned)
        if isinstance(res, dict):
            return res
    except Exception:
        pass
    match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
    if match:
        try:
            res = json.loads(match.group(1))
            if isinstance(res, dict):
                return res
        except Exception:
            pass
    return {}


def run_normalizer_agent(
    target_brand: str,
    target_part_num: str,
    raw_extraction_data: Dict[str, Any],
) -> Dict[str, Any]:
    valid_sources = []
    for key, raw_val in raw_extraction_data.items():
        if key in {"brand", "mfr_part_num"}:
            continue
        parsed = raw_val if isinstance(raw_val, dict) else extract_json_block(str(raw_val))
        if isinstance(parsed, dict) and parsed:
            valid_sources.append({"url": key, "data": parsed})

    if not valid_sources:
        return {"Correct_values": {}, "Anomaly": {}}

    prompt = f"TARGET: {target_brand} {target_part_num}\nSOURCES: {json.dumps(valid_sources, ensure_ascii=False)}"

    try:
        completion = groq_client.chat.completions.create(
            model=MODEL,
            max_completion_tokens=1500,
            messages=[
                {"role": "system", "content": NORMALIZER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
        )
        res = extract_json_block(completion.choices[0].message.content or "{}")
        if isinstance(res, dict) and "Correct_values" in res and res["Correct_values"]:
            return res
    except Exception:
        pass

    # Instant deterministic mapping if LLM fails or is rate-limited
    direct_correct = {}
    for s in valid_sources:
        for k, v in s["data"].items():
            if k not in direct_correct and v:
                direct_correct[k] = {"value": str(v), "the_url_from_which_the_value_is_taken": s["url"]}
    return {"Correct_values": direct_correct, "Anomaly": {}}