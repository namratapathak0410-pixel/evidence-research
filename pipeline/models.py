"""
models.py
Data classes used throughout the evidence research pipeline.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class QuestionAnalysis:
    """Structured understanding of the user's research question."""
    original_question: str = ""
    domain: str = ""                      # "medical", "scientific", "mixed"
    question_type: str = ""               # "intervention", "diagnostic", "prognostic", "etiology", "general"

    # PICO(T) elements
    population: str = ""
    intervention: str = ""
    comparator: str = ""
    outcome: str = ""
    condition: str = ""
    study_type_preference: str = ""

    # Medical/pharmacological specifics
    drug: str = ""
    dose: str = ""
    frequency: str = ""
    route_of_administration: str = ""
    treatment_duration: str = ""
    age_group: str = ""
    clinical_outcome: str = ""

    # Key concepts for search
    key_concepts: list = field(default_factory=list)
    scientific_context: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v}


@dataclass
class ExpandedQueries:
    """Search query variations generated from the question analysis."""
    original_question: str = ""
    core_queries: list = field(default_factory=list)      # queries for CORE API
    europepmc_queries: list = field(default_factory=list)  # queries for Europe PMC
    synonyms_used: list = field(default_factory=list)
    expansion_notes: str = ""

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class NormalizedPaper:
    """Unified paper representation across sources."""
    # Core identifiers
    title: str = ""
    authors: list = field(default_factory=list)          # list of {"name": ..., "affiliation": ...}
    abstract: str = ""
    pub_year: Optional[int] = None
    pub_date: str = ""
    journal: str = ""

    # Identifiers
    doi: str = ""
    pmid: str = ""
    pmcid: str = ""
    core_id: str = ""

    # Source tracking
    source: str = ""                    # "core", "europepmc"
    found_in_sources: list = field(default_factory=list)  # for dedup tracking

    # Content
    full_text: str = ""
    full_text_available: bool = False
    evidence_level: str = "metadata_only"  # "full_text", "abstract_only", "metadata_only"

    # Classification
    study_type: str = ""
    document_type: str = ""
    publication_status: str = "normal"  # "normal", "retracted", "corrected", "expression_of_concern", "withdrawn"
    retraction_note: str = ""

    # Metadata
    keywords: list = field(default_factory=list)
    mesh_terms: list = field(default_factory=list)
    url: str = ""
    download_url: str = ""

    # Scores (filled by later stages)
    relevance_score: float = 0.0
    quality_score: float = 0.0
    evidence_score: float = 0.0

    # Extra source-specific metadata
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            if v or v == 0:
                if k == "extra" and not v:
                    continue
                d[k] = v
        return d


@dataclass
class ExtractedClaim:
    """An individual evidence-bearing claim extracted from a paper."""
    claim_text: str = ""
    source_paper_title: str = ""
    source_paper_doi: str = ""
    source_paper_pmid: str = ""
    source_section: str = ""              # "abstract", "results", "discussion", "conclusions"
    source_passage: str = ""

    # PICO mapping
    population: str = ""
    intervention: str = ""
    comparator: str = ""
    outcome: str = ""

    # Effect details
    effect_direction: str = ""            # "positive", "negative", "neutral", "mixed", "unclear"
    effect_size: str = ""
    statistical_info: str = ""
    confidence: str = ""                  # "high", "moderate", "low"

    # Question match scores (filled by question_matcher)
    population_match: str = ""            # "exact", "partial", "indirect", "no_match"
    intervention_match: str = ""
    comparator_match: str = ""
    outcome_match: str = ""
    dose_match: str = ""
    duration_match: str = ""
    study_design_match: str = ""
    question_match_score: float = 0.0

    # Quality (filled by quality_assessor)
    evidence_quality: str = ""            # "high", "moderate", "low", "very_low"
    quality_reasoning: str = ""
    unified_score: float = 0.0

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v}


@dataclass
class CoverageReport:
    """Assessment of how well the evidence covers the question."""
    population_covered: bool = False
    intervention_covered: bool = False
    comparator_covered: bool = False
    outcome_covered: bool = False
    dose_covered: bool = False
    duration_covered: bool = False
    study_type_covered: bool = False

    coverage_score: float = 0.0           # 0-1
    missing_areas: list = field(default_factory=list)
    covered_areas: list = field(default_factory=list)
    coverage_summary: str = ""
    needs_refinement: bool = False
    refinement_suggestions: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class ConflictReport:
    """A detected disagreement between studies."""
    topic: str = ""
    conflicting_claims: list = field(default_factory=list)  # list of ExtractedClaim dicts
    conflict_type: str = ""               # "direction", "magnitude", "population_specific"
    potential_reasons: list = field(default_factory=list)
    resolution_notes: str = ""
    severity: str = ""                    # "major", "moderate", "minor"

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        return d


@dataclass
class PipelineMetadata:
    """Transparency metadata about what the pipeline did."""
    question_interpretation: dict = field(default_factory=dict)
    search_terms_generated: dict = field(default_factory=dict)
    sources_searched: list = field(default_factory=list)
    papers_found_per_source: dict = field(default_factory=dict)
    total_papers_found: int = 0
    duplicates_removed: int = 0
    retracted_papers: list = field(default_factory=list)
    papers_after_dedup: int = 0
    top_ranked_papers: list = field(default_factory=list)
    claims_extracted: int = 0
    evidence_sufficient: str = ""         # "sufficient", "partially_sufficient", "insufficient"
    search_refinements: list = field(default_factory=list)
    conflicts_detected: int = 0
    fulltext_fetched: int = 0
    processing_stages: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class ResearchResult:
    """Complete result of the evidence research pipeline."""
    # Core answer
    question: str = ""
    answer: str = ""
    confidence: str = ""                  # "high", "moderate", "low", "very_low", "insufficient"
    evidence_sufficiency: str = ""

    # Structured components
    question_analysis: dict = field(default_factory=dict)
    expanded_queries: dict = field(default_factory=dict)
    papers: list = field(default_factory=list)             # list of NormalizedPaper dicts
    claims: list = field(default_factory=list)             # list of ExtractedClaim dicts
    coverage: dict = field(default_factory=dict)
    conflicts: list = field(default_factory=list)          # list of ConflictReport dicts
    citations: list = field(default_factory=list)          # ordered citation list for the answer

    # Transparency
    pipeline_metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.__dict__
