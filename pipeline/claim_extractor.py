"""
claim_extractor.py
Requirement 11: Atomic claim extraction.

Uses a local LLM (via Ollama) to extract individual evidence-bearing claims from
the top-ranked papers. Each claim is a distinct finding with
its own PICO mapping and effect details.
"""

import json
import logging
from config import MAX_PAPERS_FOR_CLAIMS
from pipeline.llm_client import generate_json
from pipeline.models import NormalizedPaper, ExtractedClaim

logger = logging.getLogger(__name__)

def extract_claims_from_paper(paper: NormalizedPaper) -> list:
    """
    Extract atomic evidence claims from a single paper.

    Args:
        paper: NormalizedPaper with abstract and/or full text.

    Returns:
        List of ExtractedClaim objects.
    """
    # Prioritize abstract (dense, structured, and fast for CPU inference)
    text = ""
    if paper.abstract:
        text = paper.abstract[:1500]
    elif paper.full_text:
        text = paper.full_text[:1500]
    else:
        logger.warning(f"No text to extract claims from: {paper.title[:50]}")
        return []

    try:
        prompt = f"""You are a scientific evidence extraction specialist.

Extract individual evidence-bearing claims from the following research paper text.
Each claim should be a distinct finding, result, or conclusion stated in the paper.

RULES:
- Extract ONLY claims that are actually stated in the text
- Do NOT invent or fabricate claims
- Preserve statistical information exactly as stated
- Identify the direction of effect (positive, negative, neutral, mixed, unclear)
- Note effect sizes and confidence intervals if mentioned
- Identify which section the claim comes from (abstract, results, discussion, conclusions)
- A single paper may have multiple claims

Return ONLY valid JSON:
{{
  "claims": [
    {{
      "claim_text": "the exact or closely paraphrased claim",
      "source_section": "abstract or results or discussion or conclusions or methods",
      "source_passage": "the specific text passage supporting this claim",
      "population": "the study population for this claim",
      "intervention": "the intervention or exposure",
      "comparator": "what it was compared to",
      "outcome": "the measured outcome",
      "effect_direction": "positive or negative or neutral or mixed or unclear",
      "effect_size": "effect size if reported (e.g., 'OR 0.78, 95% CI 0.65-0.93')",
      "statistical_info": "p-values, confidence intervals, sample sizes mentioned",
      "confidence": "high or moderate or low"
    }}
  ]
}}

If no evidence claims can be extracted, return {{"claims": []}}

Paper title: {paper.title}
Paper text:
{text}
"""

        data = generate_json(prompt, temperature=0.1, max_tokens=1024, timeout=30)
        raw_claims = data.get("claims", [])
        if not isinstance(raw_claims, list):
            raw_claims = []

        claims = []
        for rc in raw_claims:
            if not isinstance(rc, dict):
                continue
            claim = ExtractedClaim(
                claim_text=rc.get("claim_text", ""),
                source_paper_title=paper.title,
                source_paper_doi=paper.doi,
                source_paper_pmid=paper.pmid,
                source_section=rc.get("source_section", ""),
                source_passage=rc.get("source_passage", ""),
                population=rc.get("population", ""),
                intervention=rc.get("intervention", ""),
                comparator=rc.get("comparator", ""),
                outcome=rc.get("outcome", ""),
                effect_direction=rc.get("effect_direction", "unclear"),
                effect_size=rc.get("effect_size", ""),
                statistical_info=rc.get("statistical_info", ""),
                confidence=rc.get("confidence", "moderate"),
            )
            if claim.claim_text.strip():
                claims.append(claim)

        if claims:
            logger.info(f"Extracted {len(claims)} claims via LLM from: {paper.title[:50]}")
            return claims

        # Fallback if LLM returned 0 claims
        logger.info(f"LLM returned no claims; using heuristic extraction for: {paper.title[:50]}")
        return _extract_claims_heuristic(paper)

    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error extracting claims from {paper.title[:50]}: {e}. Falling back to heuristic.")
        return _extract_claims_heuristic(paper)
    except Exception as e:
        logger.warning(f"LLM claim extraction failed for {paper.title[:50]}: {e}. Falling back to heuristic.")
        return _extract_claims_heuristic(paper)


