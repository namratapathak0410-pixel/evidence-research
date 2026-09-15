"""
retraction_checker.py
Requirement 9: Retraction and publication status checking.

Identifies retracted, corrected, withdrawn papers and expressions of concern.
Papers are not deleted but flagged and excluded from evidence scoring.
"""

import logging

logger = logging.getLogger(__name__)

# Title patterns that indicate problematic publication status
RETRACTION_INDICATORS = [
    "retracted",
    "retraction",
    "withdrawn",
    "withdrawal",
]

CONCERN_INDICATORS = [
    "expression of concern",
    "editorial concern",
]

CORRECTION_INDICATORS = [
    "erratum",
    "corrigendum",
    "correction",
    "amended",
]


def check_retractions(papers: list) -> tuple:
    """
    Check all papers for retraction/problematic publication status.

    Papers may already have status set from the Europe PMC extraction.
    This adds additional title-based checking and generates a report.

    Args:
        papers: List of NormalizedPaper objects.

    Returns:
        Tuple of (papers_with_updated_status, retracted_papers_list).
    """
    retracted_papers = []

    for paper in papers:
        # Skip if already checked during extraction
        if paper.publication_status != "normal":
            if paper.publication_status in ("retracted", "withdrawn"):
                retracted_papers.append({
                    "title": paper.title,
                    "doi": paper.doi,
                    "pmid": paper.pmid,
                    "status": paper.publication_status,
                    "note": paper.retraction_note,
                })
            continue

        # Additional title-based check
        title_lower = paper.title.lower()

        # Check retraction
        for indicator in RETRACTION_INDICATORS:
            if indicator in title_lower:
                paper.publication_status = "retracted"
                paper.retraction_note = f"Title contains '{indicator}'"
                retracted_papers.append({
                    "title": paper.title,
                    "doi": paper.doi,
                    "pmid": paper.pmid,
                    "status": "retracted",
                    "note": paper.retraction_note,
                })
                break

        if paper.publication_status != "normal":
            continue

        # Check expression of concern
        for indicator in CONCERN_INDICATORS:
            if indicator in title_lower:
                paper.publication_status = "expression_of_concern"
                paper.retraction_note = f"Title contains '{indicator}'"
                break

        if paper.publication_status != "normal":
            continue

        # Check correction
        for indicator in CORRECTION_INDICATORS:
            if indicator in title_lower:
                paper.publication_status = "corrected"
                paper.retraction_note = f"Title contains '{indicator}'"
                break

    # Log summary
    status_counts = {}
    for paper in papers:
        status_counts[paper.publication_status] = \
            status_counts.get(paper.publication_status, 0) + 1

    logger.info(f"Retraction check: {status_counts}")
    if retracted_papers:
        logger.warning(f"Found {len(retracted_papers)} retracted/withdrawn papers")

    return papers, retracted_papers


def filter_usable_papers(papers: list) -> list:
    """
    Return papers that are safe to use as evidence.
    Retracted and withdrawn papers are excluded.
    Corrected papers and expressions of concern are kept but with lower weight.

    Args:
        papers: List of NormalizedPaper objects.

    Returns:
        List of papers safe for evidence use.
    """
    usable = []
    for paper in papers:
        if paper.publication_status in ("retracted", "withdrawn"):
            logger.info(f"Excluding retracted paper: {paper.title[:60]}")
            continue
        usable.append(paper)

    excluded = len(papers) - len(usable)
    if excluded:
        logger.info(f"Excluded {excluded} retracted/withdrawn papers")

    return usable
