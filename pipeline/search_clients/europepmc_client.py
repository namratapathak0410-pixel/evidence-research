"""
europepmc_client.py
Requirement 5: Europe PMC Search.

Searches Europe PMC for biomedical and medical literature.
Evolved from the existing fetcher.py — reuses the pagination pattern
and Europe PMC base URL.
"""

import time
import logging
import requests
from config import (
    EUROPEPMC_API_BASE, EUROPEPMC_RATE_LIMIT_DELAY,
    API_TIMEOUT, MAX_PAPERS_PER_SOURCE,
)

logger = logging.getLogger(__name__)

SEARCH_URL = f"{EUROPEPMC_API_BASE}/search"


def search_europepmc(query: str, limit: int = None) -> list:
    """
    Search Europe PMC for papers matching the query.

    Uses cursorMark-based pagination from the existing fetcher.py pattern.

    Args:
        query: Search query string.
        limit: Maximum number of results.

    Returns:
        List of raw Europe PMC result dicts.
    """
    limit = limit or MAX_PAPERS_PER_SOURCE
    all_results = []
    cursor_mark = "*"
    page = 0
    max_pages = (limit // 25) + 1

    while len(all_results) < limit:
        try:
            params = {
                "query": query,
                "format": "json",
                "pageSize": min(25, limit - len(all_results)),
                "resultType": "core",   # includes abstract, authors, journal info
                "cursorMark": cursor_mark,
            }

            logger.info(f"EuropePMC search: q='{query[:60]}...', page={page + 1}")
            resp = requests.get(SEARCH_URL, params=params, timeout=API_TIMEOUT)

            if resp.status_code == 429:
                logger.warning("Europe PMC rate limited, waiting 5s...")
                time.sleep(5)
                resp = requests.get(SEARCH_URL, params=params, timeout=API_TIMEOUT)

            resp.raise_for_status()
            data = resp.json()

            result_list = data.get("resultList", {}).get("result", [])
            if not result_list:
                break

            all_results.extend(result_list)
            logger.info(f"EuropePMC: got {len(result_list)} results "
                        f"(total {len(all_results)})")

            # Pagination
            next_cursor = data.get("nextCursorMark")
            if not next_cursor or next_cursor == cursor_mark:
                break

            cursor_mark = next_cursor
            page += 1

            if page >= max_pages:
                break

            time.sleep(EUROPEPMC_RATE_LIMIT_DELAY)

        except requests.exceptions.Timeout:
            logger.error(f"Europe PMC timeout for query: {query[:50]}")
            break
        except requests.exceptions.ConnectionError:
            logger.error("Europe PMC connection error")
            break
        except requests.exceptions.HTTPError as e:
            logger.error(f"Europe PMC HTTP error: {e}")
            break
        except Exception as e:
            logger.error(f"Europe PMC unexpected error: {e}")
            break

    return all_results[:limit]


def search_europepmc_multi(queries: list, limit_per_query: int = None) -> list:
    """
    Run multiple queries against Europe PMC and aggregate results.

    Args:
        queries: List of search query strings.
        limit_per_query: Max results per query.

    Returns:
        Combined list of raw Europe PMC results (may contain duplicates).
    """
    all_results = []
    limit_per_query = limit_per_query or (MAX_PAPERS_PER_SOURCE // max(len(queries), 1))
    limit_per_query = max(limit_per_query, 5)

    for query in queries:
        results = search_europepmc(query, limit=limit_per_query)
        all_results.extend(results)

        if len(queries) > 1:
            time.sleep(EUROPEPMC_RATE_LIMIT_DELAY)

    logger.info(f"EuropePMC multi-search: {len(queries)} queries → "
                f"{len(all_results)} total results")
    return all_results


def extract_europepmc_paper(record: dict) -> dict:
    """
    Extract normalized fields from a raw Europe PMC record.

    Reuses the parse_paper pattern from the existing fetcher.py.

    Args:
        record: Raw Europe PMC result dict.

    Returns:
        Dict with standardized field names.
    """
    # Authors
    authors = []
    raw_authors = record.get("authorList", {}).get("author", [])
    if isinstance(raw_authors, list):
        for a in raw_authors:
            if isinstance(a, dict):
                authors.append({
                    "name": a.get("fullName", ""),
                    "affiliation": a.get("affiliation", ""),
                })

    # Publication year
    pub_year = record.get("pubYear")
    if pub_year:
        try:
            pub_year = int(pub_year)
        except (ValueError, TypeError):
            pub_year = None
    if not pub_year:
        fpd = record.get("firstPublicationDate", "")
        if fpd and len(fpd) >= 4:
            try:
                pub_year = int(fpd[:4])
            except (ValueError, TypeError):
                pub_year = None

    # Keywords
    keywords = []
    kw_section = record.get("keywordList", {}).get("keyword", [])
    if isinstance(kw_section, list):
        keywords = [k for k in kw_section if isinstance(k, str)]

    # MeSH terms
    mesh_terms = []
    mesh_list = record.get("meshHeadingList", {}).get("meshHeading", [])
    if isinstance(mesh_list, list):
        for m in mesh_list:
            if isinstance(m, dict):
                desc = m.get("descriptorName", "")
                if desc:
                    mesh_terms.append(desc)

    # Publication type
    pub_type = ""
    pub_type_list = record.get("pubTypeList", {}).get("pubType", [])
    if isinstance(pub_type_list, list) and pub_type_list:
        pub_type = ", ".join(pub_type_list) if isinstance(pub_type_list[0], str) else ""

    # Check retraction / correction
    publication_status = "normal"
    retraction_note = ""
    comment_corrections = record.get("commentCorrectionList", {}).get("commentCorrection", [])
    if isinstance(comment_corrections, list):
        for cc in comment_corrections:
            if isinstance(cc, dict):
                cc_type = (cc.get("type") or "").lower()
                if "retract" in cc_type:
                    publication_status = "retracted"
                    retraction_note = cc.get("note", "Retracted")
                elif "erratum" in cc_type or "correction" in cc_type:
                    if publication_status == "normal":
                        publication_status = "corrected"
                        retraction_note = cc.get("note", "Corrected")

    # Check title for retraction markers
    title = record.get("title", "")
    title_upper = title.upper()
    if "RETRACTED" in title_upper or "WITHDRAWN" in title_upper:
        publication_status = "retracted"
        retraction_note = retraction_note or "Indicated in title"
    elif "EXPRESSION OF CONCERN" in title_upper:
        publication_status = "expression_of_concern"
        retraction_note = retraction_note or "Expression of concern in title"

    # URL
    doi = record.get("doi") or ""
    url = ""
    if doi:
        url = f"https://doi.org/{doi}"
    elif record.get("pmid"):
        url = f"https://pubmed.ncbi.nlm.nih.gov/{record['pmid']}/"

    # Evidence level
    abstract = record.get("abstractText") or ""
    has_fulltext = record.get("isOpenAccess") == "Y" or record.get("inEPMC") == "Y"
    evidence_level = "abstract_only" if abstract else "metadata_only"

    return {
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "pub_year": pub_year,
        "pub_date": record.get("firstPublicationDate") or "",
        "journal": record.get("journalTitle") or "",
        "doi": doi,
        "pmid": record.get("pmid") or "",
        "pmcid": record.get("pmcid") or "",
        "source": "europepmc",
        "full_text": "",          # full text fetched separately
        "full_text_available": has_fulltext,
        "evidence_level": evidence_level,
        "study_type": pub_type,
        "publication_status": publication_status,
        "retraction_note": retraction_note,
        "url": url,
        "keywords": keywords,
        "mesh_terms": mesh_terms,
        "is_open_access": record.get("isOpenAccess") == "Y",
        "cited_by_count": record.get("citedByCount", 0),
    }
