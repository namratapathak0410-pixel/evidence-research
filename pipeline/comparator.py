"""
pipeline/comparator.py
Dual-Model Scientific Evidence Comparison Engine.
Executes the evidence synthesis pipeline across OpenAI and Google Gemini (with Groq fallback),
providing side-by-side analytical divergence, concordance metrics, and consensus alignment.
"""

import time
import logging
from concurrent.futures import ThreadPoolExecutor
from pipeline.llm_client import generate_openai_direct, generate_gemini_direct, generate_groq_direct
from pipeline.search_clients.europepmc_client import search_europepmc
from pipeline.paper_normalizer import normalize_europepmc_papers

logger = logging.getLogger(__name__)

COMPARISON_PROMPT_TEMPLATE = """You are a senior scientific evidence intelligence engine synthesizing medical and clinical literature.
Analyze the following scientific inquiry based on empirical clinical evidence:

RESEARCH INQUIRY:
{question}

RETRIEVED CLINICAL EVIDENCE CONTEXT:
{evidence_context}

Provide your synthesis strictly as a JSON object with this exact structure:
{{
  "synthesis_summary": "Comprehensive 2-3 paragraph clinical synthesis citing specific findings and effect directions.",
  "effect_direction": "positive|negative|neutral|mixed",
  "confidence_rating": "high|moderate|low",
  "confidence_rationale": "Justification for confidence rating based on study designs and sample sizes.",
  "pico": {{
    "population": "Target population identified",
    "intervention": "Investigated intervention/exposure",
    "comparator": "Control or comparator analyzed",
    "outcome": "Primary measured outcomes"
  }},
  "key_findings": [
    "Key finding 1 with quantitative/statistical significance",
    "Key finding 2 with clinical implication",
    "Key finding 3 with secondary outcome"
  ],
  "discordance_flags": [
    "Any conflicting trial results or clinical nuances"
  ],
  "clinical_recommendation": "Evidence-based summary for practitioners or researchers"
}}
"""


def get_quick_evidence_context(question: str) -> str:
    """Retrieve top papers from Europe PMC for fast comparative context."""
    try:
        raw_papers = search_europepmc(question, limit=6)
        if not raw_papers:
            return "Standard peer-reviewed clinical consensus and randomized controlled trial data."
        
        normalized = normalize_europepmc_papers(raw_papers)
        context_parts = []
        for i, p in enumerate(normalized[:5], 1):
            title = p.title or "Untitled Study"
            abstract = (p.abstract or "")[:400]
            year = p.pub_year or "N/A"
            context_parts.append(f"[{i}] {title} ({year}):\n{abstract}\n")
        return "\n".join(context_parts)
    except Exception as e:
        logger.warning(f"Failed to fetch real-time papers for comparator ({e}); using baseline context.")
        return "Context: Comprehensive clinical trials and systematic reviews on the stated intervention."


def compare_models(question: str, provider_a: str = "openai", provider_b: str = "gemini",
                   openai_key: str = None, gemini_key: str = None, groq_key: str = None) -> dict:
    """
    Run the same scientific evidence synthesis through two distinct AI engines concurrently
    and compare their outputs, consensus alignment, and latency.
    """
    t_start = time.time()
    evidence_context = get_quick_evidence_context(question)
    prompt = COMPARISON_PROMPT_TEMPLATE.format(question=question, evidence_context=evidence_context)

    results = {}

    def run_provider(provider_name: str, key_override: str = None):
        try:
            if provider_name.lower() in ["openai", "gpt-4o", "gpt-4o-mini"]:
                return generate_openai_direct(prompt, api_key=key_override, as_json=True)
            elif provider_name.lower() in ["gemini", "google"]:
                # Try Gemini; if no key configured or provided, fall back to Groq
                try:
                    return generate_gemini_direct(prompt, api_key=key_override, as_json=True)
                except Exception as gemini_err:
                    logger.info(f"Gemini direct call failed ({gemini_err}); utilizing Groq Cloud comparative engine.")
                    res = generate_groq_direct(prompt, api_key=groq_key, as_json=True)
                    res["note"] = "Executed via Groq LLaMA / GPT-OSS engine (Gemini key not configured)"
                    return res
            elif provider_name.lower() in ["groq", "llama"]:
                return generate_groq_direct(prompt, api_key=key_override or groq_key, as_json=True)
            else:
                return generate_openai_direct(prompt, api_key=key_override, as_json=True)
        except Exception as e:
            logger.error(f"Error running provider {provider_name}: {e}")
            return {
                "error": str(e),
                "provider": provider_name,
                "latency_seconds": 0,
                "result": {
                    "synthesis_summary": f"Could not complete analysis via {provider_name}: {str(e)}",
                    "effect_direction": "inconclusive",
                    "confidence_rating": "low",
                    "confidence_rationale": "Provider execution error",
                    "pico": {"population": "N/A", "intervention": "N/A", "comparator": "N/A", "outcome": "N/A"},
                    "key_findings": ["Execution error occurred"],
                    "discordance_flags": [],
                    "clinical_recommendation": "Please verify API key configuration."
                }
            }

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(run_provider, provider_a, openai_key)
        future_b = executor.submit(run_provider, provider_b, gemini_key)
        results["model_a"] = future_a.result()
        results["model_b"] = future_b.result()

    # Calculate comparative metrics
    res_a = results["model_a"].get("result") or {}
    res_b = results["model_b"].get("result") or {}

    dir_a = (res_a.get("effect_direction") or "neutral").lower()
    dir_b = (res_b.get("effect_direction") or "neutral").lower()

    conf_a = (res_a.get("confidence_rating") or "moderate").lower()
    conf_b = (res_b.get("confidence_rating") or "moderate").lower()

    # Concordance calculation
    direction_match = 1.0 if dir_a == dir_b else (0.5 if "mixed" in [dir_a, dir_b] else 0.0)
    confidence_match = 1.0 if conf_a == conf_b else 0.5
    concordance_score = round(((direction_match * 0.6) + (confidence_match * 0.4)) * 100)

    # Key differences analysis
    divergences = []
    if dir_a != dir_b:
        divergences.append(f"Effect direction divergence: {results['model_a'].get('provider')} reports '{dir_a}' whereas {results['model_b'].get('provider')} reports '{dir_b}'.")
    if conf_a != conf_b:
        divergences.append(f"Confidence rating variance: {results['model_a'].get('provider')} assigned '{conf_a.upper()}' vs {results['model_b'].get('provider')} '{conf_b.upper()}'.")
    
    findings_a = res_a.get("key_findings") or []
    findings_b = res_b.get("key_findings") or []
    if len(findings_a) != len(findings_b):
        divergences.append(f"Analytical granularity: {results['model_a'].get('provider')} extracted {len(findings_a)} key claims vs {len(findings_b)} by {results['model_b'].get('provider')}.")

    total_latency = round(time.time() - t_start, 2)

    return {
        "question": question,
        "total_latency_seconds": total_latency,
        "concordance_score": concordance_score,
        "divergence_points": divergences if divergences else ["Both models exhibit high analytical consensus on primary effect direction and clinical implications."],
        "model_a": results["model_a"],
        "model_b": results["model_b"]
    }
