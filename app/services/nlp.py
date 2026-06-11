import logging
import spacy
from spacy.matcher import PhraseMatcher

logger = logging.getLogger("uvicorn.error")

# Load the spaCy model once at module level for performance.
# Falls back to a blank English model if 'en_core_web_sm' is not installed.
try:
    nlp = spacy.load("en_core_web_sm")
    logger.info("Loaded spaCy model: en_core_web_sm")
except OSError:
    logger.warning(
        "spaCy model 'en_core_web_sm' not found. "
        "Falling back to blank English model. "
        "Run: python -m spacy download en_core_web_sm"
    )
    nlp = spacy.blank("en")


def extract_skills_from_text(text: str, skills_list: list[str]) -> list[str]:
    """
    Uses spaCy PhraseMatcher to identify known skills inside resume text.

    Args:
        text: Raw extracted resume text.
        skills_list: List of skill keyword strings from the database.

    Returns:
        A deduplicated list of matched skill strings, preserving original casing.
    """
    if not text or not skills_list:
        if not skills_list:
            logger.warning("Skill list is empty in extract_skills_from_text; using fallback default skill set.")
            skills_list = [
                "Python", "JavaScript", "React.js", "React", "Node.js", "MongoDB", "SQL",
                "Machine Learning", "Deep Learning", "TensorFlow", "OpenCV", "YOLO",
                "OCR", "Data Science", "Scikit-learn", "Git", "GitHub", "FastAPI"
            ]
        else:
            return []

    text_lower = text.lower()

    # Normalization mapping for synonyms -> canonical (lowercase)
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

    # Build canonical map: lowercase canonical -> original casing from skills_list
    canonical_map = {}
    for skill in skills_list:
        canonical_map[skill.lower()] = skill

    found: set[str] = set()

    # 1) Keyword substring matching (word-boundary aware)
    import re

    direct_matches = set()
    synonym_matches = set()
    for skill in skills_list:
        sk_low = skill.lower()
        # direct match word-boundary
        pattern = r"\b" + re.escape(sk_low) + r"\b"
        if re.search(pattern, text_lower):
            found.add(canonical_map.get(sk_low, skill))
            direct_matches.add(canonical_map.get(sk_low, skill))
            continue

        # fallback: substring match (covers cases like 'yolov8' containing 'yolo')
        if sk_low in text_lower:
            found.add(canonical_map.get(sk_low, skill))
            direct_matches.add(canonical_map.get(sk_low, skill))
            continue

        # synonyms and normalization matches
        for syn, canon in NORMALIZATION.items():
            if canon == sk_low and re.search(r"\b" + re.escape(syn) + r"\b", text_lower):
                found.add(canonical_map.get(sk_low, skill))
                synonym_matches.add(canonical_map.get(sk_low, skill))
                break

    # 2) spaCy PhraseMatcher fallback (helps with multi-word phrases)
    try:
        matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
        patterns = [nlp.make_doc(s.lower()) for s in skills_list]
        matcher.add("SKILLS", patterns)
        doc = nlp(text)
        matches = matcher(doc)
        for _, start, end in matches:
            matched_text = doc[start:end].text.lower()
            # map matched_text to canonical if present
            canon = NORMALIZATION.get(matched_text, matched_text)
            if canon in canonical_map:
                found.add(canonical_map[canon])
            elif matched_text in canonical_map:
                found.add(canonical_map[matched_text])
    except Exception as exc:
        # On any failure, ignore PhraseMatcher stage but log details
        logger.debug(f"spaCy PhraseMatcher failed during skill extraction: {exc}")

    # Additional pass: find synonyms that map to a canonical that exists in skills list
    implied_matches = set()
    for syn, canon in NORMALIZATION.items():
        if canon in canonical_map and re.search(r"\b" + re.escape(syn) + r"\b", text_lower):
            found.add(canonical_map[canon])
            synonym_matches.add(canonical_map[canon])

    # Implied skills inferred from existing matches
    IMPLIED_SKILL_MAP = {
        "tensorflow": ["deep learning"],
        "opencv": ["computer vision"],
        "yolo": ["computer vision"],
        "easyocr": ["ocr"],
        "tesseract": ["ocr"],
        "machine learning": ["data science"],
        "scikit-learn": ["data science"],
    }
    inferred = set()
    for matched in list(found):
        match_low = matched.lower()
        for key, implied in IMPLIED_SKILL_MAP.items():
            if match_low == key or re.search(r"\b" + re.escape(key) + r"\b", match_low):
                for implied_skill in implied:
                    if implied_skill in canonical_map:
                        inferred.add(canonical_map[implied_skill])
    found.update(inferred)

    logger.info("=== Skill Extraction ===")
    logger.info(f"Extracted text: {text[:240]!r}")
    logger.info(f"Skill database contents: {skills_list}")
    logger.info(f"Direct skill matches: {sorted(list(direct_matches))}")
    logger.info(f"Synonym skill matches: {sorted(list(synonym_matches))}")
    logger.info(f"Inferred skills: {sorted(list(inferred))}")
    logger.info(f"Final extracted skills: {sorted(list(found))}")

    return sorted(found)


