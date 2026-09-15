"""
answer_generator.py
Requirements 19-21: Evidence sufficiency, final answer, and complete provenance.

Determines evidence sufficiency, generates a grounded answer with inline
citations, and provides full provenance for every claim.
"""

import json
import logging
from pipeline.llm_client import generate_json
from pipeline.models import (
    QuestionAnalysis, ExtractedClaim, CoverageReport,
    ConflictReport, NormalizedPaper,
)

logger = logging.getLogger(__name__)


def determine_sufficiency(claims: list, coverage: CoverageReport,
                          conflicts: list, papers: list) -> str:
    """
    Determine whether the evidence is sufficient to answer the question.

    Returns: "sufficient", "partially_sufficient", or "insufficient"
    """
    if not claims or not papers:
        return "insufficient"

    # Count high-quality claims
    high_quality = sum(1 for c in claims
                       if c.evidence_quality in ("high", "moderate"))
    good_match = sum(1 for c in claims
                     if c.question_match_score >= 0.4)

    # Check coverage
    coverage_ok = coverage.coverage_score >= 0.6

    # Check for major unresolved conflicts
    major_conflicts = sum(1 for c in conflicts if c.severity == "major")

    if high_quality >= 3 and good_match >= 2 and coverage_ok:
        if major_conflicts == 0:
            return "sufficient"
        else:
            return "partially_sufficient"
    elif high_quality >= 1 and good_match >= 1:
        return "partially_sufficient"
    else:
        return "insufficient"


def generate_answer(question: str, analysis: QuestionAnalysis,
                    claims: list, papers: list,
                    coverage: CoverageReport, conflicts: list,
                    sufficiency: str) -> tuple:
    """
    Generate the final evidence-grounded answer.

    Args:
        question: Original question.
        analysis: Question analysis.
        claims: Scored and matched claims.
        papers: Ranked papers.
        coverage: Coverage report.
        conflicts: Detected conflicts.
        sufficiency: Evidence sufficiency level.

    Returns:
        Tuple of (answer_text, confidence, citations_list).
    """
    # Build the citation index (top papers used as evidence)
    citation_papers = []
    seen_titles = set()
    for claim in claims:
        for paper in papers:
            if paper.title == claim.source_paper_title and paper.title not in seen_titles:
                citation_papers.append(paper)
                seen_titles.add(paper.title)
                break
        if len(citation_papers) >= 15:
            break

    # Add top papers even if no claims matched
    for paper in papers[:5]:
        if paper.title not in seen_titles:
            citation_papers.append(paper)
            seen_titles.add(paper.title)

    # Build citations list
    citations = []
    for i, paper in enumerate(citation_papers, 1):
        citation = {
            "index": i,
            "title": paper.title,
            "authors": _format_authors(paper.authors),
            "year": paper.pub_year,
            "journal": paper.journal,
            "doi": paper.doi,
            "pmid": paper.pmid,
            "pmcid": paper.pmcid,
            "core_id": paper.core_id,
            "source": ", ".join(paper.found_in_sources),
            "url": paper.url or (f"https://doi.org/{paper.doi}" if paper.doi else ""),
            "evidence_level": paper.evidence_level,
            "relevance_score": paper.relevance_score,
        }
        citations.append(citation)

    # Build claims summary for the LLM
    claims_text = _format_claims_for_prompt(claims[:15], citation_papers)

    # Build conflict summary
    conflict_text = ""
    if conflicts:
        conflict_text = "\n\nCONFLICTS DETECTED:\n"
        for c in conflicts:
            conflict_text += f"- {c.topic}: {c.resolution_notes or 'Studies disagree'}\n"

    # Build the prompt with structured formatting instructions
    prompt = f"""You are a scientific evidence synthesizer. Generate a structured, highly-readable, and engaging answer to the research question based ONLY on the provided evidence.

RESEARCH QUESTION: {question}

QUESTION ANALYSIS:
- Domain: {analysis.domain}
- Population: {analysis.population}
- Intervention: {analysis.intervention}
- Comparator: {analysis.comparator}
- Outcome: {analysis.outcome}
- Dose: {analysis.dose}
- Frequency: {analysis.frequency}

EVIDENCE SUFFICIENCY: {sufficiency}
COVERAGE: {coverage.coverage_summary}
Missing areas: {', '.join(coverage.missing_areas) if coverage.missing_areas else 'None'}

EVIDENCE CLAIMS:
{claims_text}
{conflict_text}

FORMATTING & STRUCTURE INSTRUCTIONS:
Structure your answer into clear, beautifully organized sections using Markdown headers:

### 📌 Executive Summary
Provide a crisp 1-2 sentence direct bottom-line answer to the question. Highlight the central finding.

### 🔬 Key Findings & Evidence
Provide 2-4 bullet points (- ) detailing specific findings:
- Use **bold text** for key drug names, effect sizes, statistical values (e.g. **HR 0.78**, **p = 0.005**, **HbA1c reduction of 1.2%**), and specific populations.
- Cite supporting studies using inline citations [1], [2], etc.

### ⚖️ Consistency & Study Comparison
Compare results across studies. Note if studies agree, differ in magnitude, or have conflicting directions. Explain any nuances honestly.

### 💡 Clinical & Practical Takeaways
1-2 sentences on what this evidence means in practice or research.

### ⚠️ Limitations & Evidence Gaps
Mention key limitations, missing patient subgroups, or unanswered questions from the current evidence.

RULES:
- Base all claims strictly on the provided evidence claims. Do NOT fabricate numbers or facts.
- Use citations like [1], [2] referencing the numbered studies.
- Keep paragraphs concise (2-4 lines each) to maximize scannability and readability.

Return ONLY valid JSON:
{{
  "answer": "the structured markdown answer text with headers, bullet points, bold key stats, and [1], [2] citations",
  "confidence": "high" or "moderate" or "low" or "very_low" or "insufficient"
}}
"""

    try:
        data = generate_json(prompt, temperature=0.2, max_tokens=1536)
        answer = data.get("answer", "Unable to generate answer from available evidence.")
        confidence = data.get("confidence", "low")

        logger.info(f"Answer generated. Confidence: {confidence}")
        return answer, confidence, citations

    except Exception as e:
        logger.error(f"Answer generation failed: {e}")

        # Fallback: generate a basic answer without LLM
        answer = _generate_fallback_answer(
            question, claims, papers, coverage, conflicts, sufficiency
        )
        return answer, "low", citations


