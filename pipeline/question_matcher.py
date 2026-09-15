"""
question_matcher.py
Requirement 12: Fine-grained question matching.

Compares each extracted claim against the specific details of the user's
question to score how directly the evidence applies.
"""

import re
import logging
from pipeline.models import QuestionAnalysis, ExtractedClaim

logger = logging.getLogger(__name__)


def _match_field(question_value: str, claim_value: str, text_context: str = "") -> str:
    """
    Match a question field against a claim field.

    Returns: "exact", "partial", "indirect", or "no_match"
    """
    if not question_value:
        return "exact"  # no constraint from question = automatic match

    if not claim_value and not text_context:
        return "no_match"

    q_lower = question_value.lower().strip()
    c_lower = (claim_value or "").lower().strip()
    ctx_lower = (text_context or "").lower()

    # Exact match
    if q_lower == c_lower or q_lower in c_lower or c_lower in q_lower:
        return "exact"

    # Check if the question value appears in the context
    if q_lower in ctx_lower:
        return "exact"

    # Partial: individual words match
    q_words = set(re.findall(r'[a-z0-9]+', q_lower))
    c_words = set(re.findall(r'[a-z0-9]+', c_lower + " " + ctx_lower))

    if not q_words:
        return "exact"

    overlap = q_words & c_words
    ratio = len(overlap) / len(q_words)

    if ratio >= 0.7:
        return "partial"
    elif ratio >= 0.3:
        return "indirect"
    else:
        return "no_match"


def _match_score(match_level: str) -> float:
    """Convert match level to numeric score."""
    return {
        "exact": 1.0,
        "partial": 0.6,
        "indirect": 0.3,
        "no_match": 0.0,
    }.get(match_level, 0.0)


def match_claim_to_question(claim: ExtractedClaim,
                            analysis: QuestionAnalysis) -> ExtractedClaim:
    """
    Score how well a claim matches the user's specific question.

    Args:
        claim: An extracted evidence claim.
        analysis: The structured question analysis.

    Returns:
        The claim with match scores populated.
    """
    # Full text context for matching
    context = " ".join([
        claim.claim_text,
        claim.source_passage,
        claim.population,
        claim.intervention,
        claim.comparator,
        claim.outcome,
    ])

    # Match each dimension
    claim.population_match = _match_field(
        analysis.population or analysis.age_group,
        claim.population,
        context,
    )
    claim.intervention_match = _match_field(
        analysis.intervention or analysis.drug,
        claim.intervention,
        context,
    )
    claim.comparator_match = _match_field(
        analysis.comparator,
        claim.comparator,
        context,
    )
    claim.outcome_match = _match_field(
        analysis.outcome or analysis.clinical_outcome,
        claim.outcome,
        context,
    )
    claim.dose_match = _match_field(
        analysis.dose,
        "",  # claims rarely have a dedicated dose field
        context,
    )
    claim.duration_match = _match_field(
        analysis.treatment_duration,
        "",
        context,
    )
    claim.study_design_match = _match_field(
        analysis.study_type_preference,
        "",
        context,
    )

    # Calculate composite question match score
    scores = [
        _match_score(claim.population_match) * 0.15,
        _match_score(claim.intervention_match) * 0.25,
        _match_score(claim.comparator_match) * 0.10,
        _match_score(claim.outcome_match) * 0.20,
        _match_score(claim.dose_match) * 0.10,
        _match_score(claim.duration_match) * 0.05,
        _match_score(claim.study_design_match) * 0.05,
    ]

    # Bonus for having effect direction
    if claim.effect_direction and claim.effect_direction != "unclear":
        scores.append(0.05)
    # Bonus for statistical information
    if claim.statistical_info or claim.effect_size:
        scores.append(0.05)

    claim.question_match_score = round(min(1.0, sum(scores)), 4)

    return claim


def match_all_claims(claims: list, analysis: QuestionAnalysis) -> list:
    """
    Match all claims against the question.

    Args:
        claims: List of ExtractedClaim objects.
        analysis: Structured question analysis.

    Returns:
        Claims with match scores populated, sorted by match score.
    """
    matched = [match_claim_to_question(c, analysis) for c in claims]
    matched.sort(key=lambda c: c.question_match_score, reverse=True)

    if matched:
        logger.info(f"Question matching: {len(matched)} claims scored. "
                    f"Top match: {matched[0].question_match_score}")

    return matched
