import logging
import shutil
import uuid
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from pydantic import BaseModel
from app.services.resume import ResumeService
from app.repositories.skills import SkillsRepository
from app.services.nlp import extract_skills_from_text, extract_candidate_info
from app.services.matcher import match_resume_to_job
from app.repositories.candidate import CandidateRepository
from datetime import datetime

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/resume", tags=["resume"])
resume_service = ResumeService()
skills_repo = SkillsRepository()
candidate_repo = CandidateRepository()


class SkillExtractionRequest(BaseModel):
    resume_id: Optional[str] = None
    text: Optional[str] = None

# Base uploads folder relative to the backend root directory
UPLOAD_DIR = Path("uploads")
# Ensure the uploads directory exists
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Allowed files configuration
ALLOWED_EXTENSIONS = {".pdf", ".docx"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
}

@router.post("/extract", status_code=status.HTTP_201_CREATED)
async def extract_resume(file: UploadFile = File(...)):
    """
    Upload a resume file, extract text (using pdfplumber/python-docx),
    automatically save metadata/text to MongoDB, and return the response.
    """
    # 1. Validate file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type '{file_ext}'. Only PDF and DOCX files are allowed."
        )
    
    # 2. Validate MIME type
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid MIME type '{file.content_type}'. Only PDF and DOCX files are allowed."
        )

    # 3. Generate unique filename to avoid naming conflicts
    unique_filename = f"{uuid.uuid4().hex}{file_ext}"
    file_path = UPLOAD_DIR / unique_filename

    # 4. Save the file to local filesystem
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Error saving uploaded file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save file on the server."
        )

    # 5. Process, extract text (async), run heuristics and save to database
    try:
        resume_doc = await resume_service.extract_and_save_resume(
            file_path=str(file_path),
            filename=unique_filename,
            content_type=file.content_type
        )
        return {
            "id": resume_doc.get("id"),
            "filename": resume_doc.get("filename"),
            "extractedText": resume_doc.get("extractedText"),
            "candidateName": resume_doc.get("candidateName"),
            "email": resume_doc.get("email"),
            "phone": resume_doc.get("phone"),
            "uploadDate": resume_doc.get("uploadDate")
        }
    except ValueError as ve:
        # Clean up uploaded file if parsing fails
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve)
        )
    except Exception as e:
        # Clean up uploaded file if general failure occurs
        if file_path.exists():
            file_path.unlink()
        logger.error(f"Extraction processing failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to extract text from the file."
        )

@router.post("/extract-skills", status_code=status.HTTP_200_OK)
async def extract_skills(payload: SkillExtractionRequest):
    """
    Extract skills from resume text using spaCy NLP.
    Accepts either a resume_id (to load stored extracted text from MongoDB)
    or raw text directly.
    """
    text_to_analyze = payload.text

    # If a resume_id is provided, load the extracted text from MongoDB
    if payload.resume_id:
        resume = await resume_service.get_resume_by_id(payload.resume_id)
        if not resume:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resume not found for the given resume_id."
            )
        text_to_analyze = resume.get("extractedText", "")

    if not text_to_analyze:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No text provided. Supply either 'resume_id' or 'text' in the request body."
        )

    # Fetch the current skills list from MongoDB
    try:
        skills_list = await skills_repo.get_all_skills()
    except Exception as e:
        logger.error(f"Failed to retrieve skills from database: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load skills database."
        )

    # Run spaCy NLP extraction
    try:
        matched_skills = extract_skills_from_text(text_to_analyze, skills_list)
    except Exception as e:
        logger.error(f"spaCy skill extraction failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Skill extraction processing failed."
        )

    return {"skills": matched_skills}


@router.post("/candidate-info", status_code=status.HTTP_200_OK)
async def get_candidate_info(payload: SkillExtractionRequest):
    """
    Extract full candidate information (name, email, phone, skills) from
    resume text using NLP + regex techniques.
    Accepts either a resume_id (loads stored extracted text) or raw text.
    """
    text_to_analyze = payload.text

    # Resolve text from stored resume if resume_id provided
    if payload.resume_id:
        resume = await resume_service.get_resume_by_id(payload.resume_id)
        if not resume:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resume not found for the given resume_id."
            )
        text_to_analyze = resume.get("extractedText", "")

    if not text_to_analyze:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No text provided. Supply either 'resume_id' or 'text' in the request body."
        )

    # Fetch skills list from MongoDB
    try:
        skills_list = await skills_repo.get_all_skills()
    except Exception as e:
        logger.error(f"Failed to retrieve skills from database: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load skills database."
        )

    # Run combined NLP + regex extraction
    try:
        info = extract_candidate_info(text_to_analyze, skills_list)
    except Exception as e:
        logger.error(f"Candidate info extraction failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Candidate information extraction failed."
        )

    return {
        "name":   info["name"],
        "email":  info["email"],
        "phone":  info["phone"],
        "skills": info["skills"],
    }



