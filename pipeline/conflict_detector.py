"""
conflict_detector.py
Requirements 17-18: Conflict detection and analysis.

Identifies when credible studies report different findings and
investigates why they may disagree.
"""

import json
import logging
from pipeline.llm_client import generate_json
from pipeline.models import ExtractedClaim, ConflictReport

logger = logging.getLogger(__name__)


def detect_conflicts(claims: list) -> list:
    """
    Identify conflicting findings among extracted claims.

    First groups claims by outcome/topic, then checks for
    directional disagreements within each group.

    Args:
        claims: List of ExtractedClaim objects.

    Returns:
        List of ConflictReport objects.
    """
    if len(claims) < 2:
        return []

    # Group claims by general topic area (outcome + intervention)
    groups = _group_claims(claims)

    conflicts = []
    for topic, group_claims in groups.items():
        if len(group_claims) < 2:
            continue

        # Check for directional conflicts within this group
        conflict = _check_group_conflicts(topic, group_claims)
        if conflict:
            conflicts.append(conflict)

    # Use LLM for deeper conflict analysis if we found any
    if conflicts:
        conflicts = _analyze_conflicts_with_llm(conflicts, claims)

    logger.info(f"Conflict detection: found {len(conflicts)} conflicts")
    return conflicts


def _group_claims(claims: list) -> dict:
    """Group claims by their outcome/topic area."""
    groups = {}
    for claim in claims:
        # Create a topic key from outcome and intervention
        key_parts = []
        if claim.intervention:
            key_parts.append(claim.intervention.lower().strip())
        if claim.outcome:
            key_parts.append(claim.outcome.lower().strip())

        if not key_parts:
            key_parts = [claim.claim_text[:50].lower()]

        topic = " + ".join(key_parts)

        if topic not in groups:
            groups[topic] = []
        groups[topic].append(claim)

    return groups


def _check_group_conflicts(topic: str, claims: list) -> ConflictReport:
    """Check for directional conflicts within a group of claims."""
    directions = {}
    for claim in claims:
        d = claim.effect_direction or "unclear"
        if d not in directions:
            directions[d] = []
        directions[d].append(claim)

    # Identify conflicting directions
    conflict_pairs = []

    has_positive = "positive" in directions
    has_negative = "negative" in directions
    has_neutral = "neutral" in directions

    if has_positive and has_negative:
        conflict_pairs.append(("positive", "negative"))
    if has_positive and has_neutral and len(directions.get("neutral", [])) > 0:
        conflict_pairs.append(("positive", "neutral"))
    if has_negative and has_neutral and len(directions.get("neutral", [])) > 0:
        conflict_pairs.append(("negative", "neutral"))

    if not conflict_pairs:
        return None

    # Determine severity
    if has_positive and has_negative:
        severity = "major"
        conflict_type = "direction"
    else:
        severity = "moderate"
        conflict_type = "magnitude"

    # Build conflicting claims list
    conflicting = []
    for claim in claims:
        if claim.effect_direction in ("positive", "negative", "neutral"):
            conflicting.append(claim.to_dict())

    # Identify potential reasons
    potential_reasons = _identify_conflict_reasons(claims)

    return ConflictReport(
        topic=topic,
        conflicting_claims=conflicting,
        conflict_type=conflict_type,
        potential_reasons=potential_reasons,
        severity=severity,
    )


def _identify_conflict_reasons(claims: list) -> list:
    """Identify potential reasons for conflicting findings."""
    reasons = []

    # Check population differences
    populations = set()
    for c in claims:
        if c.population:
            populations.add(c.population.lower().strip())
    if len(populations) > 1:
        reasons.append(f"Different study populations: {', '.join(populations)}")

    # Check study design differences
    designs = set()
    for c in claims:
        text = c.source_passage.lower() if c.source_passage else ""
        if "randomized" in text or "rct" in text:
            designs.add("RCT")
        elif "observational" in text or "cohort" in text:
            designs.add("observational")
        elif "meta-analysis" in text or "systematic" in text:
            designs.add("systematic review")
    if len(designs) > 1:
        reasons.append(f"Different study designs: {', '.join(designs)}")

    # Check for different comparators
    comparators = set()
    for c in claims:
        if c.comparator:
            comparators.add(c.comparator.lower().strip())
    if len(comparators) > 1:
        reasons.append(f"Different comparators: {', '.join(comparators)}")

    # Check different papers (most likely)
    papers = set()
    for c in claims:
        papers.add(c.source_paper_title)
    if len(papers) > 1:
        reasons.append("Findings come from different independent studies")

    if not reasons:
        reasons.append("Exact reason for disagreement unclear from available evidence")

    return reasons


def _analyze_conflicts_with_llm(conflicts: list, all_claims: list) -> list:
    """Use LLM to provide deeper analysis of detected conflicts."""
    try:
        # Prepare conflict summary for LLM
        conflict_summaries = []
        for c in conflicts:
            summary = {
                "topic": c.topic,
                "severity": c.severity,
                "claims": [
                    {
                        "text": cl.get("claim_text", "")[:200],
                        "direction": cl.get("effect_direction", ""),
                        "paper": cl.get("source_paper_title", "")[:100],
                    }
                    for cl in c.conflicting_claims[:6]
                ],
                "initial_reasons": c.potential_reasons,
            }
            conflict_summaries.append(summary)

        prompt = f"""Analyze these scientific evidence conflicts and provide insights.
For each conflict, explain in 1-2 sentences why the studies might disagree.
Do NOT resolve conflicts through majority voting. Present the disagreement honestly.

Conflicts:
{json.dumps(conflict_summaries, indent=2)}

Return ONLY valid JSON:
{{
  "analyses": [
    {{
      "topic": "the conflict topic",
      "resolution_notes": "brief explanation of why studies may disagree and what this means"
    }}
  ]
}}
"""
        data = generate_json(prompt, temperature=0.2)
        analyses = data.get("analyses", [])

        # Map analyses back to conflicts
        for conflict in conflicts:
            for analysis in analyses:
                if analysis.get("topic") == conflict.topic:
                    conflict.resolution_notes = analysis.get("resolution_notes", "")
                    break

    except Exception as e:
        logger.error(f"LLM conflict analysis failed: {e}")
        for conflict in conflicts:
            if not conflict.resolution_notes:
                conflict.resolution_notes = (
                    "Automated analysis could not determine the exact reason "
                    "for disagreement. Consider the differences in study design, "
                    "population, and methodology."
                )

    return conflicts
