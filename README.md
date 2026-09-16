# Scientific Evidence Research System — Complete Engineering & Replication Guide

An end-to-end autonomous research engine that takes natural-language clinical/scientific questions, searches 200M+ academic papers via open-access literature APIs, extracts atomic evidence claims with statistical effect sizes, detects contradictions, assesses quality, and synthesizes evidence-grounded answers with full academic citations.

---

## 📑 Table of Contents
1. [System Architecture & Core Workflow](#1-system-architecture--core-workflow)
2. [Tools, APIs & Technologies Used](#2-tools-apis--technologies-used)
3. [The Problem: Local vs. Cloud/Render Discrepancy](#3-the-problem-local-vs-cloudrender-discrepancy)
4. [Step-by-Step Diagnosis & Technical Fixes](#4-step-by-step-diagnosis--technical-fixes)
5. [The 15-Stage Pipeline Breakdown](#5-the-15-stage-pipeline-breakdown)
6. [Complete Self-Replication Guide (From Scratch)](#6-complete-self-replication-guide-from-scratch)
7. [Environment Variables Reference](#7-environment-variables-reference)

---

## 1. System Architecture & Core Workflow

```
                        ┌────────────────────────────────────────┐
                        │        Natural Language Question       │
                        └───────────────────┬────────────────────┘
                                            │
                                            ▼
                        ┌────────────────────────────────────────┐
                        │   Stage 1: PICO Question Analysis      │
                        │ (Population, Intervention, Comparator) │
                        └───────────────────┬────────────────────┘
                                            │
                                            ▼
                        ┌────────────────────────────────────────┐
                        │   Stage 2-3: Query Expansion & Routing │
                        └─────────┬────────────────────┬─────────┘
                                  │                    │
                   CORE API (200M+ Papers)    Europe PMC REST API
                                  │                    │
                                  └─────────┬──────────┘
                                            │
                                            ▼
                        ┌────────────────────────────────────────┐
                        │ Stage 5-8: Deduplication, Retraction   │
                        │     Checking & Relevance Ranking       │
                        └───────────────────┬────────────────────┘
                                            │
                                            ▼
                        ┌────────────────────────────────────────┐
                        │ Stage 9: PMC Full-Text XML Fetching    │
                        └───────────────────┬────────────────────┘
                                            │
                                            ▼
                        ┌────────────────────────────────────────┐
                        │ Stage 10-12: Atomic Claim Extraction   │
                        │   & Study Quality Grading (RCT/Cohort) │
                        └───────────────────┬────────────────────┘
                                            │
                                            ▼
                        ┌────────────────────────────────────────┐
                        │ Stage 13-14: Coverage Analysis &       │
                        │       Contradiction / Conflict Detection│
                        └───────────────────┬────────────────────┘
                                            │
                                            ▼
                        ┌────────────────────────────────────────┐
                        │ Stage 15: Answer Synthesis & Inline    │
                        │    Provenance Citations [1], [2], [3]  │
                        └────────────────────────────────────────┘
```

---

## 2. Tools, APIs & Technologies Used

| Category | Tool / Technology | Purpose |
| :--- | :--- | :--- |
| **Backend Framework** | `Flask` + `Flask-CORS` | Lightweight Python REST API server and Server-Sent Events (SSE) streaming. |
| **WSGI Server** | `Gunicorn` | Production WSGI HTTP server for Render deployment. |
| **Primary Cloud LLM** | `Groq API` (`openai/gpt-oss-120b`) | Ultra-fast (<1s response), high-throughput inference with structured JSON output. |
| **Secondary Cloud LLM** | `OpenAI API` (`gpt-4o-mini`) | High-accuracy backup provider with automatic failover if Groq rate limits. |
| **Local LLM Option** | `Ollama` (`llama3.2`) | Local on-device CPU/GPU fallback on `http://localhost:11434`. |
| **Literature Database 1** | `CORE API v3` | Access to 200M+ open-access scholarly repositories worldwide. |
| **Literature Database 2** | `Europe PMC REST API` | Comprehensive biomedical and life sciences research papers and XML full-text. |
| **Environment Management** | `python-dotenv` | Secure loading of API keys and runtime flags from `.env`. |
| **Frontend UI** | HTML5, Vanilla CSS3, JavaScript | Modern dashboard with real-time SSE progress streaming, claim tables, and markdown rendering. |

---

## 3. The Problem: Local vs. Cloud/Render Discrepancy

### Why outputs differed between Local and Render:
1. **Ollama is Local-Only:** On local machines, the code queried `http://localhost:11434` where Ollama was running. On Render (a cloud container), `localhost:11434` does not exist. The connection failed, tripped the circuit breaker, and silently defaulted to a basic regex/heuristic fallback.
2. **Missing Environment Variables on Render:** The local `.env` contained the `CORE_API_KEY`. Because `.env` is git-ignored, Render lacked the key and skipped CORE queries, searching only Europe PMC and returning completely different literature.
3. **Model Inconsistency:** Running `llama3.2` locally while Render ran heuristic code or a different model produced mismatched claim extraction and summaries.

---

## 4. Step-by-Step Diagnosis & Technical Fixes

### Fix 1: Multi-Tier Resilient LLM Client (`pipeline/llm_client.py`)
Configured a 4-tier waterfall fallback:
```
Groq Cloud LLM ──(on failure/429)──► OpenAI Cloud LLM ──(on failure)──► Local Ollama ──(on failure)──► Heuristic Fallback
```

### Fix 2: Strict JSON Schema System Prompts
* **Issue:** Groq and OpenAI return `400 Bad Request` if `"response_format": {"type": "json_object"}` is passed without the word `"json"` in the message payload.
* **Fix:** Injected a system message in all JSON requests:
  ```python
  "messages": [
      {"role": "system", "content": "You are a scientific evidence analysis AI. Always respond with valid JSON."},
      {"role": "user", "content": prompt}
  ]
  ```

### Fix 3: Increased Token Window for Claims (`pipeline/claim_extractor.py`)
* **Issue:** Complex papers with multiple findings were getting cut off with `max_tokens=384`.
* **Fix:** Raised `max_tokens=1024` and `timeout=30` to prevent JSON parsing errors.

### Fix 4: Force Reload of Environment (`config.py`)
* **Issue:** `load_dotenv()` did not overwrite cached environment variables in long-running processes.
* **Fix:** Changed to `load_dotenv(override=True)`.

### Fix 5: Secret Sanitization (`.env.example`)
* Stripped live keys from `.env.example` to prevent accidental credential leakage when pushing to GitHub, while keeping live keys in `.env` (which is `.gitignore` protected).

---

## 5. The 15-Stage Pipeline Breakdown

1. **Question Understanding (`question_analyzer.py`):** Uses LLM to extract PICO parameters (Population, Intervention, Comparator, Outcome, Dosage, Route, Study Type preference).
2. **Query Expansion (`query_expander.py`):** Expands terms into MeSH vocabulary, synonyms, and boolean queries for CORE and Europe PMC.
3. **Source Selection (`source_selector.py`):** Routes biomedical queries to Europe PMC + CORE, and engineering/physics to CORE.
4. **Literature Search (`search_clients/`):** Asynchronously fetches candidate papers across APIs.
5. **Paper Normalization (`paper_normalizer.py`):** Standardizes authors, dates, abstracts, DOIs, PMIDs, and URLs into unified `NormalizedPaper` models.
6. **Deduplication (`deduplicator.py`):** Merges identical studies using DOI matching and normalized title Levenshtein distance.
7. **Retraction Checking (`retraction_checker.py`):** Queries Europe PMC retraction flags to drop compromised papers.
8. **Relevance Ranking (`relevance_ranker.py`):** Calculates multi-factor scores based on PICO overlap, recency, study design (RCT > cohort > review), and full-text availability.
9. **Full-Text Fetching (`fulltext_fetcher.py`):** Downloads XML full-text for top PubMed Central Open Access articles.
10. **Atomic Claim Extraction (`claim_extractor.py`):** Extracts isolated evidence claims, effect sizes (e.g. `HR 0.70`, `OR 0.85`), confidence intervals, and p-values.
11. **Claim Matching (`question_matcher.py`):** Evaluates how closely each claim addresses the core research question.
12. **Quality Assessment (`quality_assessor.py`):** Assigns evidence grades (High, Moderate, Low) based on sample sizes and study methodology.
13. **Coverage Analysis (`coverage_analyzer.py`):** Checks if all PICO domains have sufficient evidence; triggers automated query refinement if gaps exist.
14. **Conflict Detection (`conflict_detector.py`):** Detects contradictions between studies on similar interventions.
15. **Answer Synthesis (`answer_generator.py`):** Produces structured markdown with:
    * 📌 Executive Summary
    * 🔬 Key Findings & Evidence (with inline `[1]`, `[2]` citations)
    * ⚖️ Consistency & Study Comparisons
    * 💡 Clinical / Practical Takeaways
    * ⚠️ Limitations & Evidence Gaps

---

## 6. Complete Self-Replication Guide (From Scratch)

### Step 1: Clone Repository & Setup Virtual Environment
```powershell
git clone <your-repository-url>
cd scientific-evidence-research-system
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2: Acquire API Keys
1. **CORE API Key (Free):** [https://core.ac.uk/api-keys](https://core.ac.uk/api-keys)
2. **Groq API Key (Free):** [https://console.groq.com/keys](https://console.groq.com/keys)
3. **OpenAI API Key (Optional Backup):** [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)

### Step 3: Configure `.env`
Create a `.env` file in the project root:
```env
CORE_API_KEY=your_core_api_key_here
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-120b
OPENAI_API_KEY=sk-your_openai_key_here
OPENAI_MODEL=gpt-4o-mini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
FLASK_DEBUG=false
```

### Step 4: Configure Render Dashboard (For Cloud Deployment)
1. In your **Render Web Service Dashboard**, open **Environment**.
2. Add the environment variables:
   * `CORE_API_KEY`
   * `GROQ_API_KEY`
   * `GROQ_MODEL` = `openai/gpt-oss-120b`
   * `OPENAI_API_KEY`
   * `OPENAI_MODEL` = `gpt-4o-mini`
3. Save changes. Render will rebuild and deploy.

### Step 5: Run Locally
```powershell
python app.py
```
Open **`http://localhost:5000`** in any browser.

---

## 7. Environment Variables Reference

| Variable | Required | Default Value | Description |
| :--- | :--- | :--- | :--- |
| `CORE_API_KEY` | Optional (Recommended) | `""` | API key to query CORE 200M+ paper database. |
| `GROQ_API_KEY` | Yes (for Cloud LLM) | `""` | Groq API key for ultra-fast primary LLM inference. |
| `GROQ_MODEL` | No | `openai/gpt-oss-120b` | Model ID used on Groq. |
| `OPENAI_API_KEY` | Optional | `""` | OpenAI API key for secondary failover. |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | Model ID used on OpenAI. |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | Endpoint for local Ollama instance. |
| `OLLAMA_MODEL` | No | `llama3.2` | Local model tag for Ollama. |
| `PORT` | No | `5000` | Port for the Flask application. |
| `FLASK_DEBUG` | No | `false` | Enables Flask debug mode when set to `true`. |
