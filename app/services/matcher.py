"""
matcher.py — AI Resume Matching Service

Uses TF-IDF vectorisation + cosine similarity (scikit-learn) to compute
a semantic relevance score between a resume and a job description.

Skill gap analysis is handled separately via set comparison so that the
score and skill lists are independently interpretable.
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger("uvicorn.error")

# Thread pool for offloading CPU-bound sklearn work from the async event loop
_executor = ThreadPoolExecutor(max_workers=4)


# ──────────────────────────────────────────────────────────────────────────────
# Text Pre-processing
# ──────────────────────────────────────────────────────────────────────────────

def _preprocess(text: str) -> str:
    """
    Lowercase and strip non-alphanumeric characters for cleaner TF-IDF input.
    Preserves spaces so multi-word phrases stay intact.
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ──────────────────────────────────────────────────────────────────────────────
# Core Similarity Computation (synchronous — runs in thread pool)
# ──────────────────────────────────────────────────────────────────────────────

def _compute_similarity(resume_text: str, job_text: str) -> float:
    """
    Compute TF-IDF cosine similarity between resume and job description texts.
    Returns a float in [0.0, 1.0].
    """
    corpus = [_preprocess(resume_text), _preprocess(job_text)]

    # Use sublinear TF scaling and strip English stop-words for better signal
    vectorizer = TfidfVectorizer(
        sublinear_tf=True,
        stop_words="english",
        ngram_range=(1, 2),   # unigrams + bigrams to capture compound tech terms
        min_df=1,
    )

    try:
        tfidf_matrix = vectorizer.fit_transform(corpus)
        score = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        return float(score)
    except Exception as e:
        logger.error(f"TF-IDF computation failed: {e}")
        return 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Skill Gap Analysis (synchronous — cheap, no thread pool needed)
# ──────────────────────────────────────────────────────────────────────────────

def _analyse_skills(
    resume_text: str,
    required_skills: list[str],
    extracted_skills: list[str],
) -> tuple[list[str], list[str]]:
    """
    Compute matched and missing skills by comparing:
      - extracted_skills (from NLP on resume text)
      - required_skills  (from job description)

    Falls back to a case-insensitive substring search in resume_text for
    skills that the NLP might have missed (e.g. abbreviations).

    Returns:
        matched_skills: skills found in the resume
        missing_skills: skills required but absent from the resume
    """
    resume_lower = resume_text.lower()
    matched: list[str] = []
    missing: list[str] = []

    # Normalization mapping (must mirror NLP mapping)
    NORMALIZATION = {
        "yolov8": "yolo",
        "yolov5": "yolo",
        "easyocr": "ocr",
        "tesseract": "ocr",
        "react": "react.js",
        "node": "node.js",
        "mongo": "mongodb",
        "mongodb": "mongodb",
        "tensorflow": "tensorflow",
        "scikit learn": "scikit-learn",
        "sklearn": "scikit-learn",
    }

    def normalize(s: str) -> str:
        sl = s.lower()
        return NORMALIZATION.get(sl, sl)

    extracted_norm = {normalize(s) for s in extracted_skills}

    logger.debug(f"Normalized extracted skills: {sorted(list(extracted_norm))}")

    for skill in required_skills:
        skill_norm = normalize(skill)
        # Match if NLP found it OR it appears literally anywhere in the resume (case-insensitive)
        if skill_norm in extracted_norm or re.search(r"\b" + re.escape(skill_norm) + r"\b", resume_lower):
            matched.append(skill)
        else:
            missing.append(skill)

    return matched, missing


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

import asyncio


async def match_resume_to_job(
    resume_text: str,
    job_text: str,
    required_skills: list[str],
    extracted_skills: list[str],
) -> dict:
    """
    Async entry-point for the matching pipeline.

    Args:
        resume_text:      Full extracted text of the candidate's resume.
        job_text:         Full job title + description concatenated.
        required_skills:  List of required skills from the job model.
        extracted_skills: List of skills already extracted from the resume via NLP.

    Returns:
        {
            "score": int (0–100),
            "matchedSkills": list[str],
            "missingSkills": list[str],
        }
    """
    if not resume_text.strip() or not job_text.strip():
        return {"score": 0, "matchedSkills": [], "missingSkills": list(required_skills)}

    # Log full resume and skill pipeline context
    logger.info("=== Resume Analysis ===")
    logger.info(f"Extracted text: {resume_text[:240]!r}")
    logger.info(f"Extracted skills: {extracted_skills}")
    normalized_extracted = {s.lower() for s in extracted_skills}
    logger.info(f"Normalized skills: {sorted(list(normalized_extracted))}")
    logger.info(f"Job skills: {required_skills}")

    # Use skill coverage only as the scoring formula per requirements
    matched_skills, missing_skills = _analyse_skills(
        resume_text, required_skills, extracted_skills
    )

    score = 0
    if required_skills:
        try:
            score = round((len(matched_skills) / len(required_skills)) * 100)
        except Exception:
            score = 0

    # Detailed logging for debugging
    try:
        logger.info(f"Matched Skills: {matched_skills}")
        logger.info(f"Missing Skills: {missing_skills}")
        logger.info(f"Score: {score}%")
    except Exception:
        pass

    return {
        "score":         score,
        "matchedSkills": matched_skills,
        "missingSkills": missing_skills,
    }
