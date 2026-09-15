"""
question_analyzer.py
Requirement 1: Understand the user's research question.

Uses a local LLM (via Ollama) to parse a natural-language question into structured
PICO(T) elements and medical/pharmacological details.
"""

import json
import logging
from pipeline.llm_client import generate_json
from pipeline.models import QuestionAnalysis

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """You are a scientific research question analyst.

Analyze the following research question and extract structured information.
Return ONLY valid JSON with these fields (use empty string "" if not applicable):

{
  "domain": "medical" or "scientific" or "mixed",
  "question_type": "intervention" or "diagnostic" or "prognostic" or "etiology" or "general",
  "population": "the study population or subjects",
  "intervention": "the intervention, treatment, method, or technology being studied",
  "comparator": "what the intervention is compared against",
  "outcome": "the measured outcome or endpoint",
  "condition": "the disease, condition, or context",
  "study_type_preference": "preferred study type if implied (e.g., RCT, systematic review)",
  "drug": "drug name if applicable",
  "dose": "dosage if mentioned",
  "frequency": "dosing frequency if mentioned",
  "route_of_administration": "route if mentioned (oral, IV, etc.)",
  "treatment_duration": "treatment duration if mentioned",
  "age_group": "age group if specified",
  "clinical_outcome": "specific clinical outcome if mentioned",
  "key_concepts": ["list", "of", "key", "scientific", "concepts"],
  "scientific_context": "brief description of the scientific/medical context"
}

IMPORTANT RULES:
- Preserve ALL specific details (doses, frequencies, populations, comparators)
- Do NOT lose important medical details during analysis
- "domain" should be "medical" for health/disease/drug/treatment questions
- "domain" should be "scientific" for CS/physics/engineering/math questions
- "domain" should be "mixed" for questions combining technology with medicine
- Extract ALL key concepts that would be useful for searching literature

Research question: """


def analyze_question(question: str) -> QuestionAnalysis:
    """
    Parse a natural-language research question into structured elements.

    Args:
        question: The user's research question in natural language.

    Returns:
        QuestionAnalysis with structured PICO elements and metadata.
    """
    analysis = QuestionAnalysis(original_question=question)

    try:
        data = generate_json(ANALYSIS_PROMPT + question, temperature=0.1)

        # Map parsed data to QuestionAnalysis fields
        analysis.domain = data.get("domain", "scientific")
        analysis.question_type = data.get("question_type", "general")
        analysis.population = data.get("population", "")
        analysis.intervention = data.get("intervention", "")
        analysis.comparator = data.get("comparator", "")
        analysis.outcome = data.get("outcome", "")
        analysis.condition = data.get("condition", "")
        analysis.study_type_preference = data.get("study_type_preference", "")
        analysis.drug = data.get("drug", "")
        analysis.dose = data.get("dose", "")
        analysis.frequency = data.get("frequency", "")
        analysis.route_of_administration = data.get("route_of_administration", "")
        analysis.treatment_duration = data.get("treatment_duration", "")
        analysis.age_group = data.get("age_group", "")
        analysis.clinical_outcome = data.get("clinical_outcome", "")
        analysis.key_concepts = data.get("key_concepts", [])
        analysis.scientific_context = data.get("scientific_context", "")

        logger.info(f"Question analyzed: domain={analysis.domain}, "
                     f"type={analysis.question_type}")

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        # Fallback: basic analysis
        analysis.domain = _guess_domain(question)
        analysis.key_concepts = _extract_basic_concepts(question)

    except Exception as e:
        logger.warning(f"LLM question analysis failed ({e}), using rule-based fallback analyzer.")
        _populate_fallback_analysis(analysis, question)

    return analysis


