"""
orchestrator.py
Requirements 22-23: Pipeline coordination, transparency, and failure handling.

Coordinates all pipeline stages in sequence, collects metadata,
handles errors gracefully, and produces the complete ResearchResult.
"""

import time
import logging
from config import MAX_QUERY_REFINEMENT_RETRIES, MAX_FULLTEXT_FETCHES, MAX_PAPERS_FOR_CLAIMS
from pipeline.models import (
    ResearchResult, PipelineMetadata, QuestionAnalysis,
    ExpandedQueries, CoverageReport,
)
from pipeline.question_analyzer import analyze_question
from pipeline.query_expander import expand_queries
from pipeline.source_selector import select_sources
from pipeline.search_clients.core_client import search_core_multi
from pipeline.search_clients.europepmc_client import search_europepmc_multi
from pipeline.search_clients.fulltext_fetcher import fetch_fulltext_for_papers
from pipeline.paper_normalizer import normalize_all
from pipeline.deduplicator import deduplicate
from pipeline.retraction_checker import check_retractions, filter_usable_papers
from pipeline.relevance_ranker import rank_papers
from pipeline.claim_extractor import extract_all_claims
from pipeline.question_matcher import match_all_claims
from pipeline.quality_assessor import assess_all_claims
from pipeline.coverage_analyzer import analyze_coverage, generate_refined_queries
from pipeline.conflict_detector import detect_conflicts
from pipeline.answer_generator import generate_answer, determine_sufficiency

logger = logging.getLogger(__name__)


