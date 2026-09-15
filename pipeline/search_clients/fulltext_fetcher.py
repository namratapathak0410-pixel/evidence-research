"""
fulltext_fetcher.py
Requirement 6: Full-text evidence retrieval.

Fetches full-text content for papers when available.
For Europe PMC papers: fetches JATS XML and parses body text.
For CORE papers: uses fullText from the search response.

Reuses the XML parsing logic from the existing parse_fulltext.py.
"""

import time
import logging
import xml.etree.ElementTree as ET
import requests
from config import EUROPEPMC_FULLTEXT_URL, API_TIMEOUT, EUROPEPMC_RATE_LIMIT_DELAY

logger = logging.getLogger(__name__)


def _text(el) -> str:
    """
    Recursively extract all inner text from an XML element.
    Reused from existing parse_fulltext.py.
    """
    if el is None:
        return ""
    parts = []
    if el.text:
        parts.append(el.text.strip())
    for child in el:
        parts.append(_text(child))
        if child.tail:
            parts.append(child.tail.strip())
    return " ".join(p for p in parts if p)


def fetch_fulltext_europepmc(pmcid: str) -> dict:
    """
    Fetch and parse full-text XML from Europe PMC for a given PMCID.

    Args:
        pmcid: The PMC identifier (e.g., "PMC12345678").

    Returns:
        Dict with 'full_text', 'sections', and 'success' fields.
    """
    if not pmcid:
        return {"full_text": "", "sections": {}, "success": False, "error": "No PMCID"}

    try:
        url = EUROPEPMC_FULLTEXT_URL.format(pmcid=pmcid)
        logger.info(f"Fetching full text for {pmcid}")
        resp = requests.get(url, timeout=API_TIMEOUT)

        if resp.status_code == 404:
            return {"full_text": "", "sections": {}, "success": False,
                    "error": "Full text not available"}

        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        # Parse sections from the body
        sections = {}
        body = root.find("body")
        if body is not None:
            for sec in body.findall(".//sec"):
                sec_title_el = sec.find("title")
                sec_title = _text(sec_title_el) if sec_title_el is not None else "Untitled"

                paragraphs = []
                for p in sec.findall("p"):
                    text = _text(p).strip()
                    if text:
                        paragraphs.append(text)

                if paragraphs:
                    sections[sec_title] = "\n".join(paragraphs)

        # If no sections found, get all paragraphs
        if not sections and body is not None:
            all_paragraphs = []
            for p in body.iter("p"):
                text = _text(p).strip()
                if text:
                    all_paragraphs.append(text)
            if all_paragraphs:
                sections["Body"] = "\n\n".join(all_paragraphs)

        # Also parse the abstract from XML if available
        front = root.find("front")
        if front is not None:
            abstract_el = front.find(".//abstract")
            if abstract_el is not None:
                abstract_text = _text(abstract_el)
                if abstract_text:
                    sections["Abstract"] = abstract_text

        # Combine all sections into full text
        full_text = "\n\n".join(
            f"[{title}]\n{content}" for title, content in sections.items()
        )

        return {
            "full_text": full_text,
            "sections": sections,
            "success": True,
            "error": "",
        }

    except ET.ParseError as e:
        logger.error(f"XML parse error for {pmcid}: {e}")
        return {"full_text": "", "sections": {}, "success": False,
                "error": f"XML parse error: {e}"}
    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching full text for {pmcid}")
        return {"full_text": "", "sections": {}, "success": False,
                "error": "Request timeout"}
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error fetching full text for {pmcid}: {e}")
        return {"full_text": "", "sections": {}, "success": False,
                "error": f"HTTP error: {e}"}
    except Exception as e:
        logger.error(f"Error fetching full text for {pmcid}: {e}")
        return {"full_text": "", "sections": {}, "success": False,
                "error": str(e)}


def fetch_fulltext_for_papers(papers: list, max_fetches: int = 5) -> list:
    """
    Attempt to fetch full text for top papers that have PMCID.

    Args:
        papers: List of NormalizedPaper objects.
        max_fetches: Maximum number of full-text fetches to attempt.

    Returns:
        The same list of papers with full_text populated where available.
    """
    fetched = 0

    for paper in papers:
        if fetched >= max_fetches:
            break

        # Only fetch for papers that claim full text is available
        if not paper.full_text_available or paper.full_text:
            continue

        if paper.pmcid:
            result = fetch_fulltext_europepmc(paper.pmcid)
            if result["success"] and result["full_text"]:
                paper.full_text = result["full_text"]
                paper.evidence_level = "full_text"
                paper.extra["sections"] = list(result["sections"].keys())
                fetched += 1
                logger.info(f"Full text fetched for {paper.pmcid}: "
                            f"{len(paper.full_text)} chars")
                time.sleep(EUROPEPMC_RATE_LIMIT_DELAY)

    logger.info(f"Full text fetched for {fetched}/{max_fetches} papers")
    return papers