def _format_authors(authors: list) -> str:
    """Format authors list into a string."""
    if not authors:
        return "Unknown authors"

    names = []
    for a in authors[:3]:
        if isinstance(a, dict):
            names.append(a.get("name", ""))
        elif isinstance(a, str):
            names.append(a)

    result = ", ".join(n for n in names if n)
    if len(authors) > 3:
        result += " et al."
    return result or "Unknown authors"


def _format_claims_for_prompt(claims: list, citation_papers: list) -> str:
    """Format claims with citation indices for the LLM prompt."""
    # Build title to citation index mapping
    title_to_idx = {}
    for i, p in enumerate(citation_papers, 1):
        title_to_idx[p.title] = i

    lines = []
    for claim in claims:
        idx = title_to_idx.get(claim.source_paper_title, "?")
        line = (
            f"[{idx}] {claim.claim_text} "
            f"(Effect: {claim.effect_direction}, "
            f"Quality: {claim.evidence_quality}, "
            f"Match: {claim.question_match_score:.2f})"
        )
        if claim.effect_size:
            line += f" [Effect size: {claim.effect_size}]"
        if claim.statistical_info:
            line += f" [Stats: {claim.statistical_info}]"
        lines.append(line)

    return "\n".join(lines) if lines else "No specific evidence claims available."


def _generate_fallback_answer(question, claims, papers, coverage,
                              conflicts, sufficiency):
    """Generate a structured, evidence-grounded answer when the LLM call fails or times out."""
    title_to_idx = {p.title: i for i, p in enumerate(papers[:15], 1)}

    lines = [
        "### 📌 Executive Summary",
    ]

    if claims:
        top_claim = claims[0].claim_text.rstrip(".")
        first_idx = title_to_idx.get(claims[0].source_paper_title, 1)
        lines.append(
            f"Based on evidence synthesized from {len(papers)} retrieved scientific studies, "
            f"key findings indicate that {top_claim.lower() if not top_claim.startswith('In') else top_claim} [{first_idx}]."
        )
    else:
        lines.append(
            f"Literature search returned {len(papers)} relevant publications regarding \"{question}\". "
            "However, direct atomic claims were limited and require closer contextual review."
        )

    lines.append("\n### 🔬 Key Findings & Evidence")
    if claims:
        for claim in claims[:6]:
            idx = title_to_idx.get(claim.source_paper_title, "?")
            stats_str = f" (**{claim.statistical_info}**)" if claim.statistical_info else ""
            effect_str = f" **{claim.effect_direction}**" if claim.effect_direction and claim.effect_direction != "unclear" else ""
            lines.append(f"- {claim.claim_text}{stats_str} [{idx}]")
    elif papers:
        for i, p in enumerate(papers[:4], 1):
            sample_text = (p.abstract or p.title)[:160].rstrip(".")
            lines.append(f"- **{p.title}**: {sample_text}... [{i}]")

    lines.append("\n### ⚖️ Consistency & Study Comparison")
    if conflicts:
        conflict_desc = "; ".join([c.topic for c in conflicts[:2]])
        lines.append(f"Variations were noted across studies regarding {conflict_desc}. Differences may relate to study designs or cohort variations.")
    elif len(papers) > 1:
        lines.append(f"The reviewed publications ({len(papers)} sources) demonstrate broad thematic consistency regarding the central research inquiry.")
    else:
        lines.append("Single primary publication analyzed; further multi-center trials are warranted.")

    lines.append("\n### 💡 Clinical & Practical Takeaways")
    lines.append(f"The identified evidence provides supportive backing for research decisions relating to {question.rstrip('?').lower()}.")

    lines.append("\n### ⚠️ Limitations & Evidence Gaps")
    if coverage and coverage.missing_areas:
        lines.append(f"Areas requiring further focused investigation include: {', '.join(coverage.missing_areas)}.")
    else:
        lines.append("Generalizability may be constrained by study inclusion criteria and publication date ranges.")

    return "\n".join(lines)
