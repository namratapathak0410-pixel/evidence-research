"""
source_selector.py
Requirement 3: Intelligent source selection.

Determines which API sources to query based on the question domain.
Uses the domain classification from question_analyzer plus keyword
reinforcement.
"""

import logging
from pipeline.models import QuestionAnalysis

logger = logging.getLogger(__name__)

# Keywords that strongly indicate biomedical content → Europe PMC
BIOMEDICAL_KEYWORDS = {
    "disease", "diseases", "drug", "drugs", "treatment", "treatments",
    "patient", "patients", "clinical", "diagnosis", "therapy", "therapies",
    "medication", "medications", "symptom", "symptoms", "cancer",
    "diabetes", "cardiovascular", "hospital", "surgery", "randomized",
    "placebo", "adverse", "efficacy", "safety", "trial", "trials",
    "injection", "oral", "intravenous", "prognosis", "mortality",
    "morbidity", "biomarker", "biomarkers", "pathology", "epidemiology",
    "prevalence", "incidence", "dose", "dosage", "metformin", "insulin",
    "statin", "antibiotic", "chemotherapy", "immunotherapy", "vaccine",
    "infection", "inflammation", "chronic", "acute", "syndrome",
    "disorder", "transplant", "biopsy", "radiology", "oncology",
    "cardiology", "neurology", "psychiatry", "pediatric", "geriatric",
    "pharmacology", "toxicology", "genomics", "proteomics",
    "randomised", "blinded", "double-blind", "cohort", "case-control",
    "meta-analysis", "systematic review", "rct", "medical", "medicine",
    "healthcare", "health care", "health", "pharmaceutical",
}

# Keywords that strongly indicate general scientific content → CORE
SCIENTIFIC_KEYWORDS = {
    "algorithm", "algorithms", "neural network", "neural networks",
    "machine learning", "deep learning", "computing", "computation",
    "software", "engineering", "physics", "mathematics", "mathematical",
    "robotics", "optimization", "simulation", "information retrieval",
    "transformer", "transformers", "natural language processing", "nlp",
    "artificial intelligence", "computer science", "data science",
    "quantum", "cryptography", "blockchain", "database", "cloud",
    "distributed", "parallel", "compiler", "operating system",
    "network", "networking", "cybersecurity", "iot", "sensor",
    "semiconductor", "nanotechnology", "material science", "materials",
    "renewable energy", "solar", "wind energy", "battery",
    "reinforcement learning", "generative", "large language model",
    "llm", "gpt", "bert", "convolutional", "recurrent",
    "classification", "clustering", "dimensionality",
    "scientific", "research", "computational",
}


def select_sources(analysis: QuestionAnalysis) -> list:
    """
    Determine which API sources to query based on question analysis.

    Args:
        analysis: Structured question analysis.

    Returns:
        List of source names: ["core"], ["europepmc"], or ["core", "europepmc"].
    """
    domain = analysis.domain.lower()

    # Primary decision from LLM-determined domain
    if domain == "medical":
        sources = ["europepmc"]
    elif domain == "scientific":
        sources = ["core"]
    elif domain == "mixed":
        sources = ["core", "europepmc"]
    else:
        # Fallback: keyword-based reinforcement
        sources = _keyword_based_selection(analysis)

    # Keyword reinforcement: check if domain classification missed something
    sources = _reinforce_selection(analysis, sources)

    logger.info(f"Selected sources: {sources} (domain={domain})")
    return sources


def _keyword_based_selection(analysis: QuestionAnalysis) -> list:
    """Fallback source selection using keyword matching."""
    text = " ".join([
        analysis.original_question,
        analysis.intervention,
        analysis.population,
        analysis.outcome,
        analysis.condition,
        " ".join(analysis.key_concepts),
    ]).lower()

    bio_score = sum(1 for kw in BIOMEDICAL_KEYWORDS if kw in text)
    sci_score = sum(1 for kw in SCIENTIFIC_KEYWORDS if kw in text)

    if bio_score > 0 and sci_score > 0:
        return ["core", "europepmc"]
    elif bio_score > sci_score:
        return ["europepmc"]
    elif sci_score > bio_score:
        return ["core"]
    else:
        # Default: search both if we can't tell
        return ["core", "europepmc"]


def _reinforce_selection(analysis: QuestionAnalysis, sources: list) -> list:
    """Add a missing source if keywords strongly suggest it should be included."""
    text = " ".join([
        analysis.original_question,
        analysis.intervention,
        analysis.population,
        analysis.outcome,
        analysis.condition,
        " ".join(analysis.key_concepts),
    ]).lower()

    bio_hits = sum(1 for kw in BIOMEDICAL_KEYWORDS if kw in text)
    sci_hits = sum(1 for kw in SCIENTIFIC_KEYWORDS if kw in text)

    # If we chose only one source but there are strong signals for the other
    if "europepmc" not in sources and bio_hits >= 3:
        sources.append("europepmc")
        logger.info("Added europepmc due to strong biomedical keyword signals")

    if "core" not in sources and sci_hits >= 3:
        sources.append("core")
        logger.info("Added core due to strong scientific keyword signals")

    return sources