def run_research_pipeline(question: str, progress_callback=None) -> ResearchResult:
    """
    Run the full evidence research pipeline for a given question.

    Args:
        question: The user's natural-language research question.
        progress_callback: Optional function(stage_name, stage_data) called
                          after each stage completes.

    Returns:
        Complete ResearchResult with answer, evidence, and metadata.
    """
    result = ResearchResult(question=question)
    metadata = PipelineMetadata()
    start_time = time.time()

    def _progress(stage, data=None):
        entry = {"stage": stage, "time": round(time.time() - start_time, 2)}
        if data:
            entry["details"] = data
        metadata.processing_stages.append(entry)
        if progress_callback:
            try:
                progress_callback(stage, entry)
            except Exception:
                pass

    try:
        # ══════════════════════════════════════════════════════════════
        # STAGE 1: Understand the question
        # ══════════════════════════════════════════════════════════════
        _progress("analyzing_question")
        analysis = analyze_question(question)
        result.question_analysis = analysis.to_dict()
        metadata.question_interpretation = analysis.to_dict()
        _progress("question_analyzed", {
            "domain": analysis.domain,
            "type": analysis.question_type,
        })

        # ══════════════════════════════════════════════════════════════
        # STAGE 2: Expand queries
        # ══════════════════════════════════════════════════════════════
        _progress("expanding_queries")
        expanded = expand_queries(analysis)
        result.expanded_queries = expanded.to_dict()
        metadata.search_terms_generated = {
            "core_queries": expanded.core_queries,
            "europepmc_queries": expanded.europepmc_queries,
            "synonyms": expanded.synonyms_used,
        }
        _progress("queries_expanded", {
            "core_queries": len(expanded.core_queries),
            "europepmc_queries": len(expanded.europepmc_queries),
        })

        # ══════════════════════════════════════════════════════════════
        # STAGE 3: Select sources
        # ══════════════════════════════════════════════════════════════
        sources = select_sources(analysis)
        metadata.sources_searched = sources
        _progress("sources_selected", {"sources": sources})

        # ══════════════════════════════════════════════════════════════
        # STAGE 4: Search APIs
        # ══════════════════════════════════════════════════════════════
        _progress("searching_literature")
        core_raw = []
        europepmc_raw = []

        if "core" in sources:
            try:
                core_raw = search_core_multi(expanded.core_queries)
                metadata.papers_found_per_source["core"] = len(core_raw)
            except Exception as e:
                logger.error(f"CORE search failed: {e}")
                metadata.errors.append(f"CORE search error: {e}")

        if "europepmc" in sources:
            try:
                europepmc_raw = search_europepmc_multi(expanded.europepmc_queries)
                metadata.papers_found_per_source["europepmc"] = len(europepmc_raw)
            except Exception as e:
                logger.error(f"Europe PMC search failed: {e}")
                metadata.errors.append(f"Europe PMC search error: {e}")

        metadata.total_papers_found = len(core_raw) + len(europepmc_raw)
        _progress("search_complete", {
            "core": len(core_raw),
            "europepmc": len(europepmc_raw),
            "total": metadata.total_papers_found,
        })

        # ══════════════════════════════════════════════════════════════
        # STAGE 5: Normalize papers
        # ══════════════════════════════════════════════════════════════
        _progress("normalizing_papers")
        all_papers = normalize_all(core_raw, europepmc_raw)

        # ══════════════════════════════════════════════════════════════
        # STAGE 6: Deduplicate
        # ══════════════════════════════════════════════════════════════
        _progress("deduplicating")
        all_papers, dups_removed = deduplicate(all_papers)
        metadata.duplicates_removed = dups_removed
        metadata.papers_after_dedup = len(all_papers)
        _progress("deduplicated", {
            "unique_papers": len(all_papers),
            "duplicates_removed": dups_removed,
        })

        # ══════════════════════════════════════════════════════════════
        # STAGE 7: Check retractions
        # ══════════════════════════════════════════════════════════════
        _progress("checking_retractions")
        all_papers, retracted = check_retractions(all_papers)
        metadata.retracted_papers = retracted
        usable_papers = filter_usable_papers(all_papers)
        _progress("retractions_checked", {
            "retracted": len(retracted),
            "usable": len(usable_papers),
        })

        # ══════════════════════════════════════════════════════════════
        # STAGE 8: Rank by relevance
        # ══════════════════════════════════════════════════════════════
        _progress("ranking_papers")
        ranked_papers = rank_papers(usable_papers, analysis)
        metadata.top_ranked_papers = [
            {"title": p.title[:80], "score": p.relevance_score}
            for p in ranked_papers[:10]
        ]
        _progress("papers_ranked", {"ranked_count": len(ranked_papers)})

        # ══════════════════════════════════════════════════════════════
        # STAGE 9: Fetch full text for top papers
        # ══════════════════════════════════════════════════════════════
        _progress("fetching_fulltext")
        ranked_papers = fetch_fulltext_for_papers(
            ranked_papers[:MAX_PAPERS_FOR_CLAIMS + 2],
            max_fetches=MAX_FULLTEXT_FETCHES,
        )
        fulltext_count = sum(1 for p in ranked_papers
                             if p.evidence_level == "full_text")
        metadata.fulltext_fetched = fulltext_count
        _progress("fulltext_fetched", {"fetched": fulltext_count})

        # ══════════════════════════════════════════════════════════════
        # STAGE 10: Extract claims
        # ══════════════════════════════════════════════════════════════
        _progress("extracting_claims")
        claims = extract_all_claims(
            ranked_papers,
            max_papers=MAX_PAPERS_FOR_CLAIMS,
            progress_fn=_progress,
        )
        _progress("claims_extracted", {"count": len(claims)})

        # ══════════════════════════════════════════════════════════════
        # STAGE 11: Match claims to question
        # ══════════════════════════════════════════════════════════════
        _progress("matching_claims")
        claims = match_all_claims(claims, analysis)

        # ══════════════════════════════════════════════════════════════
        # STAGE 12: Assess quality
        # ══════════════════════════════════════════════════════════════
        _progress("assessing_quality")
        claims = assess_all_claims(claims, ranked_papers)
        metadata.claims_extracted = len(claims)
        _progress("quality_assessed", {"claims_scored": len(claims)})

        # ══════════════════════════════════════════════════════════════
        # STAGE 13: Check coverage + refine if needed
        # ══════════════════════════════════════════════════════════════
        _progress("analyzing_coverage")
        coverage = analyze_coverage(claims, analysis)
        result.coverage = coverage.to_dict()

        # Automatic query refinement if coverage is insufficient
        refinement_round = 0
        while (coverage.needs_refinement and
               refinement_round < MAX_QUERY_REFINEMENT_RETRIES):
            refinement_round += 1
            _progress(f"refining_search_round_{refinement_round}", {
                "missing": coverage.missing_areas,
            })

            refined = generate_refined_queries(
                analysis, coverage, refinement_round
            )
            metadata.search_refinements.append({
                "round": refinement_round,
                "queries": refined,
                "reason": coverage.missing_areas,
            })

            # Search again with refined queries
            new_core_raw = []
            new_epmc_raw = []

            if "core" in sources and refined.get("core_queries"):
                try:
                    new_core_raw = search_core_multi(
                        refined["core_queries"],
                        limit_per_query=5,
                    )
                except Exception as e:
                    logger.error(f"Refined CORE search failed: {e}")

            if "europepmc" in sources and refined.get("europepmc_queries"):
                try:
                    new_epmc_raw = search_europepmc_multi(
                        refined["europepmc_queries"],
                        limit_per_query=5,
                    )
                except Exception as e:
                    logger.error(f"Refined Europe PMC search failed: {e}")

            if new_core_raw or new_epmc_raw:
                new_papers = normalize_all(new_core_raw, new_epmc_raw)
                existing_titles = {p.title.lower().strip() for p in ranked_papers}
                fresh_papers = [
                    p for p in new_papers
                    if p.title.lower().strip() not in existing_titles
                ]

                # Merge with existing papers
                combined = ranked_papers + fresh_papers
                combined, _ = deduplicate(combined)
                combined, _ = check_retractions(combined)
                combined = filter_usable_papers(combined)
                ranked_papers = rank_papers(combined, analysis)

                # Extract claims from up to 2 fresh papers and add to existing claims
                if fresh_papers:
                    fresh_claims = extract_all_claims(
                        fresh_papers,
                        max_papers=2,
                        progress_fn=_progress,
                    )
                    claims.extend(fresh_claims)

                claims = match_all_claims(claims, analysis)
                claims = assess_all_claims(claims, ranked_papers)
                coverage = analyze_coverage(claims, analysis)
                result.coverage = coverage.to_dict()

            _progress(f"refinement_complete_round_{refinement_round}", {
                "new_papers": len(new_core_raw) + len(new_epmc_raw),
                "coverage_score": coverage.coverage_score,
            })

        _progress("coverage_analyzed", {
            "score": coverage.coverage_score,
            "refinements": refinement_round,
        })

        # ══════════════════════════════════════════════════════════════
        # STAGE 14: Detect conflicts
        # ══════════════════════════════════════════════════════════════
        _progress("detecting_conflicts")
        conflicts = detect_conflicts(claims)
        metadata.conflicts_detected = len(conflicts)
        result.conflicts = [c.to_dict() for c in conflicts]
        _progress("conflicts_detected", {"count": len(conflicts)})

        # ══════════════════════════════════════════════════════════════
        # STAGE 15: Determine sufficiency + generate answer
        # ══════════════════════════════════════════════════════════════
        _progress("generating_answer")
        sufficiency = determine_sufficiency(claims, coverage, conflicts,
                                            ranked_papers)
        metadata.evidence_sufficient = sufficiency
        result.evidence_sufficiency = sufficiency

        answer, confidence, citations = generate_answer(
            question, analysis, claims, ranked_papers,
            coverage, conflicts, sufficiency,
        )

        result.answer = answer
        result.confidence = confidence
        result.citations = citations
        result.claims = [c.to_dict() for c in claims]
        result.papers = [p.to_dict() for p in ranked_papers[:20]]

        _progress("answer_generated", {
            "confidence": confidence,
            "sufficiency": sufficiency,
            "citations": len(citations),
        })

    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        metadata.errors.append(f"Pipeline error: {str(e)}")
        result.answer = (
            f"An error occurred during the research process: {str(e)}. "
            f"Please try again or rephrase your question."
        )
        result.confidence = "insufficient"
        _progress("error", {"error": str(e)})

    # Finalize
    total_time = round(time.time() - start_time, 2)
    metadata.processing_stages.append({
        "stage": "complete",
        "time": total_time,
    })
    result.pipeline_metadata = metadata.to_dict()

    logger.info(f"Pipeline complete in {total_time}s")
    return result
