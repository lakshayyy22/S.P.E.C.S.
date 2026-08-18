import os
import re
import json
import time
from io import BytesIO
from dotenv import load_dotenv
import requests
import pypdf
from groq import Groq
from ResourceFinder import get_resources

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL = "openai/gpt-oss-20b"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}


def extract_pdf_fallback(url: str) -> str:
    try:
        response = requests.get(url, headers=BROWSER_HEADERS, timeout=8)
        if response.status_code == 200 and response.content.startswith(b'%PDF'):
            pdf_file = BytesIO(response.content)
            reader = pypdf.PdfReader(pdf_file)
            text = ""
            for page in reader.pages[:2]:
                text += (page.extract_text() or "") + "\n"
            return text.strip()
    except Exception:
        pass
    return ""


def re_clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


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


def regex_fallback_extraction(text: str) -> dict:
    """Zero-token instant fallback extractor when API is limited."""
    specs = {}
    
    # Grit matching (e.g. P150, 120 Grit)
    grit_match = re.search(r"\b(P\d{2,4}|\d{2,4}\s*(?:Grit|grit))\b", text)
    if grit_match:
        specs["Grit"] = grit_match.group(1)
        
    # Dimensions (e.g. 1/2" x 18", 5 in)
    dim_match = re.search(r'(\d+(?:/\d+)?(?:\s*x\s*\d+(?:/\d+)?)?\s*(?:in|inch|inches|\"|mm|cm))', text, re.IGNORECASE)
    if dim_match:
        specs["Diameter / Dimensions"] = dim_match.group(1).replace('"', ' inches')
        
    # Quantity / Pack
    qty_match = re.search(r"\b(\d+)\s*(?:Disc/Box|pc|pack|count|pk)\b", text, re.IGNORECASE)
    if qty_match:
        specs["Pack Quantity"] = qty_match.group(1)
        
    # Material / Series
    if re.search(r"Cubitron\s*II", text, re.IGNORECASE):
        specs["Mineral Type"] = "Precision Shaped Ceramic Grain"
    if re.search(r"Film", text, re.IGNORECASE):
        specs["Backing Material"] = "Film"
    if re.search(r"Stikit", text, re.IGNORECASE):
        specs["Attachment Type"] = "Stikit (PSA)"
        
    return specs


def process_data(text: str) -> dict:
    if not text or len(text.strip()) < 15:
        return {}

    clean_snippet = re_clean(text)[:1000]

    try:
        comp = groq_client.chat.completions.create(
            model=MODEL,
            max_completion_tokens=800,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a technical catalog extraction engine. "
                        "Extract the top 8-12 concise product specifications into a single flat JSON object. "
                        "Keys must be short feature names (e.g. 'Diameter', 'Grit', 'Width', 'Length', 'Pack Quantity', 'Material'). "
                        "Values must be strings or numbers. Do NOT output nested dictionaries or markdown."
                    )
                },
                {
                    "role": "user",
                    "content": f"Extract technical specs into a JSON object from this text:\n\n{clean_snippet}"
                }
            ]
        )
        raw_output = comp.choices[0].message.content or "{}"
        parsed = extract_json_block(raw_output)
        if parsed:
            return parsed
    except Exception:
        pass

    # Instant deterministic extraction if LLM is rate-limited or fails
    return regex_fallback_extraction(clean_snippet)


def process_product(brand: str, part_num: str, description: str = "") -> dict:
    resources = get_resources(brand, part_num, description=description)
    data = {"brand": brand, "mfr_part_num": part_num}

    top_url = ""
    if resources:
        for url, content in list(resources.items())[:2]:
            if not top_url and url.startswith("http"):
                top_url = url

            text_to_process = content
            if (not text_to_process or len(text_to_process) < 100) and (".pdf" in url.lower()):
                text_to_process = extract_pdf_fallback(url)

            if text_to_process and len(text_to_process) > 30:
                extracted_dict = process_data(text_to_process)
                if extracted_dict:
                    data[url] = extracted_dict

    # Fallback to description if crawl was empty
    if len(data) <= 2 and description:
        fallback_source = top_url if top_url else f"https://www.3m.com/catalog/{part_num}"
        extracted_from_desc = process_data(f"Product: {brand} {part_num}\nDescription: {description}")
        if not extracted_from_desc:
            extracted_from_desc = regex_fallback_extraction(description)
        if extracted_from_desc:
            data[fallback_source] = extracted_from_desc

    return data