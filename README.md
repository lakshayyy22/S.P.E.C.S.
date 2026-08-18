# SPECS — Smart Product Extraction & Catalog Synchronizer

> **An enterprise-grade multi-agent AI system for discovering, extracting, normalizing, validating, and auditing technical product specifications at scale.**

## 🚀 Overview

Managing large product catalogs containing thousands of tools, industrial components, and technical parts often requires manually searching across manufacturer websites, distributor catalogs, and specification PDFs. This process is slow, inconsistent, and highly susceptible to incorrect product matches and conflicting specifications.

**SPECS** automates this workflow using a **4-agent AI pipeline**.

Given an input `.xlsx` or `.csv` containing a **brand** and **manufacturer part number**, SPECS:

1. Finds relevant manufacturer pages, specification sheets, and distributor sources.
2. Extracts technical specifications from HTML pages and PDFs.
3. Cross-validates and normalizes the extracted information using **Llama-3.3-70B**.
4. Detects conflicting or suspicious specifications and preserves their provenance.
5. Generates an audit-ready CSV containing normalized specifications and source URLs.

The result is a **clean, traceable, and verification-friendly product catalog**.

---

## 🏗️ Workflow

                USER
                  │
                  ▼
        Upload .xlsx / .csv
                  │
                  ▼
        ┌──────────────────┐
        │     BACKEND      │
        │                  │
        │ Read input rows  │
        └────────┬─────────┘
                 │
                 │ Row 1
                 ▼
       ┌─────────────────────┐
       │   Agent Pipeline    │
       │                     │
       │ Resource Finder     │
       │        ↓            │
       │ Extraction Engine   │
       │        ↓            │
       │ Normaliser/Auditor  │
       │        ↓            │
       │ Output Agent        │
       └──────────┬──────────┘
                  │
                  ▼
          Processed Row 1
                  │
                  ▼
       Add row to Final CSV
                  │
                  │ Row 2
                  ▼
       ┌─────────────────────┐
       │   Agent Pipeline    │
       │        ...          │
       └──────────┬──────────┘
                  │
                  ▼
          Processed Row 2
                  │
                  ▼
       Add row to Final CSV
                  │
                  │
                 ...
                  │
                  ▼
        All rows processed?
                  │
                  ▼
        ┌──────────────────┐
        │   Final CSV      │
        │                  │
        │ Row 1            │
        │ Row 2            │
        │ Row 3            │
        │ ...              │
        └────────┬─────────┘
                 │
                 ▼
             USER DOWNLOAD



---

## 🤖 Agent Responsibilities

| Agent       | Name                 | Technology                           | Primary Responsibility                                                                                                     |
| ----------- | -------------------- | ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| **Agent 1** | Resource Finder      | Tavily Search API                    | Discover relevant sources for a given brand + part number.  |
| **Agent 2** | Extraction Engine    | Requests, BeautifulSoup, PyPDF, Groq | Retrieve source content and extract raw technical specifications into structured JSON.                                     |
| **Agent 3** | Normaliser & Auditor | Groq, Llama-3.3-70B                  | Validate product identity, resolve conflicts, normalize units, detect anomalies, and preserve provenance.                  |
| **Agent 4** | Output Agent         | Python, CSV, Backend Orchestration   | Transform validated specifications into the final catalog format and expose citations/anomaly information to the frontend. |

---

# 🔎 Agent 1 — Resource Finder

The **Resource Finder** is responsible for discovering the most useful sources for every product.

### Input

```text
Brand: Milwaukee
Part Number: 49-94-0073
```

### Search Strategy

The agent searches for combinations such as:

```text
"Milwaukee 49-94-0073"
"Milwaukee 49-94-0073 specifications"
"Milwaukee 49-94-0073 PDF"
"49-94-0073 site:milwaukeetool.com"
```

### Output

``` text
A list of relevant urls
```

---

# 📄 Agent 2 — Extraction Engine

The **Extraction Engine** converts unstructured web pages and PDFs into structured technical data.

## HTML Extraction

The system uses:

* `requests`
* `BeautifulSoup4`

Irrelevant HTML elements such as:

```text
<script>
<style>
<nav>
<footer>
```

are removed before extraction.

This reduces noise and prevents navigation, advertisements, CSS, and unrelated page content from being passed to the LLM.

## PDF Extraction

Technical specification sheets are downloaded and processed using **PyPDF**.

The extracted text is then passed to the LLM for structured specification extraction.

### Example Raw Output

```json
{
  "https://example.com/spec-sheet.pdf": "The entire content on the page"  
}
```

---

# 🧠 Agent 3 — Normaliser & Anomaly Auditor

The **Normaliser & Anomaly Auditor** is the core intelligence layer of SPECS.

It does not blindly trust extracted information.

Instead, it evaluates:

* Product identity
* Part-number correctness
* Source reliability
* Specification conflicts
* Unit consistency
* Numeric formatting
* Manufacturer vs. distributor differences

## 1. Strict Product Matching

A source must correspond to the requested product.

For example, when searching for:

```text
49-94-0073
```

a source referring to:

```text
49-94-4500
```

must be rejected even if the product category and specifications appear similar.

This prevents search-result contamination from visually similar products.

---

## 2. Source Authority

When multiple sources provide different values, the system prioritizes authoritative information.

Example:

```text
Manufacturer:
Arbor Size = 1 inch

Distributor A:
Arbor Size = 1 inch

Distributor B:
Arbor Size = 7/8 inch
```

The manufacturer value is treated as the canonical value, while the conflicting distributor value is retained as an anomaly.