@router.post("/analyze", status_code=status.HTTP_200_OK)
async def analyze_resume(file: Optional[UploadFile] = File(None), resume_id: Optional[str] = None, job_id: Optional[str] = None):
    """
    Analyze a resume: accepts either an uploaded file (PDF/DOCX) or an existing resume_id.
    Optionally provide `job_id` to compute a matching score and persist candidate ranking.
    """
    # Ensure we have either a file or resume_id
    if file is None and not resume_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide a file or a resume_id")

    # If file provided, reuse extract flow
    resume_doc = None
    if file is not None:
        # reuse extract endpoint behavior (validate extension/mime)
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS or file.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file upload")
        unique_filename = f"{uuid.uuid4().hex}{file_ext}"
        file_path = UPLOAD_DIR / unique_filename
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            resume_doc = await resume_service.extract_and_save_resume(str(file_path), unique_filename, file.content_type)
        except Exception as e:
            if file_path.exists():
                file_path.unlink()
            raise HTTPException(status_code=500, detail=str(e))
    else:
        resume_doc = await resume_service.get_resume_by_id(resume_id)
        if not resume_doc:
            raise HTTPException(status_code=404, detail="Resume not found")

    # Extract candidate info
    try:
        skills_list = await skills_repo.get_all_skills()
        info = extract_candidate_info(resume_doc.get("extractedText", ""), skills_list)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to extract candidate info")

    response = {
        "candidateName": info.get("name") or resume_doc.get("candidateName"),
        "email": info.get("email") or resume_doc.get("email"),
        "phone": info.get("phone") or resume_doc.get("phone"),
        "skills": info.get("skills", []),
        "resumeId": resume_doc.get("id")
    }

    # If job_id supplied, run matching and persist candidate result
    if job_id:
        # Use match service directly
        try:
            # Compose job text and required_skills by loading via JobService
            from app.services.job import JobService
            job_service = JobService()
            job_obj = await job_service.get_job_by_id(job_id)
            job_text = f"{job_obj.get('title','')} {job_obj.get('description','')}"
            required_skills = job_obj.get('requiredSkills', [])
            match_result = await match_resume_to_job(
                resume_text=resume_doc.get('extractedText',''),
                job_text=job_text,
                required_skills=required_skills,
                extracted_skills=response['skills']
            )

            # Persist candidate
            cand = {
                "candidateName": response["candidateName"],
                "email": response["email"],
                "phone": response["phone"],
                "skills": response["skills"],
                "extractedSkills": response["skills"],
                "score": match_result.get('score', 0),
                "matchedSkills": match_result.get('matchedSkills', []),
                "missingSkills": match_result.get('missingSkills', []),
                "resumeFile": resume_doc.get('filename'),
                "resumeId": resume_doc.get('id'),
                "lastMatch": {
                    "jobId": job_id,
                    "score": match_result.get('score', 0),
                    "matchedSkills": match_result.get('matchedSkills', []),
                    "missingSkills": match_result.get('missingSkills', []),
                    "timestamp": datetime.utcnow()
                }
            }

            if cand["email"]:
                await candidate_repo.update_by_email(cand["email"], cand)
            else:
                await candidate_repo.create(cand)

            response.update({
                "match": match_result
            })
        except Exception as e:
            logger.error(f"Failed to run matching during analyze: {e}")

    return response


@router.get("", response_model=list)
async def list_resumes():
    """
    Retrieve all processed resumes and their extraction details.
    """
    return await resume_service.get_all_resumes()

@router.get("/{id}")
async def get_resume(id: str):
    """
    Retrieve a specific resume by its MongoDB ID.
    """
    resume = await resume_service.get_resume_by_id(id)
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found"
        )
    return resume

@router.delete("/{id}")
async def delete_resume(id: str):
    """
    Delete a resume from MongoDB and remove the physical file from the local server disk.
    """
    success = await resume_service.delete_resume(id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found or could not be deleted"
        )
    return {
        "status": "success",
        "message": "Resume and associated file deleted successfully"
    }
