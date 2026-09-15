"""
deduplicator.py
Requirement 8: Duplicate detection.

Detects and merges duplicate papers across CORE and Europe PMC
using DOI, PMID, PMCID, and title similarity.
"""

import logging
from pipeline.models import NormalizedPaper

logger = logging.getLogger(__name__)


def _normalize_doi(doi: str) -> str:
    """Normalize DOI for comparison."""
    if not doi:
        return ""
    doi = doi.strip().lower()
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    doi = doi.replace("https://dx.doi.org/", "").replace("http://dx.doi.org/", "")
    return doi


def _normalize_title(title: str) -> str:
    """Normalize title for comparison."""
    if not title:
        return ""
    # Lowercase, remove punctuation, collapse whitespace
    t = title.lower().strip()
    t = "".join(c if c.isalnum() or c.isspace() else "" for c in t)
    t = " ".join(t.split())
    return t


def _title_similarity(t1: str, t2: str) -> float:
    """Simple word-based Jaccard similarity between two normalized titles."""
    if not t1 or not t2:
        return 0.0
    words1 = set(t1.split())
    words2 = set(t2.split())
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)


def _merge_papers(primary: NormalizedPaper, duplicate: NormalizedPaper) -> NormalizedPaper:
    """
    Merge metadata from a duplicate into the primary paper.
    Keeps the richest metadata.
    """
    # Track sources
    if duplicate.source not in primary.found_in_sources:
        primary.found_in_sources.append(duplicate.source)

    # Fill missing identifiers
    if not primary.doi and duplicate.doi:
        primary.doi = duplicate.doi
    if not primary.pmid and duplicate.pmid:
        primary.pmid = duplicate.pmid
    if not primary.pmcid and duplicate.pmcid:
        primary.pmcid = duplicate.pmcid
    if not primary.core_id and duplicate.core_id:
        primary.core_id = duplicate.core_id

    # Prefer richer abstract
    if len(duplicate.abstract) > len(primary.abstract):
        primary.abstract = duplicate.abstract

    # Prefer richer full text
    if len(duplicate.full_text) > len(primary.full_text):
        primary.full_text = duplicate.full_text
        primary.full_text_available = True
        primary.evidence_level = "full_text"

    # Merge metadata
    if not primary.journal and duplicate.journal:
        primary.journal = duplicate.journal
    if not primary.pub_year and duplicate.pub_year:
        primary.pub_year = duplicate.pub_year
    if not primary.study_type and duplicate.study_type:
        primary.study_type = duplicate.study_type
    if not primary.url and duplicate.url:
        primary.url = duplicate.url

    # Merge keywords and MeSH
    existing_kw = set(primary.keywords)
    for kw in duplicate.keywords:
        if kw not in existing_kw:
            primary.keywords.append(kw)
    existing_mesh = set(primary.mesh_terms)
    for m in duplicate.mesh_terms:
        if m not in existing_mesh:
            primary.mesh_terms.append(m)

    # Use the more detailed authors list
    if len(duplicate.authors) > len(primary.authors):
        primary.authors = duplicate.authors

    # Keep the more concerning publication status
    status_priority = {
        "retracted": 4, "withdrawn": 3,
        "expression_of_concern": 2, "corrected": 1, "normal": 0,
    }
    if status_priority.get(duplicate.publication_status, 0) > \
       status_priority.get(primary.publication_status, 0):
        primary.publication_status = duplicate.publication_status
        primary.retraction_note = duplicate.retraction_note

    return primary


def deduplicate(papers: list) -> tuple:
    """
    Detect and merge duplicate papers.

    Args:
        papers: List of NormalizedPaper objects from all sources.

    Returns:
        Tuple of (deduplicated_papers, num_duplicates_removed).
    """
    if not papers:
        return [], 0

    # Build index maps for fast lookup
    doi_map = {}        # normalized_doi -> paper index
    pmid_map = {}       # pmid -> paper index
    pmcid_map = {}      # pmcid -> paper index
    title_map = {}      # normalized_title -> paper index

    unique_papers = []
    duplicates_removed = 0

    for paper in papers:
        norm_doi = _normalize_doi(paper.doi)
        norm_title = _normalize_title(paper.title)
        is_duplicate = False
        merge_target = None

        # Check DOI match
        if norm_doi and norm_doi in doi_map:
            merge_target = doi_map[norm_doi]
            is_duplicate = True

        # Check PMID match
        if not is_duplicate and paper.pmid and paper.pmid in pmid_map:
            merge_target = pmid_map[paper.pmid]
            is_duplicate = True

        # Check PMCID match
        if not is_duplicate and paper.pmcid and paper.pmcid in pmcid_map:
            merge_target = pmcid_map[paper.pmcid]
            is_duplicate = True

        # Check title similarity (with same year check)
        if not is_duplicate and norm_title:
            for existing_title, idx in title_map.items():
                sim = _title_similarity(norm_title, existing_title)
                if sim > 0.85:
                    # Also check year matches if both available
                    existing_year = unique_papers[idx].pub_year
                    if paper.pub_year and existing_year:
                        if abs(paper.pub_year - existing_year) <= 1:
                            merge_target = idx
                            is_duplicate = True
                            break
                    elif sim > 0.92:
                        # Very high similarity even without year check
                        merge_target = idx
                        is_duplicate = True
                        break

        if is_duplicate and merge_target is not None:
            # Merge into existing paper
            unique_papers[merge_target] = _merge_papers(
                unique_papers[merge_target], paper
            )
            duplicates_removed += 1
        else:
            # New unique paper
            idx = len(unique_papers)
            unique_papers.append(paper)

            if norm_doi:
                doi_map[norm_doi] = idx
            if paper.pmid:
                pmid_map[paper.pmid] = idx
            if paper.pmcid:
                pmcid_map[paper.pmcid] = idx
            if norm_title:
                title_map[norm_title] = idx

    logger.info(f"Deduplication: {len(papers)} → {len(unique_papers)} "
                f"({duplicates_removed} duplicates removed)")
    return unique_papers, duplicates_removed
