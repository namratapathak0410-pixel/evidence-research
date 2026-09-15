"""
paper_normalizer.py
Requirement 7: Paper normalization.

Converts CORE and Europe PMC results into a unified NormalizedPaper format.
"""

import logging
from pipeline.models import NormalizedPaper
from pipeline.search_clients.core_client import extract_core_paper
from pipeline.search_clients.europepmc_client import extract_europepmc_paper

logger = logging.getLogger(__name__)


def normalize_core_papers(raw_results: list) -> list:
    """
    Normalize a list of raw CORE API results into NormalizedPaper objects.

    Args:
        raw_results: List of raw dicts from CORE API.

    Returns:
        List of NormalizedPaper objects.
    """
    papers = []
    for raw in raw_results:
        try:
            extracted = extract_core_paper(raw)
            paper = NormalizedPaper(
                title=extracted["title"],
                authors=extracted["authors"],
                abstract=extracted["abstract"],
                pub_year=extracted["pub_year"],
                pub_date=extracted["pub_date"],
                journal=extracted["journal"],
                doi=extracted["doi"],
                core_id=extracted["core_id"],
                source="core",
                found_in_sources=["core"],
                full_text=extracted["full_text"],
                full_text_available=extracted["full_text_available"],
                evidence_level=extracted["evidence_level"],
                document_type=extracted["document_type"],
                url=extracted["url"],
                download_url=extracted["download_url"],
                keywords=extracted.get("keywords", []),
            )
            # Skip papers without title
            if paper.title.strip():
                papers.append(paper)
        except Exception as e:
            logger.warning(f"Failed to normalize CORE paper: {e}")

    logger.info(f"Normalized {len(papers)} papers from CORE")
    return papers


def normalize_europepmc_papers(raw_results: list) -> list:
    """
    Normalize a list of raw Europe PMC results into NormalizedPaper objects.

    Args:
        raw_results: List of raw dicts from Europe PMC.

    Returns:
        List of NormalizedPaper objects.
    """
    papers = []
    for record in raw_results:
        try:
            extracted = extract_europepmc_paper(record)
            paper = NormalizedPaper(
                title=extracted["title"],
                authors=extracted["authors"],
                abstract=extracted["abstract"],
                pub_year=extracted["pub_year"],
                pub_date=extracted["pub_date"],
                journal=extracted["journal"],
                doi=extracted["doi"],
                pmid=extracted["pmid"],
                pmcid=extracted["pmcid"],
                source="europepmc",
                found_in_sources=["europepmc"],
                full_text_available=extracted["full_text_available"],
                evidence_level=extracted["evidence_level"],
                study_type=extracted["study_type"],
                publication_status=extracted["publication_status"],
                retraction_note=extracted["retraction_note"],
                url=extracted["url"],
                keywords=extracted["keywords"],
                mesh_terms=extracted["mesh_terms"],
            )
            if paper.title.strip():
                papers.append(paper)
        except Exception as e:
            logger.warning(f"Failed to normalize EuropePMC paper: {e}")

    logger.info(f"Normalized {len(papers)} papers from Europe PMC")
    return papers


def normalize_all(core_raw: list, europepmc_raw: list) -> list:
    """
    Normalize results from all sources into a unified list.

    Args:
        core_raw: Raw results from CORE API.
        europepmc_raw: Raw results from Europe PMC.

    Returns:
        Combined list of NormalizedPaper objects.
    """
    all_papers = []
    all_papers.extend(normalize_core_papers(core_raw))
    all_papers.extend(normalize_europepmc_papers(europepmc_raw))

    logger.info(f"Total normalized papers: {len(all_papers)}")
    return all_papers
