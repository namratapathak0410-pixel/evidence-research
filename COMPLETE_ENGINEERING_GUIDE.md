# Complete Engineering & Debugging Documentation

## What This Document Covers

This document records **every single step, decision, API, tool, code change, and test** performed to diagnose and fix the "Local vs Render output mismatch" problem in the Scientific Evidence Research System. Follow this document line-by-line to replicate every step independently.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Tech Stack & Dependencies](#2-tech-stack--dependencies)
3. [All External APIs Used (with URLs & Registration)](#3-all-external-apis-used)
4. [The Problem We Solved](#4-the-problem-we-solved)
5. [Root Cause Analysis](#5-root-cause-analysis)
6. [Every Code Change Made (with Before & After)](#6-every-code-change-made)
7. [How the LLM Fallback Chain Works](#7-how-the-llm-fallback-chain-works)
8. [How We Discovered the Right Groq Model](#8-how-we-discovered-the-right-groq-model)
9. [The 15-Stage Research Pipeline](#9-the-15-stage-research-pipeline)
10. [Every Test We Ran](#10-every-test-we-ran)
11. [Git & Deployment Steps](#11-git--deployment-steps)
12. [Full Replication Guide From Scratch](#12-full-replication-guide-from-scratch)
13. [Environment Variables Reference](#13-environment-variables-reference)
14. [File-by-File Project Structure](#14-file-by-file-project-structure)

---

## 1. Project Overview

**What the system does:** Takes a natural-language research question (e.g., "Does metformin reduce mortality in type 2 diabetes?"), searches academic literature databases, extracts evidence claims with statistics, detects contradictions, and synthesizes a structured answer with inline citations.

**Where it runs:**
- **Locally** on your Windows PC at `http://localhost:5000`
- **In the cloud** on Render.com (auto-deployed from GitHub)

---

## 2. Tech Stack & Dependencies

### Python Packages (`requirements.txt`)

```
flask
flask-cors
requests
python-dotenv
gunicorn
```

| Package | Version | Why We Use It |
| :--- | :--- | :--- |
| `flask` | latest | Lightweight Python web framework. Serves the frontend HTML and provides REST API endpoints (`/api/research`, `/api/health`, `/api/ollama/status`). |
| `flask-cors` | latest | Enables Cross-Origin Resource Sharing. Without this, browser JavaScript at `localhost:5000` cannot make `fetch()` calls to the Flask API. |
| `requests` | latest | Makes HTTP calls to external APIs (CORE, Europe PMC, Groq, OpenAI, Ollama). Every LLM call and paper search uses this. |
| `python-dotenv` | latest | Reads the `.env` file and injects variables into `os.environ`. This is how API keys are loaded without hardcoding them in source code. |
| `gunicorn` | latest | Production WSGI server for Render deployment. Flask's built-in server is single-threaded and only for development. Render's `Procfile` or start command uses `gunicorn app:app`. |

### How to install them:
```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

---

## 3. All External APIs Used

### 3.1 CORE API v3 (Paper Search)

| Detail | Value |
| :--- | :--- |
| **What it does** | Searches 200M+ open-access academic papers from repositories worldwide |
| **Base URL** | `https://api.core.ac.uk/v3` |
| **Search endpoint** | `https://api.core.ac.uk/v3/search/works` |
| **Auth method** | `Authorization: Bearer {CORE_API_KEY}` header |
| **Rate limit** | Free tier: ~10 requests/minute (we use 6.5s delay between calls) |
| **Get your key** | Register free at https://core.ac.uk/api-keys |
| **Used in file** | `pipeline/search_clients/core_client.py` |
| **Returns** | JSON with title, abstract, authors, DOI, publication year, full text (when available) |

### 3.2 Europe PMC REST API (Biomedical Paper Search)

| Detail | Value |
| :--- | :--- |
| **What it does** | Searches biomedical and life sciences literature (PubMed, PMC, clinical trials) |
| **Search URL** | `https://www.ebi.ac.uk/europepmc/webservices/rest/search` |
| **Full-text URL** | `https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML` |
| **Auth method** | None required (completely free, no API key needed) |
| **Rate limit** | 0.4s delay between requests (polite usage) |
| **Used in files** | `pipeline/search_clients/europepmc_client.py`, `pipeline/search_clients/fulltext_fetcher.py` |
| **Returns** | JSON with title, abstract, authors, DOI, PMID, PMCID, journal, publication date |

### 3.3 Groq Cloud LLM API (Primary AI Provider)

| Detail | Value |
| :--- | :--- |
| **What it does** | Runs large language models in the cloud (ultra-fast, less than 1 second response) |
| **Chat completions URL** | `https://api.groq.com/openai/v1/chat/completions` |
| **Models listing URL** | `https://api.groq.com/openai/v1/models` |
| **Auth method** | `Authorization: Bearer {GROQ_API_KEY}` header |
| **Model we use** | `openai/gpt-oss-120b` (a 120B parameter model, available on Groq free tier) |
| **Why not llama-3.3-70b-versatile** | That model was **removed** from Groq. We discovered this by listing available models (see Section 8). |
| **Rate limit** | Free tier has token-per-minute limits; returns HTTP 429 when exceeded |
| **Get your key** | Register free at https://console.groq.com/keys (key starts with `gsk_`) |
| **Used in file** | `pipeline/llm_client.py` in `generate_json()` and `generate_text()` |

### 3.4 OpenAI API (Secondary AI Provider / Backup)

| Detail | Value |
| :--- | :--- |
| **What it does** | Runs GPT models in the cloud (high accuracy, paid per token) |
| **Chat completions URL** | `https://api.openai.com/v1/chat/completions` |
| **Auth method** | `Authorization: Bearer {OPENAI_API_KEY}` header |
| **Model we use** | `gpt-4o-mini` (cost-effective, high quality) |
| **When it is used** | Only when Groq fails (429 rate limit, 400 error, or timeout) |
| **Get your key** | https://platform.openai.com/api-keys (key starts with `sk-`) |
| **Used in file** | `pipeline/llm_client.py` as fallback inside `generate_json()` and `generate_text()` |

### 3.5 Ollama (Local LLM — Development Only)

| Detail | Value |
| :--- | :--- |
| **What it does** | Runs LLMs locally on your CPU/GPU (no internet needed) |
| **Generate URL** | `http://localhost:11434/api/generate` |
| **Tags URL** | `http://localhost:11434/api/tags` (list installed models) |
| **Model we use** | `llama3.2` (3B parameter model, runs on CPU) |
| **When it is used** | Only when both Groq AND OpenAI fail, and Ollama is running locally |
| **Install** | Download from https://ollama.com, then run `ollama pull llama3.2` |
| **NOT available on Render** | Render containers do not have Ollama installed. This is why we needed cloud LLMs. |

---

## 4. The Problem We Solved

**User's complaint:** "Local and Render output are different."

**Symptoms:**
- Running locally produced good, detailed research answers with evidence claims
- Running on Render produced basic/fallback answers, missing claims, different papers

---

## 5. Root Cause Analysis

We diagnosed **3 root causes:**

### Cause 1: Ollama Does Not Exist on Render
- **Locally:** Code connects to `http://localhost:11434` where Ollama runs your local `llama3.2` model
- **On Render:** `localhost:11434` is unreachable. Connection refused. Circuit breaker trips. Code falls back to regex-based heuristic extraction (no AI).
- **Evidence:** Render logs showed `"Ollama circuit tripped for 45.0s; using fast heuristic fallbacks."`

### Cause 2: Missing API Keys on Render
- Your `.env` file is in `.gitignore` so it is never pushed to GitHub and Render does not have it
- `CORE_API_KEY` missing on Render means CORE search skipped entirely and only Europe PMC searched which returns fewer/different papers
- `GROQ_API_KEY` missing on Render means Groq LLM skipped which falls through to Ollama which is not available so the system uses heuristic fallback

### Cause 3: Wrong Groq Model ID
- `config.py` originally defaulted to `llama-3.3-70b-versatile`
- This model was **removed from Groq's platform** so every Groq call returned `404 model_not_found`
- We discovered this by querying `https://api.groq.com/openai/v1/models` and testing each model

---

## 6. Every Code Change Made

### Change 1: `config.py` — Two modifications

**File:** `config.py` (line 10 and line 15)

**Change A — load_dotenv() to load_dotenv(override=True)**

```python
# BEFORE:
load_dotenv()

# AFTER:
load_dotenv(override=True)
```

**Why:** By default, `load_dotenv()` does NOT overwrite variables that already exist in `os.environ`. If you edit `.env` and restart the server, old cached values persist. `override=True` forces fresh values from `.env` every time.

---

**Change B — Default GROQ_MODEL**

```python
# BEFORE:
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# AFTER:
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
```

**Why:** `llama-3.3-70b-versatile` no longer exists on Groq. `openai/gpt-oss-120b` is a 120B-parameter model that is active, supports `response_format: json_object`, and is available on the free tier.

---

### Change 2: `pipeline/llm_client.py` — Added system message for JSON compliance

**File:** `pipeline/llm_client.py` (lines 139-142 and lines 165-168)

```python
# BEFORE (Groq section):
"messages": [{"role": "user", "content": prompt}],

# AFTER:
"messages": [
    {"role": "system", "content": "You are a scientific evidence analysis AI. Always respond with valid JSON."},
    {"role": "user", "content": prompt}
],
```

The same change was applied to the OpenAI section too.

**Why:** Both Groq and OpenAI enforce a strict rule: when you send `"response_format": {"type": "json_object"}`, the messages **must contain the word "json"** somewhere. Without it, the API returns:
```
400 Bad Request: 'messages' must contain the word 'json' in some form,
to use 'response_format' of type 'json_object'.
```
Adding the system message `"Always respond with valid JSON."` satisfies this requirement for every call.

**How we discovered this:** We ran a test call and got a 400 error. We then made a raw `requests.post()` call with verbose output and saw the exact error message in the response body.

---

### Change 3: `pipeline/claim_extractor.py` — Increased token budget

**File:** `pipeline/claim_extractor.py` (line 79)

```python
# BEFORE:
data = generate_json(prompt, temperature=0.1, max_tokens=384, timeout=20)

# AFTER:
data = generate_json(prompt, temperature=0.1, max_tokens=1024, timeout=30)
```

**Why:** Research papers often contain 3-6 atomic claims with effect sizes (e.g., `HR 0.70, 95% CI 0.60-0.81`), p-values, sample sizes, and population descriptions. With `max_tokens=384`, the JSON response was getting truncated mid-claim, causing `json.JSONDecodeError`. Raising to `1024` tokens and `30s` timeout prevents this.

---

### Change 4: `.env` — Added cloud LLM keys

**File:** `.env`

```env
# BEFORE:
CORE_API_KEY=OtAKc1zDV3SQa6Jk2TlI4brYP50uXCvn
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2

# AFTER:
CORE_API_KEY=OtAKc1zDV3SQa6Jk2TlI4brYP50uXCvn
GROQ_API_KEY=gsk_your_key_here
GROQ_MODEL=openai/gpt-oss-120b
OPENAI_API_KEY=sk-your_key_here
OPENAI_MODEL=gpt-4o-mini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
```

**Why:** Both local and Render now use the same Groq cloud model as primary LLM. Ollama is kept as a tertiary fallback for fully offline development.

---

### Change 5: `.env.example` — Added template entries (keys sanitized)

**File:** `.env.example`

```env
CORE_API_KEY=
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
FLASK_DEBUG=true
```

**Why:** `.env.example` is committed to GitHub as a template showing which variables are needed. Actual keys are NEVER committed as they stay in `.env` which is protected by `.gitignore`.

---

## 7. How the LLM Fallback Chain Works

Every time the pipeline needs AI (question analysis, query expansion, claim extraction, answer synthesis), it calls `generate_json()` or `generate_text()` in `pipeline/llm_client.py`. The fallback order is:

```
Step 1: Is GROQ_API_KEY set?
  YES -> Call Groq API (https://api.groq.com/openai/v1/chat/completions)
         Success? -> Return result
         Failed (429/400/timeout)? -> Log warning, continue to Step 2

Step 2: Is OPENAI_API_KEY set?
  YES -> Call OpenAI API (https://api.openai.com/v1/chat/completions)
         Success? -> Return result
         Failed? -> Log warning, continue to Step 3

Step 3: Is Ollama circuit closed?
  YES -> Call Ollama (http://localhost:11434/api/generate)
         Success? -> Return result
         Connection refused / timeout? -> Trip circuit breaker for 45 seconds
                                          Raise exception

Step 4: Exception propagates to calling module
  -> Each module has its own fallback (regex extraction, heuristic scoring, etc.)
```

---

## 8. How We Discovered the Right Groq Model

### Step 1: Listed all available models
```python
import requests, os
from dotenv import load_dotenv
load_dotenv()
key = os.getenv('GROQ_API_KEY')
r = requests.get('https://api.groq.com/openai/v1/models',
                  headers={'Authorization': f'Bearer {key}'})
print([m['id'] for m in r.json()['data']])
```

**Result:** `['meta-llama/llama-prompt-guard-2-22m', 'groq/compound', 'groq/compound-mini', 'openai/gpt-oss-20b', 'whisper-large-v3-turbo', 'openai/gpt-oss-120b', 'qwen/qwen3.8-27b', ...]`

**Note:** `llama-3.3-70b-versatile` was NOT in the list. It had been removed.

### Step 2: Tested each candidate model
```python
for m in ['groq/compound', 'openai/gpt-oss-120b', 'qwen/qwen3.8-27b', 'llama-3.1-8b-instant']:
    r = requests.post('https://api.groq.com/openai/v1/chat/completions',
        json={'model': m, 'messages': [{'role': 'user', 'content': 'hi'}]},
        headers={'Authorization': f'Bearer {key}'})
    print(m, r.status_code)
```

**Result:**
```
groq/compound     -> 200 (works)
openai/gpt-oss-120b -> 200 (works)
qwen/qwen3.8-27b -> 200 (works)
llama-3.1-8b-instant -> 404 (removed)
```

### Step 3: Tested JSON mode compatibility
```python
payload = {
    'model': 'openai/gpt-oss-120b',
    'messages': [{'role': 'user', 'content': 'Return JSON with key test and value 123.'}],
    'response_format': {'type': 'json_object'}
}
r = requests.post(url, json=payload, headers=headers)
print(r.status_code, r.json()['choices'][0]['message']['content'])
# Output: 200 {"test":123}
```

**Conclusion:** `openai/gpt-oss-120b` works, supports JSON mode, and is available on the free tier.

---

## 9. The 15-Stage Research Pipeline

All stages run sequentially in `pipeline/orchestrator.py`:

| # | Stage Name | File | What It Does |
| :--- | :--- | :--- | :--- |
| 1 | Question Analysis | `question_analyzer.py` | Sends question to LLM. Extracts PICO elements (Population, Intervention, Comparator, Outcome), domain (medical/scientific), question type, drug name, dosage, frequency, route, age group |
| 2 | Query Expansion | `query_expander.py` | Sends PICO analysis to LLM. Generates multiple search query variations with synonyms, MeSH terms, and boolean operators for both CORE and Europe PMC |
| 3 | Source Selection | `source_selector.py` | Rule-based routing: medical questions go to Europe PMC + CORE; CS/physics questions go to CORE only |
| 4 | Literature Search | `core_client.py` + `europepmc_client.py` | Sends expanded queries to CORE API and Europe PMC REST API. Handles pagination, rate limiting, and error recovery |
| 5 | Normalization | `paper_normalizer.py` | Converts CORE JSON format and Europe PMC JSON format into unified `NormalizedPaper` objects with consistent field names |
| 6 | Deduplication | `deduplicator.py` | Removes duplicate papers using DOI matching and normalized title comparison |
| 7 | Retraction Check | `retraction_checker.py` | Checks Europe PMC metadata for retracted or flagged papers, marks them, filters unusable ones |
| 8 | Relevance Ranking | `relevance_ranker.py` | Scores papers using weighted formula: PICO match (35%) + keyword relevance (30%) + study type (10%) + recency (5%) + full-text availability (10%) + evidence level (10%) |
| 9 | Full-Text Fetch | `fulltext_fetcher.py` | For top-ranked papers with a PMCID, downloads JATS XML from Europe PMC and parses body text sections |
| 10 | Claim Extraction | `claim_extractor.py` | Sends each paper's abstract/text to LLM. Extracts atomic claims with effect direction, effect size, statistical info, confidence level |
| 11 | Claim Matching | `question_matcher.py` | Compares each extracted claim against the original question's PICO elements. Assigns a match score (0-1) |
| 12 | Quality Assessment | `quality_assessor.py` | Grades each claim as High/Moderate/Low based on study design (RCT > cohort > case study), sample size, and statistical rigor |
| 13 | Coverage Analysis | `coverage_analyzer.py` | Checks if all PICO dimensions are covered by at least one claim. If coverage is below 60%, triggers automatic query refinement (up to 2 rounds) |
| 14 | Conflict Detection | `conflict_detector.py` | Groups claims by topic/intervention, detects when studies contradict each other, classifies severity (minor/major) |
| 15 | Answer Synthesis | `answer_generator.py` | Sends all claims, coverage, and conflicts to LLM. Generates structured markdown answer with sections: Executive Summary, Key Findings, Study Comparison, Clinical Takeaways, Limitations |

---

## 10. Every Test We Ran

### Test 1: Check LLM provider status
```python
from pipeline.llm_client import check_ollama_status
print(check_ollama_status())
# Expected: {'running': True, 'model_available': True, 'provider': 'groq', 'models': ['openai/gpt-oss-120b']}
```

### Test 2: Test generate_text (plain text response)
```python
from pipeline.llm_client import generate_text
print(generate_text('Respond with: LLM is working perfectly.'))
# Expected: "LLM is working perfectly."
```

### Test 3: Test generate_json (structured JSON response)
```python
from pipeline.llm_client import generate_json
print(generate_json('Return a JSON object with key status and value success.'))
# Expected: {'status': 'success'}
```

### Test 4: Test claim extraction from a paper
```python
from pipeline.claim_extractor import extract_claims_from_paper
from pipeline.models import NormalizedPaper
p = NormalizedPaper(
    title='Metformin and mortality in diabetes',
    abstract='In a cohort study of 10,000 type 2 diabetes patients, metformin was associated with a 30% reduction in all-cause mortality (HR 0.70, 95% CI 0.60-0.81, p<0.001).'
)
claims = extract_claims_from_paper(p)
print('Claims:', len(claims))
print('Claim text:', claims[0].claim_text)
print('Effect size:', claims[0].effect_size)
# Expected: 1 claim with effect size "HR 0.70, 95% CI 0.60-0.81"
```

### Test 5: Full end-to-end pipeline
```python
import sys
sys.stdout.reconfigure(encoding='utf-8')
from pipeline.orchestrator import run_research_pipeline
res = run_research_pipeline('Does metformin reduce mortality in type 2 diabetes?')
print('Domain:', res.question_analysis.get('domain'))      # "medical"
print('Papers found:', len(res.papers))                     # ~10
print('Claims extracted:', len(res.claims))                 # ~16
print('Sufficiency:', res.evidence_sufficiency)             # "sufficient"
print('Confidence:', res.confidence)                        # "high"
print('Answer:', res.answer[:300])                          # Markdown with citations
```

### Test 6: Flask endpoint tests
```python
from app import app
client = app.test_client()

# Health check
r = client.get('/api/health')
print(r.status_code, r.get_json())
# 200 {'service': 'scientific-evidence-research', 'status': 'ok'}

# LLM status
r = client.get('/api/ollama/status')
print(r.status_code, r.get_json())
# 200 {'model_available': True, 'models': ['openai/gpt-oss-120b'], 'provider': 'groq', 'running': True}
```

---

## 11. Git & Deployment Steps

### What we committed:
```powershell
git add .env.example config.py pipeline/claim_extractor.py pipeline/llm_client.py
git commit -m "feat: enhance cloud LLM support with Groq/OpenAI failover and JSON formatting"
git push origin main
```

### Files changed in the commit:
1. `.env.example` — Added Groq/OpenAI template entries
2. `config.py` — `load_dotenv(override=True)` + default model fix
3. `pipeline/claim_extractor.py` — `max_tokens=1024, timeout=30`
4. `pipeline/llm_client.py` — System message for JSON compliance

### Files NOT committed (protected by `.gitignore`):
- `.env` (contains live secret API keys)
- `venv/`, `.venv/` (virtual environment)
- `__pycache__/` (Python bytecode cache)

### Render deployment:
Render automatically detects the GitHub push and redeploys. But you must manually add environment variables in the Render Dashboard:

1. Go to https://dashboard.render.com/
2. Click your Web Service then go to Environment
3. Add these variables:
   - `CORE_API_KEY` = your CORE key
   - `GROQ_API_KEY` = your Groq key
   - `GROQ_MODEL` = `openai/gpt-oss-120b`
   - `OPENAI_API_KEY` = your OpenAI key
   - `OPENAI_MODEL` = `gpt-4o-mini`
4. Click Save and Render rebuilds automatically

---

## 12. Full Replication Guide From Scratch

### Step 1: Clone and setup
```powershell
git clone https://github.com/namratapathak0410-pixel/scientific-evidence-research-system.git
cd scientific-evidence-research-system
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2: Get API keys
1. **CORE API Key (free):** Go to https://core.ac.uk/api-keys then Register then Copy key
2. **Groq API Key (free):** Go to https://console.groq.com/keys then Create account then Create API Key then Copy (starts with `gsk_`)
3. **OpenAI API Key (optional, paid):** Go to https://platform.openai.com/api-keys then Create key then Copy (starts with `sk-`)

### Step 3: Create `.env` file
In the project root directory, create a file named `.env`:
```env
CORE_API_KEY=paste_your_core_key_here
GROQ_API_KEY=gsk_paste_your_groq_key_here
GROQ_MODEL=openai/gpt-oss-120b
OPENAI_API_KEY=sk-paste_your_openai_key_here
OPENAI_MODEL=gpt-4o-mini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
FLASK_DEBUG=false
```

### Step 4: Run locally
```powershell
python app.py
```
Open `http://localhost:5000` in your browser.

### Step 5: Test the API
```powershell
curl http://localhost:5000/api/health
curl http://localhost:5000/api/ollama/status
```

### Step 6: Deploy to Render
1. Push your code to GitHub
2. Connect the repo to Render.com
3. Add environment variables in Render Dashboard (same keys as `.env`, minus OLLAMA settings)
4. Render auto-deploys on every push

---

## 13. Environment Variables Reference

| Variable | Required? | Default | Where to Set | Description |
| :--- | :--- | :--- | :--- | :--- |
| `CORE_API_KEY` | Recommended | `""` | `.env` + Render | CORE API key for searching 200M+ papers |
| `GROQ_API_KEY` | Yes (cloud) | `""` | `.env` + Render | Groq API key for primary cloud LLM |
| `GROQ_MODEL` | No | `openai/gpt-oss-120b` | `.env` + Render | Which model to use on Groq |
| `OPENAI_API_KEY` | Optional | `""` | `.env` + Render | OpenAI API key for backup LLM |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | `.env` + Render | Which model to use on OpenAI |
| `OPENAI_BASE_URL` | No | `https://api.openai.com/v1` | `.env` | OpenAI-compatible base URL |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | `.env` only | Local Ollama endpoint (local dev only) |
| `OLLAMA_MODEL` | No | `llama3.2` | `.env` only | Local Ollama model tag |
| `PORT` | No | `5000` | Render auto-sets | Port for the Flask server |
| `FLASK_DEBUG` | No | `false` | `.env` | Enable Flask debug mode |

---

## 14. File-by-File Project Structure

```
scientific-evidence-research-system/
|
|-- app.py                          # Flask web server (routes, SSE streaming)
|-- config.py                       # Central configuration (loads .env, defines constants)
|-- requirements.txt                # Python package dependencies
|-- .env                            # SECRET: live API keys (git-ignored, never committed)
|-- .env.example                    # Template showing required variables (committed)
|-- .gitignore                      # Protects .env, venv/, __pycache__/ from git
|
|-- static/                         # Frontend files served by Flask
|   |-- index.html                  # Main HTML page
|   |-- styles.css                  # CSS styling
|   |-- app.js                      # JavaScript (SSE streaming, DOM rendering)
|
|-- pipeline/                       # All 15 pipeline modules
|   |-- __init__.py
|   |-- models.py                   # Data classes (NormalizedPaper, ExtractedClaim, etc.)
|   |-- llm_client.py               # Centralized LLM calls (Groq -> OpenAI -> Ollama)
|   |-- question_analyzer.py        # Stage 1: PICO extraction
|   |-- query_expander.py           # Stage 2: Search query generation
|   |-- source_selector.py          # Stage 3: API routing
|   |-- paper_normalizer.py         # Stage 5: Format unification
|   |-- deduplicator.py             # Stage 6: Duplicate removal
|   |-- retraction_checker.py       # Stage 7: Retraction flagging
|   |-- relevance_ranker.py         # Stage 8: Multi-factor scoring
|   |-- claim_extractor.py          # Stage 10: Atomic claim extraction
|   |-- question_matcher.py         # Stage 11: Claim-question matching
|   |-- quality_assessor.py         # Stage 12: Evidence grading
|   |-- coverage_analyzer.py        # Stage 13: Gap analysis + refinement
|   |-- conflict_detector.py        # Stage 14: Contradiction detection
|   |-- answer_generator.py         # Stage 15: Final synthesis
|   |-- orchestrator.py             # Coordinates all 15 stages
|   |
|   |-- search_clients/             # External API clients
|       |-- __init__.py
|       |-- core_client.py          # Stage 4: CORE API search
|       |-- europepmc_client.py     # Stage 4: Europe PMC search
|       |-- fulltext_fetcher.py     # Stage 9: PMC XML full-text
|
|-- scratch_test_system.py          # Comprehensive test script
|-- PIPELINE.md                     # Pipeline documentation
|-- SYSTEM_ARCHITECTURE.md          # Architecture documentation
|-- README.md                       # Project README
```
