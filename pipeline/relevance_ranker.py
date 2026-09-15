"""
relevance_ranker.py
Requirement 10: Relevance ranking.

Ranks papers by how useful they are for answering the user's specific question.
Uses keyword overlap, PICO matching, study type, recency, and evidence level.
"""

import re
import math
import logging
from datetime import datetime
from config import (
    WEIGHT_KEYWORD_RELEVANCE, WEIGHT_PICO_MATCH, WEIGHT_STUDY_TYPE,
    WEIGHT_RECENCY, WEIGHT_FULLTEXT, WEIGHT_EVIDENCE_LEVEL,
    MIN_RELEVANCE_SCORE,
)
from pipeline.models import QuestionAnalysis, NormalizedPaper

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> set:
    """Tokenize text into lowercase words."""
    if not text:
        return set()
    words = re.findall(r'[a-zA-Z0-9]+', text.lower())
    # Remove common stop words
    stop = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "to", "of", "in", "for", "on",
        "with", "at", "by", "from", "as", "into", "through", "during",
        "before", "after", "and", "or", "but", "not", "no", "nor",
        "this", "that", "these", "those", "it", "its", "we", "our",
    }
    return {w for w in words if w not in stop and len(w) > 1}


def _keyword_score(question_tokens: set, paper: NormalizedPaper) -> float:
    """Score keyword overlap between question and paper."""
    paper_text = " ".join([
        paper.title or "",
        paper.abstract or "",
        " ".join(paper.keywords),
        " ".join(paper.mesh_terms),
    ])
    paper_tokens = _tokenize(paper_text)

    if not question_tokens or not paper_tokens:
        return 0.0

    overlap = question_tokens & paper_tokens
    if not overlap:
        return 0.0

    # Weighted by fraction of question terms found
    recall = len(overlap) / len(question_tokens)
    # Also consider precision so we don't reward papers that match
    # many terms but are about something else entirely
    precision = len(overlap) / min(len(paper_tokens), len(question_tokens) * 3)

    return min(1.0, (2 * recall * precision) / max(recall + precision, 0.001))


def _pico_score(analysis: QuestionAnalysis, paper: NormalizedPaper) -> float:
    """Score how well the paper matches the PICO elements."""
    paper_text = " ".join([
        paper.title or "",
        paper.abstract or "",
        " ".join(paper.keywords),
        " ".join(paper.mesh_terms),
    ]).lower()

    scores = []

    def _check(term):
        if not term:
            return None
        term_lower = term.lower()
        # Check for exact phrase
        if term_lower in paper_text:
            return 1.0
        # Check for individual words (partial match)
        words = _tokenize(term_lower)
        if not words:
            return None
        matches = sum(1 for w in words if w in paper_text)
        return matches / len(words)

    # Check each PICO element
    for field in [
        analysis.population, analysis.intervention,
        analysis.comparator, analysis.outcome,
        analysis.condition, analysis.drug,
        analysis.dose, analysis.clinical_outcome,
    ]:
        score = _check(field)
        if score is not None:
            scores.append(score)

    if not scores:
        return 0.0

    return sum(scores) / len(scores)


def _study_type_score(analysis: QuestionAnalysis, paper: NormalizedPaper) -> float:
    """Score how well the paper's study type matches the question's needs."""
    if not analysis.study_type_preference:
        return 0.5  # neutral if no preference

    pref = analysis.study_type_preference.lower()
    paper_type = (paper.study_type or paper.document_type or "").lower()

    if not paper_type:
        return 0.3  # unknown type

    # High-value matches
    if pref in paper_type or paper_type in pref:
        return 1.0

    # Related types
    rct_terms = {"rct", "randomized", "randomised", "controlled trial"}
    review_terms = {"systematic review", "meta-analysis", "meta analysis", "review"}
    observational_terms = {"cohort", "case-control", "cross-sectional", "observational"}

    pref_set = set(pref.split())
    type_set = set(paper_type.split())

    if pref_set & rct_terms and type_set & rct_terms:
        return 0.9
    if pref_set & review_terms and type_set & review_terms:
        return 0.9
    if pref_set & observational_terms and type_set & observational_terms:
        return 0.7

    return 0.3


def _recency_score(paper: NormalizedPaper) -> float:
    """Score paper recency (slight boost for newer papers)."""
    if not paper.pub_year:
        return 0.3

    current_year = datetime.now().year
    age = current_year - paper.pub_year

    if age <= 2:
        return 1.0
    elif age <= 5:
        return 0.85
    elif age <= 10:
        return 0.7
    elif age <= 20:
        return 0.5
    else:
        return 0.3


def _fulltext_score(paper: NormalizedPaper) -> float:
    """Score based on full-text availability."""
    if paper.full_text_available or paper.evidence_level == "full_text":
        return 1.0
    elif paper.abstract:
        return 0.6
    else:
        return 0.2


def _evidence_level_score(paper: NormalizedPaper) -> float:
    """Score based on evidence level."""
    level_scores = {
        "full_text": 1.0,
        "abstract_only": 0.6,
        "metadata_only": 0.2,
    }
    return level_scores.get(paper.evidence_level, 0.3)


def rank_papers(papers: list, analysis: QuestionAnalysis) -> list:
    """
    Rank papers by relevance to the user's question.

    Args:
        papers: List of NormalizedPaper objects.
        analysis: Structured question analysis.

    Returns:
        Papers sorted by relevance_score descending.
    """
    question_tokens = _tokenize(analysis.original_question)

    # Also add PICO terms to question tokens for keyword matching
    for field in [analysis.population, analysis.intervention,
                  analysis.comparator, analysis.outcome,
                  analysis.condition, analysis.drug]:
        if field:
            question_tokens |= _tokenize(field)

    for paper in papers:
        kw = _keyword_score(question_tokens, paper)
        pico = _pico_score(analysis, paper)
        st = _study_type_score(analysis, paper)
        rec = _recency_score(paper)
        ft = _fulltext_score(paper)
        el = _evidence_level_score(paper)

        # Publication status penalty
        status_multiplier = 1.0
        if paper.publication_status == "expression_of_concern":
            status_multiplier = 0.5
        elif paper.publication_status == "corrected":
            status_multiplier = 0.85

        paper.relevance_score = (
            WEIGHT_KEYWORD_RELEVANCE * kw +
            WEIGHT_PICO_MATCH * pico +
            WEIGHT_STUDY_TYPE * st +
            WEIGHT_RECENCY * rec +
            WEIGHT_FULLTEXT * ft +
            WEIGHT_EVIDENCE_LEVEL * el
        ) * status_multiplier

        paper.relevance_score = round(paper.relevance_score, 4)

    # Sort by relevance score descending
    papers.sort(key=lambda p: p.relevance_score, reverse=True)

    # Filter out very low relevance
    original_count = len(papers)
    papers = [p for p in papers if p.relevance_score >= MIN_RELEVANCE_SCORE]
    filtered = original_count - len(papers)
    if filtered:
        logger.info(f"Filtered {filtered} papers below relevance threshold "
                    f"{MIN_RELEVANCE_SCORE}")

    logger.info(f"Ranked {len(papers)} papers. "
                f"Top score: {papers[0].relevance_score if papers else 0}")

    return papers
