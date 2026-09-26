"""
config.py
Central configuration for the Scientific Evidence Research System.
Loads environment variables and defines pipeline parameters.
"""

import os
from dotenv import load_dotenv

load_dotenv(override=True)

# ─── API Keys & Cloud LLMs ───────────────────────────────────────────────────
CORE_API_KEY = os.getenv("CORE_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# ─── Ollama (Local LLM) ──────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

# ─── API Base URLs ────────────────────────────────────────────────────────────
CORE_API_BASE = "https://api.core.ac.uk/v3"
EUROPEPMC_API_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
EUROPEPMC_FULLTEXT_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"

# ─── Rate Limiting ────────────────────────────────────────────────────────────
CORE_RATE_LIMIT_DELAY = 6.5       # seconds between CORE requests (free tier: ~10/min)
EUROPEPMC_RATE_LIMIT_DELAY = 0.4  # seconds between Europe PMC requests
API_TIMEOUT = 30                   # seconds per request

# ─── Pipeline Parameters ─────────────────────────────────────────────────────
MAX_PAPERS_PER_SOURCE = 20        # max papers to retrieve per source per query
MAX_PAPERS_FOR_CLAIMS = 8         # top-ranked papers to extract claims from
MAX_FULLTEXT_FETCHES = 5          # max full-text XML fetches
MAX_QUERY_REFINEMENT_RETRIES = 2  # max search refinement rounds
MIN_RELEVANCE_SCORE = 0.15       # minimum relevance to keep a paper

# ─── Scoring Weights ─────────────────────────────────────────────────────────
WEIGHT_KEYWORD_RELEVANCE = 0.30
WEIGHT_PICO_MATCH = 0.35
WEIGHT_STUDY_TYPE = 0.10
WEIGHT_RECENCY = 0.05
WEIGHT_FULLTEXT = 0.10
WEIGHT_EVIDENCE_LEVEL = 0.10

# ─── Flask ────────────────────────────────────────────────────────────────────
FLASK_HOST = "0.0.0.0"
FLASK_PORT = int(os.getenv("PORT", 5000))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
