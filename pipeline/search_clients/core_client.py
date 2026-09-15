"""
core_client.py
Requirement 4: CORE API Search.

Searches the CORE API v3 for scientific literature.
API key is passed via Authorization header, never exposed.
"""

import time
import logging
import requests
from config import (
    CORE_API_KEY, CORE_API_BASE, CORE_RATE_LIMIT_DELAY,
    API_TIMEOUT, MAX_PAPERS_PER_SOURCE,
)

logger = logging.getLogger(__name__)

SEARCH_URL = f"{CORE_API_BASE}/search/works"


def search_core(query: str, limit: int = None) -> list:
    """
    Search CORE API for works matching the query.

    Args:
        query: Search query string.
        limit: Maximum number of results to return.

    Returns:
        List of raw CORE API result dicts.
    """
    if not CORE_API_KEY:
        logger.warning("CORE_API_KEY not set — skipping CORE search")
        return []

    limit = limit or MAX_PAPERS_PER_SOURCE
    all_results = []
    offset = 0
    page_size = min(limit, 20)  # CORE API page size

    headers = {
        "Authorization": f"Bearer {CORE_API_KEY}",
    }

    while len(all_results) < limit:
        try:
            params = {
                "q": query,
                "limit": page_size,
                "offset": offset,
            }

            logger.info(f"CORE search: q='{query[:60]}...', offset={offset}")
            resp = requests.get(
                SEARCH_URL,
                params=params,
                headers=headers,
                timeout=API_TIMEOUT,
            )

            if resp.status_code == 429:
                # Rate limited — wait and retry once
                logger.warning("CORE API rate limited, waiting 10s...")
                time.sleep(10)
                resp = requests.get(
                    SEARCH_URL,
                    params=params,
                    headers=headers,
                    timeout=API_TIMEOUT,
                )

            if resp.status_code == 401:
                logger.error("CORE API: Invalid API key")
                return all_results

            if resp.status_code == 400:
                logger.warning(f"CORE API: Bad request for query '{query[:50]}'")
                return all_results

            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            if not results:
                break

            all_results.extend(results)
            logger.info(f"CORE: got {len(results)} results (total {len(all_results)})")

            # Check if there are more results
            total_hits = data.get("totalHits", 0)
            if offset + page_size >= total_hits:
                break

            offset += page_size
            if len(all_results) >= limit:
                break

            time.sleep(CORE_RATE_LIMIT_DELAY)

        except requests.exceptions.Timeout:
            logger.error(f"CORE API timeout for query: {query[:50]}")
            break
        except requests.exceptions.ConnectionError:
            logger.error("CORE API connection error")
            break
        except requests.exceptions.HTTPError as e:
            logger.error(f"CORE API HTTP error: {e}")
            break
        except Exception as e:
            logger.error(f"CORE API unexpected error: {e}")
            break

    return all_results[:limit]


def search_core_multi(queries: list, limit_per_query: int = None) -> list:
    """
    Run multiple queries against CORE and aggregate results.

    Args:
        queries: List of search query strings.
        limit_per_query: Max results per query.

    Returns:
        Combined list of raw CORE results (may contain duplicates).
    """
    all_results = []
    limit_per_query = limit_per_query or (MAX_PAPERS_PER_SOURCE // max(len(queries), 1))
    limit_per_query = max(limit_per_query, 5)

    for query in queries:
        results = search_core(query, limit=limit_per_query)
        all_results.extend(results)

        if len(queries) > 1:
            time.sleep(CORE_RATE_LIMIT_DELAY)

    logger.info(f"CORE multi-search: {len(queries)} queries → {len(all_results)} total results")
    return all_results


def extract_core_paper(raw: dict) -> dict:
    """
    Extract normalized fields from a raw CORE API result.

    Args:
        raw: Raw result dict from CORE API.

    Returns:
        Dict with standardized field names.
    """
    # Extract authors
    authors = []
    for a in (raw.get("authors") or []):
        if isinstance(a, dict):
            authors.append({
                "name": a.get("name", ""),
                "affiliation": "",
            })
        elif isinstance(a, str):
            authors.append({"name": a, "affiliation": ""})

    # Extract DOI
    doi = raw.get("doi") or ""
    if not doi:
        for ident in (raw.get("identifiers") or []):
            if isinstance(ident, dict) and ident.get("type") == "DOI":
                doi = ident.get("identifier", "")
                break
            elif isinstance(ident, str) and ident.startswith("10."):
                doi = ident
                break

    # Extract year
    year = raw.get("yearPublished")
    if not year:
        pub_date = raw.get("publishedDate") or ""
        if pub_date and len(pub_date) >= 4:
            try:
                year = int(pub_date[:4])
            except ValueError:
                year = None

    # Extract URLs
    url = ""
    download_url = raw.get("downloadUrl") or ""
    for link in (raw.get("links") or []):
        if isinstance(link, dict):
            if link.get("type") == "display" and not url:
                url = link.get("url", "")
            elif link.get("type") == "download" and not download_url:
                download_url = link.get("url", "")

    # Extract journal
    journal = ""
    for j in (raw.get("journals") or []):
        if isinstance(j, dict) and j.get("title"):
            journal = j["title"]
            break

    # Full text
    full_text = raw.get("fullText") or ""

    return {
        "title": raw.get("title") or "",
        "authors": authors,
        "abstract": raw.get("abstract") or "",
        "pub_year": year,
        "pub_date": raw.get("publishedDate") or "",
        "journal": journal,
        "doi": doi,
        "core_id": str(raw.get("id") or ""),
        "source": "core",
        "full_text": full_text,
        "full_text_available": bool(full_text),
        "evidence_level": "full_text" if full_text else ("abstract_only" if raw.get("abstract") else "metadata_only"),
        "document_type": raw.get("documentType") or "",
        "url": url,
        "download_url": download_url,
        "publisher": raw.get("publisher") or "",
        "keywords": raw.get("subjects") or [],
    }
