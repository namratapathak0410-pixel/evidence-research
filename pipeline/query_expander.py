"""
query_expander.py
Requirement 2: Query expansion.

Generates search query variations using synonyms, abbreviations,
alternative scientific terminology, and related concepts.
"""

import json
import logging
from pipeline.llm_client import generate_json
from pipeline.models import QuestionAnalysis, ExpandedQueries

logger = logging.getLogger(__name__)

EXPANSION_PROMPT = """You are a scientific literature search expert.

Given a research question analysis, generate effective search queries for two literature databases:
1. CORE API — for general scientific/research literature (CS, physics, engineering, etc.)
2. Europe PMC — for medical and biomedical literature

Return ONLY valid JSON:
{
  "core_queries": [
    "query string 1 for CORE",
    "query string 2 for CORE"
  ],
  "europepmc_queries": [
    "query string 1 for Europe PMC",
    "query string 2 for Europe PMC"
  ],
  "synonyms_used": ["synonym1 -> original", "synonym2 -> original"],
  "expansion_notes": "brief explanation of expansion strategy"
}

RULES:
- Generate 2-4 queries per source, each with different terminology
- Use synonyms, abbreviations, alternative names (e.g., "heart attack" -> "myocardial infarction")
- For drugs: include both generic and brand names if known
- For diseases: include alternative names and abbreviations
- For methods/technologies: include alternative terminology
- Keep queries focused — don't make them too broad
- Each query should be a search string that will work well as a keyword query
- Preserve the MEANING of the original question in all variations
- For Europe PMC queries, use medical/clinical terminology
- For CORE queries, use broader scientific terminology
- If the domain is "medical", focus europepmc queries; if "scientific", focus core queries
- If "mixed", provide good queries for both

Question analysis:
"""



def expand_queries(analysis: QuestionAnalysis) -> ExpandedQueries:
    """
    Generate expanded search queries from the question analysis.

    Args:
        analysis: Structured question analysis from question_analyzer.

    Returns:
        ExpandedQueries with multiple query variations per source.
    """
    result = ExpandedQueries(original_question=analysis.original_question)

    try:
        # Build a rich context string for the LLM
        context = json.dumps(analysis.to_dict(), indent=2)
        data = generate_json(EXPANSION_PROMPT + context, temperature=0.3)

        result.core_queries = data.get("core_queries", [])
        result.europepmc_queries = data.get("europepmc_queries", [])
        result.synonyms_used = data.get("synonyms_used", [])
        result.expansion_notes = data.get("expansion_notes", "")

        logger.info(f"Queries expanded: {len(result.core_queries)} CORE, "
                     f"{len(result.europepmc_queries)} EuropePMC")

    except Exception as e:
        logger.error(f"Query expansion failed: {e}")
        # Fallback: use the original question and key concepts
        result.core_queries = _build_fallback_queries(analysis)
        result.europepmc_queries = _build_fallback_queries(analysis)
        result.expansion_notes = "Fallback: using original terms (LLM expansion failed)"

    # Ensure we always have at least one query per source
    if not result.core_queries:
        result.core_queries = [analysis.original_question]
    if not result.europepmc_queries:
        result.europepmc_queries = [analysis.original_question]

    return result


def _build_fallback_queries(analysis: QuestionAnalysis) -> list:
    """Build basic queries from the analysis when LLM expansion fails."""
    queries = [analysis.original_question]

    # Build a PICO-based query
    parts = []
    if analysis.intervention:
        parts.append(analysis.intervention)
    if analysis.population:
        parts.append(analysis.population)
    if analysis.outcome:
        parts.append(analysis.outcome)
    if analysis.condition:
        parts.append(analysis.condition)

    if parts:
        queries.append(" ".join(parts))

    # Build a concept-based query
    if analysis.key_concepts:
        queries.append(" ".join(analysis.key_concepts[:5]))

    return queries
