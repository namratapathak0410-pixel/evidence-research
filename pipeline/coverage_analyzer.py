"""
coverage_analyzer.py
Requirements 15-16: Evidence coverage analysis + automatic query refinement.

Checks whether retrieved evidence adequately covers all dimensions of
the user's question, and suggests refined queries when coverage is insufficient.
"""

import json
import logging
from pipeline.llm_client import generate_json
from pipeline.models import QuestionAnalysis, ExtractedClaim, CoverageReport

logger = logging.getLogger(__name__)


def analyze_coverage(claims: list, analysis: QuestionAnalysis) -> CoverageReport:
    """
    Check how well the extracted claims cover the user's question.

    Args:
        claims: List of ExtractedClaim objects.
        analysis: Structured question analysis.

    Returns:
        CoverageReport indicating covered and missing areas.
    """
    report = CoverageReport()

    if not claims:
        report.coverage_summary = "No evidence claims were extracted."
        report.coverage_score = 0.0
        report.needs_refinement = True
        report.missing_areas = _get_all_dimensions(analysis)
        return report

    # Aggregate claim information
    all_claim_text = " ".join([
        " ".join([
            c.claim_text or "", c.population or "", c.intervention or "",
            c.comparator or "", c.outcome or "", c.source_passage or "",
            c.source_paper_title or "",
        ]) for c in claims
    ]).lower()

    dimensions = []
    covered = []
    missing = []

    def _check_dimension(name: str, question_value: str) -> bool:
        if not question_value:
            return True
        val_lower = question_value.lower()
        if val_lower in all_claim_text:
            return True

        # Stop words to ignore during matching
        stop = {
            "the", "a", "an", "in", "on", "of", "with", "and", "or", "to", "for",
            "by", "at", "as", "is", "are", "was", "were", "compared", "standard",
            "care", "vs", "versus", "adults", "patients", "human", "study"
        }
        import re
        tokens = re.findall(r'\b[a-z0-9-]{3,}\b', val_lower)
        content_words = [t for t in tokens if t not in stop]

        if not content_words:
            return any(t in all_claim_text for t in tokens) if tokens else True

        # Check match count
        matches = sum(1 for w in content_words if w in all_claim_text)
        threshold = max(1, len(content_words) // 2)
        return matches >= threshold

    # Check each dimension
    if analysis.population:
        dimensions.append("population")
        if _check_dimension("population", analysis.population):
            report.population_covered = True
            covered.append(f"Population ({analysis.population})")
        else:
            missing.append(f"Population ({analysis.population})")

    if analysis.intervention or analysis.drug:
        dimensions.append("intervention")
        val = analysis.intervention or analysis.drug
        if _check_dimension("intervention", val):
            report.intervention_covered = True
            covered.append(f"Intervention ({val})")
        else:
            missing.append(f"Intervention ({val})")

    if analysis.comparator:
        dimensions.append("comparator")
        if _check_dimension("comparator", analysis.comparator):
            report.comparator_covered = True
            covered.append(f"Comparator ({analysis.comparator})")
        else:
            missing.append(f"Comparator ({analysis.comparator})")

    if analysis.outcome or analysis.clinical_outcome:
        dimensions.append("outcome")
        val = analysis.outcome or analysis.clinical_outcome
        if _check_dimension("outcome", val):
            report.outcome_covered = True
            covered.append(f"Outcome ({val})")
        else:
            missing.append(f"Outcome ({val})")

    if analysis.condition:
        dimensions.append("condition")
        if _check_dimension("condition", analysis.condition):
            covered.append(f"Condition ({analysis.condition})")
        else:
            missing.append(f"Condition ({analysis.condition})")

    if analysis.dose:
        dimensions.append("dose")
        if _check_dimension("dose", analysis.dose):
            report.dose_covered = True
            covered.append(f"Dose ({analysis.dose})")
        else:
            missing.append(f"Dose ({analysis.dose})")

    # If key concepts exist and few dimensions are defined, check concepts
    if analysis.key_concepts and len(dimensions) < 3:
        for concept in analysis.key_concepts[:3]:
            if not any(concept.lower() in d.lower() for d in dimensions):
                dimensions.append(f"concept_{concept}")
                if _check_dimension("concept", concept):
                    covered.append(f"Concept ({concept})")
                else:
                    missing.append(f"Concept ({concept})")

    # Calculate coverage score
    total_dimensions = len(dimensions) if dimensions else 1
    covered_count = len(covered)
    report.coverage_score = round(covered_count / total_dimensions, 3) if total_dimensions else 0.5

    report.covered_areas = covered
    report.missing_areas = missing
    report.needs_refinement = report.coverage_score < 0.5

    # Generate summary
    if report.coverage_score >= 0.8:
        report.coverage_summary = (
            f"Evidence adequately covers the question. "
            f"{covered_count}/{total_dimensions} dimensions covered."
        )
    elif report.coverage_score >= 0.5:
        report.coverage_summary = (
            f"Evidence partially covers the question. "
            f"Missing: {', '.join(missing)}."
        )
    else:
        report.coverage_summary = (
            f"Evidence has significant gaps. "
            f"Missing: {', '.join(missing)}."
        )

    logger.info(f"Coverage: {report.coverage_score} "
                f"({covered_count}/{total_dimensions})")
    return report


def generate_refined_queries(analysis: QuestionAnalysis,
                             coverage: CoverageReport,
                             attempt: int) -> dict:
    """
    Generate refined search queries to fill coverage gaps.

    Args:
        analysis: Original question analysis.
        coverage: Current coverage report with missing areas.
        attempt: Which refinement attempt this is (1 or 2).

    Returns:
        Dict with "core_queries" and "europepmc_queries" lists.
    """
    if not coverage.missing_areas:
        return {"core_queries": [], "europepmc_queries": []}

    try:
        prompt = f"""You are a scientific search expert. 
The following research question was searched but the evidence has gaps.

Question: {analysis.original_question}

Missing evidence areas: {', '.join(coverage.missing_areas)}

This is refinement attempt {attempt} of 2.

Generate 2-3 NEW search queries that specifically target the missing areas.
{'Use broader terminology since the previous search was too specific.' if attempt > 1 else 'Try using synonyms and alternative terminology.'}

Return ONLY valid JSON:
{{
  "core_queries": ["query1", "query2"],
  "europepmc_queries": ["query1", "query2"]
}}
"""
        data = generate_json(prompt, temperature=0.4)
        logger.info(f"Generated {len(data.get('core_queries', []))} + "
                    f"{len(data.get('europepmc_queries', []))} refined queries")
        return data

    except Exception as e:
        logger.error(f"Query refinement failed: {e}")
        # Fallback: broaden existing queries
        return _build_fallback_refinements(analysis, coverage)


def _build_fallback_refinements(analysis: QuestionAnalysis,
                                coverage: CoverageReport) -> dict:
    """Build simple fallback refined queries."""
    queries = []

    # Use key concepts plus missing areas
    for area in coverage.missing_areas[:2]:
        # Extract the term from "Dimension (term)" format
        parts = area.split("(")
        if len(parts) > 1:
            term = parts[1].rstrip(")")
            if analysis.intervention:
                queries.append(f"{analysis.intervention} {term}")
            elif analysis.key_concepts:
                queries.append(f"{analysis.key_concepts[0]} {term}")

    if not queries:
        queries = [analysis.original_question]

    return {
        "core_queries": queries,
        "europepmc_queries": queries,
    }


def _get_all_dimensions(analysis: QuestionAnalysis) -> list:
    """Get all question dimensions as a list of strings."""
    dims = []
    if analysis.population:
        dims.append(f"Population ({analysis.population})")
    if analysis.intervention or analysis.drug:
        dims.append(f"Intervention ({analysis.intervention or analysis.drug})")
    if analysis.comparator:
        dims.append(f"Comparator ({analysis.comparator})")
    if analysis.outcome or analysis.clinical_outcome:
        dims.append(f"Outcome ({analysis.outcome or analysis.clinical_outcome})")
    if analysis.condition:
        dims.append(f"Condition ({analysis.condition})")
    if analysis.key_concepts:
        for c in analysis.key_concepts[:3]:
            if not any(c.lower() in d.lower() for d in dims):
                dims.append(f"Concept ({c})")
    return dims or ["Research inquiry"]