# ---------------------------------------------------------------------------
# Candidate Information Extraction
# ---------------------------------------------------------------------------

import re

# Email: standard RFC-style pattern
_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE
)

# Phone: covers international (+91), US, and common formatted numbers
_PHONE_RE = re.compile(
    r"""
    (?:(?:\+|00)\d{1,3}[\s\-.])?   # optional country code
    (?:\(?\d{2,4}\)?[\s\-.])?       # optional area code
    \d{3,5}[\s\-.]                  # first block
    \d{3,5}                         # second block
    (?:[\s\-.]\d{1,5})?             # optional third block
    """,
    re.VERBOSE
)


def _extract_email(text: str) -> str:
    """Return the first email address found in the text, or empty string."""
    match = _EMAIL_RE.search(text)
    return match.group(0).strip() if match else ""


def _extract_phone(text: str) -> str:
    """
    Return the best phone number found in the text.
    Filters out short matches that are likely not phone numbers (< 7 digits).
    """
    candidates = _PHONE_RE.findall(text)
    for candidate in candidates:
        digits = re.sub(r"\D", "", candidate)
        if len(digits) >= 7:
            return candidate.strip()
    return ""


def _extract_name(text: str) -> str:
    """
    Attempt to extract the candidate's full name using two strategies:
    1. spaCy NER — look for the first PERSON entity in the top 20 lines.
    2. Heuristic fallback — the first short, mostly-alphabetic line.
    """
    # Only analyze the top portion of the document for performance and accuracy
    top_text = "\n".join(text.splitlines()[:30])
    doc = nlp(top_text)

    # Strategy 1: NER PERSON entities (works well with en_core_web_sm)
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            name = ent.text.strip()
            # Sanity check: a real name is 2–5 words and mostly alphabetic
            words = name.split()
            if 2 <= len(words) <= 5 and all(w.replace("-", "").isalpha() for w in words):
                return name

    # Strategy 2: Heuristic — scan early lines for a plausible name line
    for line in text.splitlines()[:15]:
        line = line.strip()
        if not line:
            continue
        # Skip lines that look like section headers, emails, phone numbers, or URLs
        if any(ch in line for ch in ["@", "http", "/", "|", ":"]):
            continue
        if _PHONE_RE.search(line):
            continue
        words = line.split()
        if 2 <= len(words) <= 5 and all(w.replace("-", "").replace(".", "").isalpha() for w in words):
            # Title-case check — names are usually capitalised
            if sum(1 for w in words if w[0].isupper()) >= len(words) - 1:
                return line

    return ""


def extract_candidate_info(text: str, skills_list: list[str]) -> dict:
    """
    Extract all key candidate information from raw resume text.

    Args:
        text:         Raw extracted resume text.
        skills_list:  List of skill keyword strings from the database.

    Returns:
        A dict with keys: name, email, phone, skills.
    """
    return {
        "name":   _extract_name(text),
        "email":  _extract_email(text),
        "phone":  _extract_phone(text),
        "skills": extract_skills_from_text(text, skills_list),
    }