def _extract_claims_heuristic(paper: NormalizedPaper) -> list:
    """
    Rule-based / NLP heuristic fallback to extract key finding claims
    from paper abstract when LLM extraction fails or is unavailable.
    """
    import re

    text = paper.abstract or paper.full_text or ""
    if not text or len(text.strip()) < 30:
        return []

    # Split into sentences
    raw_sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 25]

    if not sentences:
        return []

    # Keywords signaling key findings or conclusions
    finding_signals = [
        "concluded", "demonstrated", "showed", "found", "revealed", "associated with",
        "reduced", "increased", "decreased", "improved", "significant", "effective",
        "efficacy", "safety", "risk of", "hazard ratio", "odds ratio", "relative risk",
        "p <", "p=", "p-value", "ci", "confidence interval", "in conclusion", "results show",
        "our findings", "trial showed", "treatment with", "compared to", "versus"
    ]

    scored_sentences = []
    for s in sentences:
        s_lower = s.lower()
        score = sum(1 for sig in finding_signals if sig in s_lower)
        # Extra points if has stats or percentages
        if re.search(r'\b\d+(?:\.\d+)?%\b|\bp\s*[<=]\s*0\.\d+|\b(?:HR|OR|RR|CI)\b', s, re.I):
            score += 2
        # Extra points if near the end of the abstract (conclusion section)
        if any(w in s_lower for w in ["conclusion", "conclude", "in summary", "overall"]):
            score += 3
        if score > 0:
            scored_sentences.append((score, s))

    # Sort by score descending
    scored_sentences.sort(key=lambda x: x[0], reverse=True)

    # Pick top 1-3 finding sentences
    selected = [s for _, s in scored_sentences[:3]]
    if not selected and sentences:
        # Pick the last sentence (typical conclusion)
        selected = [sentences[-1]]

    claims = []
    for s in selected:
        s_lower = s.lower()

        # Determine effect direction
        pos_words = ["reduced risk", "decreased risk", "improved", "benefit", "effective", "superior", "positive", "enhanced", "significantly lower", "protective"]
        neg_words = ["increased risk", "higher risk", "adverse", "worsened", "failed", "ineffective", "harmful", "no significant difference", "no benefit", "did not reduce"]

        if any(w in s_lower for w in pos_words):
            direction = "positive"
        elif any(w in s_lower for w in neg_words):
            direction = "negative"
        else:
            direction = "neutral"

        # Extract stats
        stats_matches = re.findall(r'(?:p\s*[<=]\s*0\.\d+|\b(?:95%\s*CI|CI|HR|OR|RR)\s*[:=]?\s*[\d\.\s,-]+|\b\d+(?:\.\d+)?%)', s, re.I)
        stat_info = ", ".join(stats_matches[:3]) if stats_matches else ""

        # Section detection
        section = "abstract"
        if "conclusion" in s_lower:
            section = "conclusion"
        elif "result" in s_lower or "found" in s_lower:
            section = "results"

        claim = ExtractedClaim(
            claim_text=s,
            source_paper_title=paper.title,
            source_paper_doi=paper.doi,
            source_paper_pmid=paper.pmid,
            source_section=section,
            source_passage=s,
            effect_direction=direction,
            statistical_info=stat_info,
            confidence="moderate",
        )
        claims.append(claim)

    logger.info(f"Extracted {len(claims)} heuristic claims from: {paper.title[:50]}")
    return claims


def extract_all_claims(papers: list, max_papers: int = None, progress_fn=None) -> list:
    """
    Extract claims from the top-ranked papers.

    Args:
        papers: List of NormalizedPaper objects, sorted by relevance.
        max_papers: Maximum papers to process.
        progress_fn: Optional callback function(stage, data) for progress reporting.

    Returns:
        List of all ExtractedClaim objects.
    """
    max_papers = max_papers or MAX_PAPERS_FOR_CLAIMS
    papers_to_process = papers[:max_papers]
    all_claims = []

    for i, paper in enumerate(papers_to_process, 1):
        if progress_fn:
            try:
                progress_fn("extracting_claims", {
                    "paper_index": i,
                    "total_papers": len(papers_to_process),
                    "paper_title": paper.title[:60],
                })
            except Exception:
                pass
        claims = extract_claims_from_paper(paper)
        all_claims.extend(claims)

    logger.info(f"Total claims extracted: {len(all_claims)} "
                f"from {len(papers_to_process)} papers")
    return all_claims
