from typing import List
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from app.services.job import JobService

router = APIRouter(prefix="/job", tags=["job"])
job_service = JobService()


class JobCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    requiredSkills: List[str] = Field(default_factory=list)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_job(payload: JobCreateRequest):
    """
    Create and persist a new job description.
    """
    job = await job_service.create_job(
        title=payload.title,
        description=payload.description,
        required_skills=payload.requiredSkills,
    )
    return job


@router.get("", response_model=list)
async def list_jobs():
    """
    Retrieve all job descriptions, newest first.
    """
    return await job_service.get_all_jobs()


@router.get("/{id}")
async def get_job(id: str):
    """
    Retrieve a single job description by MongoDB ID.
    """
    job = await job_service.get_job_by_id(id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    return job
