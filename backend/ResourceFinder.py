import os
import re
from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

BLOCKED_DOMAINS = [
    "linkedin.com", "facebook.com", "twitter.com", "instagram.com",
    "youtube.com", "pinterest.com", "wikipedia.org", "reddit.com"
]


def clean_brand_name(brand: str, description: str) -> str:
    known_brands = ["3M", "Diablo", "Milwaukee", "DeWalt", "Norton", "Bosch", "Makita", "Metabo", "Walter", "Freud"]
    for kb in known_brands:
        if re.search(rf"\b{re.escape(kb)}\b", description, flags=re.IGNORECASE):
            return kb
        if brand and re.search(rf"\b{re.escape(kb)}\b", brand, flags=re.IGNORECASE):
            return kb

    if not brand:
        return ""
    brand = re.sub(r"\(.*?\)", "", brand)
    brand = re.sub(r"\b(LLC|Inc|Corp|Co|Supply|Industrial|Services)\b", "", brand, flags=re.IGNORECASE)
    return brand.strip()


def build_search_queries(brand: str, part_num: str, description: str = "") -> list:
    effective_brand = clean_brand_name(brand, description)
    
    # Strip vendor prefix: e.g. 3MABR-7100075678 -> 7100075678
    core_part = part_num.split("-")[-1] if "-" in part_num else part_num

    clean_desc = re.sub(r"[^\w\s\./-]", " ", description)
    words = [w for w in clean_desc.split() if len(w) > 1 and w.lower() not in {"disc/box", "pack", "the", "and", "box", "case"}][:6]
    
    if words and effective_brand and words[0].lower() == effective_brand.lower():
        words = words[1:]
    
    desc_snippet = " ".join(words)

    queries = []
    if desc_snippet:
        queries.append(f"{effective_brand} {desc_snippet} datasheet specifications".strip())
        queries.append(f"{effective_brand} {desc_snippet}".strip())
    if core_part:
        queries.append(f"{effective_brand} {core_part} specifications".strip())
    
    return queries


def get_resources(brand: str, part_num: str, description: str = "", max_results: int = 4) -> dict:
    queries = build_search_queries(brand, part_num, description)
    resources = {}

    for query in queries:
        print(f"[ResourceFinder] Searching for: {query}")
        try:
            response = tavily.search(
                query=query,
                max_results=max_results,
                include_raw_content=True
            )
            for res in response.get('results', []):
                url = res.get('url', '')
                if any(domain in url.lower() for domain in BLOCKED_DOMAINS):
                    continue

                raw = res.get('raw_content') or ""
                snippet = res.get('content') or ""
                combined = (raw if len(raw.strip()) > 100 else snippet).strip()

                if combined and len(combined) > 40:
                    resources[url] = combined

            if len(resources) >= 2:
                break
        except Exception as e:
            print(f"[ResourceFinder] Error: {e}")

    return resources