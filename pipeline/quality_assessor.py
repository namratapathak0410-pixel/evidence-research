"""
quality_assessor.py
Requirements 13-14: Evidence quality assessment + unified evidence score.

Evaluates how strong each piece of evidence is, considering study design,
statistical precision, population relevance, and more.
"""

import logging
from pipeline.models import ExtractedClaim, NormalizedPaper

logger = logging.getLogger(__name__)

# Study design hierarchy (higher = stronger evidence for interventional questions)
STUDY_DESIGN_SCORES = {
    "systematic review": 0.95,
    "meta-analysis": 0.95,
    "meta analysis": 0.95,
    "randomized controlled trial": 0.90,
    "rct": 0.90,
    "randomised controlled trial": 0.90,
    "controlled trial": 0.80,
    "clinical trial": 0.75,
    "cohort study": 0.65,
    "cohort": 0.65,
    "prospective study": 0.65,
    "case-control": 0.55,
    "case control": 0.55,
    "cross-sectional": 0.50,
    "cross sectional": 0.50,
    "observational": 0.50,
    "case report": 0.30,
    "case series": 0.35,
    "expert opinion": 0.20,
    "editorial": 0.15,
    "letter": 0.15,
    "narrative review": 0.40,
    "review": 0.45,
    "research": 0.50,
    "research article": 0.55,
    "journal article": 0.50,
}


def _infer_study_design_score(paper: NormalizedPaper, claim: ExtractedClaim) -> float:
    """Infer study design quality from paper metadata and claim text."""
    # Check paper study type
    paper_type = (paper.study_type or paper.document_type or "").lower()

    # Direct match
    for design, score in STUDY_DESIGN_SCORES.items():
        if design in paper_type:
            return score

    # Check in claim text and abstract
    text = " ".join([
        claim.claim_text,
        claim.source_passage,
        paper.abstract or "",
    ]).lower()

    best_score = 0.3  # default unknown
    for design, score in STUDY_DESIGN_SCORES.items():
        if design in text and score > best_score:
            best_score = score

    return best_score


def _statistical_precision_score(claim: ExtractedClaim) -> float:
    """Score based on presence of statistical information."""
    score = 0.3  # baseline

    text = " ".join([
        claim.statistical_info or "",
        claim.effect_size or "",
        claim.source_passage or "",
    ]).lower()

    # Check for confidence intervals
    if "confidence interval" in text or "ci" in text or "95%" in text:
        score += 0.2

    # Check for p-values
    if "p <" in text or "p =" in text or "p-value" in text or "p value" in text:
        score += 0.15

    # Check for effect sizes
    if any(term in text for term in [
        "odds ratio", "or ", "hazard ratio", "hr ", "risk ratio", "rr ",
        "relative risk", "absolute risk", "number needed",
        "mean difference", "standardized mean", "effect size",
        "cohen", "d =",
    ]):
        score += 0.15

    # Check for sample size mentions
    if any(term in text for term in [
        "n =", "n=", "sample size", "participants", "subjects", "enrolled",
        "patients were", "randomized",
    ]):
        score += 0.1

    return min(1.0, score)


def _evidence_level_quality(paper: NormalizedPaper) -> float:
    """Score based on evidence level (full text vs abstract)."""
    if paper.evidence_level == "full_text":
        return 1.0
    elif paper.evidence_level == "abstract_only":
        return 0.6
    else:
        return 0.3


def _recency_quality(paper: NormalizedPaper) -> float:
    """Slight quality adjustment for recency."""
    if not paper.pub_year:
        return 0.5

    from datetime import datetime
    age = datetime.now().year - paper.pub_year

    if age <= 3:
        return 0.9
    elif age <= 7:
        return 0.8
    elif age <= 15:
        return 0.6
    else:
        return 0.4


def _publication_status_quality(paper: NormalizedPaper) -> float:
    """Quality adjustment for publication status."""
    status_scores = {
        "normal": 1.0,
        "corrected": 0.7,
        "expression_of_concern": 0.3,
        "retracted": 0.0,
        "withdrawn": 0.0,
    }
    return status_scores.get(paper.publication_status, 0.8)


def assess_claim_quality(claim: ExtractedClaim,
                         paper: NormalizedPaper) -> ExtractedClaim:
    """
    Assess the quality of an individual evidence claim.

    Args:
        claim: The extracted claim.
        paper: The paper it came from.

    Returns:
        Claim with quality assessment populated.
    """
    # Individual quality dimensions
    design_score = _infer_study_design_score(paper, claim)
    stat_score = _statistical_precision_score(claim)
    evidence_level = _evidence_level_quality(paper)
    recency = _recency_quality(paper)
    pub_status = _publication_status_quality(paper)

    # Weighted quality score
    quality = (
        design_score * 0.35 +
        stat_score * 0.25 +
        evidence_level * 0.15 +
        recency * 0.10 +
        pub_status * 0.15
    )

    # Determine quality category
    if quality >= 0.75:
        quality_label = "high"
    elif quality >= 0.50:
        quality_label = "moderate"
    elif quality >= 0.30:
        quality_label = "low"
    else:
        quality_label = "very_low"

    claim.evidence_quality = quality_label
    claim.quality_reasoning = (
        f"Study design: {design_score:.2f}, "
        f"Statistical precision: {stat_score:.2f}, "
        f"Evidence level: {evidence_level:.2f}, "
        f"Recency: {recency:.2f}, "
        f"Publication status: {pub_status:.2f}"
    )

    # Unified score combining relevance (question_match_score) and quality
    claim.unified_score = round(
        claim.question_match_score * 0.50 + quality * 0.50,
        4,
    )

    return claim


def assess_all_claims(claims: list, papers: list) -> list:
    """
    Assess quality for all claims.

    Args:
        claims: List of ExtractedClaim objects.
        papers: List of NormalizedPaper objects.

    Returns:
        Claims with quality assessments, sorted by unified score.
    """
    # Build paper lookup by title
    paper_map = {}
    for p in papers:
        paper_map[p.title] = p
        if p.doi:
            paper_map[p.doi] = p
        if p.pmid:
            paper_map[p.pmid] = p

    for claim in claims:
        # Find the source paper
        paper = (
            paper_map.get(claim.source_paper_title) or
            paper_map.get(claim.source_paper_doi) or
            paper_map.get(claim.source_paper_pmid)
        )

        if paper:
            assess_claim_quality(claim, paper)
        else:
            # Can't find paper — assign moderate quality by default
            claim.evidence_quality = "moderate"
            claim.quality_reasoning = "Source paper not found for detailed assessment"
            claim.unified_score = claim.question_match_score * 0.5

    # Sort by unified score
    claims.sort(key=lambda c: c.unified_score, reverse=True)

    if claims:
        logger.info(f"Quality assessment: {len(claims)} claims. "
                    f"Top unified score: {claims[0].unified_score}")

    return claims