---

## 3. Provenance Tracking

Every accepted value retains the URL from which it originated.

This allows every specification to be independently verified.

---

# 📊 Agent 3 Output Schema

```json
{
  "Correct_values": {
    "Diameter": {
      "value": "14 inches",
      "the_url_from_which_the_value_is_taken": "https://www.milwaukeetool.com/products/49-94-0073"
    },
    "Arbor Size": {
      "value": "1 inches",
      "the_url_from_which_the_value_is_taken": "https://www.milwaukeetool.com/products/49-94-0073"
    }
  },
  "Anomaly": {
    "Arbor Size": [
      {
        "Value": "7/8 inches",
        "Url": "https://www.distributor-example.com/p/49-94-0073"
      }
    ]
  }
}
```

This structure separates:

* **Canonical / accepted values**
* **Conflicting values**
* **Source provenance**

---

# 📤 Agent 4 — Output Agent

The Output Agent converts the normalized audit data into the final catalog format.

## Example Final CSV

| MFR PART NUMBER | BRAND     | Arbor Size | Diameter  | Pack Quantity | Thickness  | MFR URL                    | Ref URL1             |
| --------------- | --------- | ---------- | --------- | ------------- | ---------- | -------------------------- | -------------------- |
| 49-94-0073      | Milwaukee | 1 inches   | 14 inches | 10            | 1/8 inches | `https://milwaukeetool...` | `https://applied...` |

The output can additionally expose anomaly information to the frontend so users can immediately identify specifications requiring manual verification.
It returns a json object containing the csv row, anamolies and citations.
---

# 🔐 Data Provenance & Auditability

A key design principle of SPECS is:

> **No extracted specification should become part of the final catalog without retaining its source.**

For every normalized field, the system maintains:

```text
Specification
      │
      ├── Canonical Value
      │
      ├── Source URL
      │
      ├── Source Type
      │
      └── Anomaly Information
```

This provides traceability from the final CSV back to the original manufacturer or distributor source.

---

# 🛡️ Edge Cases & Reliability

## 403 / Anti-Bot Responses

The extraction layer uses configurable HTTP headers, including a realistic `User-Agent`, to improve compatibility with standard websites.

For sources that cannot be accessed automatically, the pipeline can retain the URL for manual review rather than fabricating data.

---

## Wrong Product Matches

Search engines may return products with similar names or part numbers.

Example:

```text
Requested:
49-94-0073

Incorrect:
49-94-4500
```

The Auditor explicitly verifies the product identifier before accepting extracted specifications.

---

## Conflicting Specifications

Example:

```text
Manufacturer → Arbor Size: 1 inch
Distributor A → Arbor Size: 1 inch
Distributor B → Arbor Size: 7/8 inch
```

Final result:

```text
Canonical:
1 inch

Anomaly:
7/8 inch
```

The conflicting value is not silently discarded; it is preserved for auditability.

---

## Fraction Standardization

Fractions are stored as strings to avoid spreadsheet interpretation issues.

Examples:

```text
1/8
7/8
3/16
5/16
```

This prevents spreadsheet software from incorrectly interpreting fractions as dates or numeric values.

---

# 🧩 Technology Stack

### AI

* **Groq**
* **GPT-OSS-20B**

### Search

* **Tavily Search API**
* Automated WEB Crawling and Domain Filtering

### Web Extraction

* **Requests**
* **In-memory Stream Extraction(BYtesIO)**

### Document Extraction

* **PyPDF**

### Frontend 

* Vanilla JavaScript(ES6+)

* HTML5 and CSS3

* HTML5 Drag-and-Drop aand File API

* EventSource API

### Backend

* Python 3.10+

* **FastAPI** (Async REST API Framework)

* **Uvicorn** (High-performance ASGI Server)

* Server-Sent Events (SSE) (via FastAPI StreamingResponse for live job progress)

* Pandas & OpenPyXL (Batch CSV/Excel ingestion, structured attribute mapping, and schema formatting)

* Python-dotenv (Environment variable & API key management)

# 🎯 Key Benefits

### ⚡ Faster Catalog Enrichment

Automates repetitive searches across manufacturer and distributor websites.

### 🎯 Higher Product-Match Accuracy

Strict part-number validation reduces incorrect specifications caused by similar products.

### 🧠 AI-Assisted Conflict Resolution

Cross-source inconsistencies are detected instead of being silently overwritten.

### 📐 Consistent Specifications

Measurements and fractions are normalized into a predictable format.

### 🔗 Complete Provenance

Every accepted specification retains a source URL.

### 🚨 Explicit Anomaly Detection

Conflicting distributor values remain visible for review.

### 📦 Scalable Architecture

The agent-based pipeline can process large catalogs while keeping discovery, extraction, auditing, and publishing logically separated.

---

# 🚀 Future Improvements

Potential extensions include:

* Parallel processing of thousands of SKUs
* Source reliability scoring
* Automatic retry and rate-limit handling
* OCR support for scanned specification PDFs
* Table extraction from complex PDFs
* Database-backed product catalogs
* Human-in-the-loop approval workflows
* Confidence scores for individual specifications
* Version history for catalog changes
* Automatic re-validation when manufacturer pages change
* Additional export formats such as XLSX and JSON
* Richer anomaly dashboards with filtering and review states

---

# 📜 License

This project was developed for **UniHack 2026** and is released under the **MIT License**.

---

## ⭐ SPECS in One Sentence

> **SPECS turns an unstructured list of product part numbers into a verified, normalized, provenance-backed technical catalog using a multi-agent AI pipeline.**