def _populate_fallback_analysis(analysis: QuestionAnalysis, question: str) -> None:
    """Populate structured PICO analysis using rule-based and regex extraction."""
    import re
    q = question.strip()
    q_lower = q.lower()

    analysis.domain = _guess_domain(q)
    analysis.key_concepts = _extract_basic_concepts(q)

    # 1. Dose & Frequency
    dose_match = re.search(r'\b(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu|units))\b', q, re.I)
    if dose_match:
        analysis.dose = dose_match.group(1)

    freq_match = re.search(r'\b(once|twice|thrice|\d+\s*times)\s*(?:daily|per day|weekly|a day)\b|\b(?:daily|bid|tid|qid|prn)\b', q, re.I)
    if freq_match:
        analysis.frequency = freq_match.group(0)

    # 2. Population & Condition
    pop_cond_match = re.search(r'\b(?:in|among|for)\s+((?:adults|children|patients|elderly|men|women|individuals|subjects)(?:\s+with\s+[^?,;]+)?)\b', q, re.I)
    if pop_cond_match:
        analysis.population = pop_cond_match.group(1).strip()
        cond_in_pop = re.search(r'\bwith\s+([^?,;]+)', analysis.population, re.I)
        if cond_in_pop:
            analysis.condition = cond_in_pop.group(1).strip()
    else:
        cond_match = re.search(r'\b(?:in|with)\s+([a-z0-9\s]+(?:diabetes|cancer|disease|syndrome|hypertension|infection|disorder|failure))\b', q, re.I)
        if cond_match:
            analysis.condition = cond_match.group(1).strip()
            analysis.population = f"Patients with {analysis.condition}"

    # 3. Comparator
    comp_match = re.search(r'\b(?:compared\s+with|compared\s+to|versus|vs\.?)\s+([^?,;]+?)(?:\s+in|\s+for|\?|$)', q, re.I)
    if comp_match:
        analysis.comparator = comp_match.group(1).strip()

    # 4. Intervention & Outcome
    intv_match = re.search(r'^(?:does|do|can|is|are|will|effect\s+of|role\s+of|impact\s+of|what\s+are\s+recent\s+applications\s+of|how\s+effective\s+are)\s+([^?,;]+?)(?:\s+(?:reduce|prevent|improve|increase|treat|affect|compared|in\s+patients|in\s+adults|using|for)\b|\?|$)', q, re.I)
    if intv_match:
        intv_cand = intv_match.group(1).strip()
        analysis.intervention = intv_cand
        # Check if intervention contains drug
        if analysis.domain == "medical":
            analysis.drug = intv_cand.split()[0] if intv_cand else ""

    outcome_match = re.search(r'\b(?:reduce|prevent|improve|increase|treat|lower|cause)\s+([^?,;]+?)(?:\s+(?:compared|in\s+patients|in\s+adults|among)\b|\?|$)', q, re.I)
    if outcome_match:
        analysis.outcome = outcome_match.group(1).strip()
    elif "detection" in q_lower or "accuracy" in q_lower or "retrieval" in q_lower:
        tech_outcome = re.search(r'\b(?:for|in)\s+([^?,;]+?)(?:\s+using|\?|$)', q, re.I)
        if tech_outcome:
            analysis.outcome = tech_outcome.group(1).strip()

    logger.info(f"Fallback PICO analysis: intervention='{analysis.intervention}', "
                f"outcome='{analysis.outcome}', population='{analysis.population}'")


def _guess_domain(question: str) -> str:
    """Fallback domain classification using keyword matching."""
    q = question.lower()
    medical_terms = [
        "disease", "drug", "treatment", "patient", "clinical", "diagnosis",
        "therapy", "dose", "medication", "symptom", "cancer", "diabetes",
        "cardiovascular", "hospital", "surgery", "randomized", "placebo",
        "adverse", "efficacy", "safety", "trial", "mg", "injection",
        "oral", "intravenous", "prognosis", "mortality", "morbidity",
        "biomarker", "pathology", "epidemiology", "prevalence", "incidence",
        "metformin", "statin", "aspirin", "insulin", "antibiotic",
    ]
    scientific_terms = [
        "algorithm", "neural network", "machine learning", "deep learning",
        "computing", "software", "engineering", "physics", "mathematics",
        "robotics", "optimization", "simulation", "information retrieval",
        "transformer", "natural language processing", "artificial intelligence",
    ]

    med_count = sum(1 for t in medical_terms if t in q)
    sci_count = sum(1 for t in scientific_terms if t in q)

    if med_count > 0 and sci_count > 0:
        return "mixed"
    elif med_count > sci_count:
        return "medical"
    else:
        return "scientific"


def _extract_basic_concepts(question: str) -> list:
    """Fallback concept extraction using simple word filtering."""
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "dare", "ought",
        "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "as", "into", "through", "during", "before", "after", "above",
        "below", "between", "out", "off", "over", "under", "again",
        "further", "then", "once", "here", "there", "when", "where", "why",
        "how", "all", "each", "every", "both", "few", "more", "most",
        "other", "some", "such", "no", "nor", "not", "only", "own", "same",
        "so", "than", "too", "very", "just", "because", "but", "and", "or",
        "if", "while", "what", "which", "who", "whom", "this", "that",
        "these", "those", "am", "it", "its", "i", "me", "my", "myself",
        "we", "our", "ours", "you", "your", "he", "him", "she", "her",
        "they", "them", "their", "about", "up", "down", "compared",
    }
    import re
    words = re.findall(r'\b[a-zA-Z0-9-]{3,}\b', question.lower())
    return [w for w in words if w not in stop_words][:8]
