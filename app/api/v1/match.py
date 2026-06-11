"""
match.py — POST /api/v1/match

Compares a stored resume against a stored job description using
TF-IDF cosine similarity and NLP skill extraction.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.repositories.resume import ResumeRepository
from app.repositories.skills import SkillsRepository
from app.services.job import JobService
from app.services.nlp import extract_skills_from_text
from app.services.matcher import match_resume_to_job
from app.repositories.candidate import CandidateRepository
from datetime import datetime

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/match", tags=["match"])

resume_repo  = ResumeRepository()
skills_repo  = SkillsRepository()
job_service  = JobService()
candidate_repo = CandidateRepository()


class MatchRequest(BaseModel):
    resume_id: str
    job_id:    str


@router.post("", status_code=status.HTTP_200_OK)
async def match_resume(payload: MatchRequest):
    """
    Compare a resume against a job description.

    Loads the resume and job from MongoDB, runs TF-IDF cosine similarity,
    and returns a blended match score alongside matched and missing skills.

    Response:
        {
            "score":         int   (0–100),
            "matchedSkills": list[str],
            "missingSkills": list[str],
        }
    """
    # ── 1. Fetch Resume ────────────────────────────────────────────────────────
    resume = await resume_repo.get_by_id(payload.resume_id)
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resume not found: {payload.resume_id}"
        )

    resume_text: str = resume.get("extractedText", "").strip()
    if not resume_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Resume has no extracted text. Please run /resume/extract first."
        )

    # ── 2. Fetch Job Description ───────────────────────────────────────────────
    job = await job_service.get_job_by_id(payload.job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {payload.job_id}"
        )

    # Combine title + description for richer TF-IDF comparison
    job_text: str = f"{job.get('title', '')} {job.get('description', '')}".strip()
    required_skills: list[str] = job.get("requiredSkills", [])

    # ── 3. Extract NLP Skills from Resume ─────────────────────────────────────
    try:
        skills_list = await skills_repo.get_all_skills()
        logger.info(f"Loaded skill database size: {len(skills_list)}")
        logger.info(f"Skill database entries: {skills_list}")
        extracted_skills = extract_skills_from_text(resume_text, skills_list)
    except Exception as e:
        logger.error(f"Skill extraction during matching failed: {e}")
        extracted_skills = []

    # ── 4. Run Matching Pipeline ───────────────────────────────────────────────
    try:
        result = await match_resume_to_job(
            resume_text=resume_text,
            job_text=job_text,
            required_skills=required_skills,
            extracted_skills=extracted_skills,
        )
    except Exception as e:
        logger.error(f"Matching pipeline failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Resume matching failed. Please try again."
        )

    # Persist candidate ranking/result in DB (upsert by email when possible)
    try:
        candidate_data = {
            "candidateName": resume.get("candidateName") or resume.get("filename"),
            "email": resume.get("email", ""),
            "phone": resume.get("phone", ""),
            "skills": extracted_skills,
            "extractedSkills": extracted_skills,
            "score": result.get("score", 0),
            "matchedSkills": result.get("matchedSkills", []),
            "missingSkills": result.get("missingSkills", []),
            "resumeFile": resume.get("filename"),
            "resumeId": resume.get("id"),
            "lastMatch": {
                "jobId": payload.job_id,
                "score": result.get("score", 0),
                "matchedSkills": result.get("matchedSkills", []),
                "missingSkills": result.get("missingSkills", []),
                "timestamp": datetime.utcnow()
            }
        }

        # Prefer updating by email when available to avoid duplicates
        if candidate_data["email"]:
            saved = await candidate_repo.update_by_email(candidate_data["email"], candidate_data)
        else:
            saved = await candidate_repo.create(candidate_data)
    except Exception as e:
        logger.error(f"Failed to persist candidate result: {e}")

    return {
        "score":         result["score"],
        "matchedSkills": result["matchedSkills"],
        "missingSkills": result["missingSkills"],
    }
