import logging
from fastapi import APIRouter, HTTPException, status, Query

from app.repositories.candidate import CandidateRepository
from app.repositories.resume import ResumeRepository
from app.repositories.skills import SkillsRepository
from app.services.nlp import extract_candidate_info
from app.services.job import JobService
from app.services.matcher import match_resume_to_job

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/candidates", tags=["candidates"])
repo = CandidateRepository()
resume_repo = ResumeRepository()
skills_repo = SkillsRepository()
job_service = JobService()


async def _analyze_and_persist_resume(resume_doc: dict, job_id: str | None = None) -> dict:
    """Ensure a candidate document exists for the resume and (optionally) compute match for job_id.

    Returns the persisted candidate document.
    """
    # Extract skills and contact info
    skills_list = await skills_repo.get_all_skills()
    info = extract_candidate_info(resume_doc.get("extractedText", ""), skills_list)

    candidate_data = {
        "candidateName": info.get("name") or resume_doc.get("candidateName") or resume_doc.get("filename"),
        "email": info.get("email") or resume_doc.get("email", ""),
        "phone": info.get("phone") or resume_doc.get("phone", ""),
        "skills": info.get("skills", []),
        "resumeFile": resume_doc.get("filename"),
        "resumeId": resume_doc.get("id"),
    }

    # If job specified, compute matching score & lists
    if job_id:
        job_obj = await job_service.get_job_by_id(job_id)
        if job_obj:
            job_text = f"{job_obj.get('title','')} {job_obj.get('description','')}"
            required_skills = job_obj.get('requiredSkills', [])
            match_result = await match_resume_to_job(
                resume_text=resume_doc.get('extractedText', ''),
                job_text=job_text,
                required_skills=required_skills,
                extracted_skills=candidate_data['skills'],
            )

            candidate_data.update({
                "score": match_result.get('score', 0),
                "matchedSkills": match_result.get('matchedSkills', []),
                "missingSkills": match_result.get('missingSkills', []),
                "lastMatch": {
                    "jobId": job_id,
                    "score": match_result.get('score', 0),
                    "matchedSkills": match_result.get('matchedSkills', []),
                    "missingSkills": match_result.get('missingSkills', []),
                }
            })

    # Upsert by email when available, else create new doc
    try:
        if candidate_data['email']:
            saved = await repo.update_by_email(candidate_data['email'], candidate_data)
        else:
            saved = await repo.create(candidate_data)
        return saved
    except Exception as e:
        logger.error(f"Failed to persist candidate for resume {resume_doc.get('id')}: {e}")
        raise


@router.get("", status_code=status.HTTP_200_OK)
async def list_candidates(job_id: str | None = Query(None)):
    """Return all candidates. If `job_id` provided, ensure analysis against that job has been run for all resumes.

    If a candidate lacks skills, skills will be extracted and saved. If `job_id` is present,
    matching will be computed and persisted before returning results.
    """
    try:
        # Load all uploaded resumes and ensure candidate documents exist/analyzed
        resumes = await resume_repo.get_all()
        for r in resumes:
            # Persist analysis (will upsert by email or create)
            await _analyze_and_persist_resume(r, job_id=job_id)

        # Only return candidates that are linked to existing resumes.
        # Gather resume ids present in the DB (string ids produced by ResumeRepository.get_all)
        resume_ids = {r.get('id') for r in resumes}

        all_candidates = await repo.get_all()
        # Filter out orphaned candidates (those whose resumeId no longer exists)
        filtered = [c for c in all_candidates if c.get('resumeId') in resume_ids]
        return filtered
    except Exception as e:
        logger.error(f"Failed to list candidates: {e}")
        raise HTTPException(status_code=500, detail="Could not retrieve candidates")


@router.get("/ranked", status_code=status.HTTP_200_OK)
async def get_ranked(job_id: str | None = Query(None)):
    """Return candidates ranked by score. If `job_id` provided, compute matches against that job for all resumes first."""
    try:
        resumes = await resume_repo.get_all()
        for r in resumes:
            await _analyze_and_persist_resume(r, job_id=job_id)

        # Fetch ranked candidates from repository
        ranked = await repo.get_ranked(job_id)

        # Only include candidates with an existing resume document
        resume_ids = {r.get('id') for r in resumes}
        ranked = [c for c in ranked if c.get('resumeId') in resume_ids]

        # Update rank field in DB and include rank in response
        for idx, cand in enumerate(ranked):
            rank_val = idx + 1
            # update by email if present, else by resumeId
            filt = {}
            if cand.get('email'):
                filt = {'email': cand['email']}
            elif cand.get('resumeId'):
                filt = {'resumeId': cand['resumeId']}
            if filt:
                try:
                    await repo.collection.update_one(filt, {'$set': {'rank': rank_val}})
                except Exception:
                    pass
            cand['rank'] = rank_val

        return ranked
    except Exception as e:
        logger.error(f"Failed to retrieve ranked candidates: {e}")
        raise HTTPException(status_code=500, detail="Could not retrieve ranked candidates")



@router.get("/debug/{id}", status_code=status.HTTP_200_OK)
async def debug_candidate(id: str, job_id: str | None = Query(None)):
    """Return detailed analysis for a candidate. If `job_id` provided, run matching against that job."""
    try:
        cand = await repo.get_by_id(id)
        if not cand:
            raise HTTPException(status_code=404, detail="Candidate not found")

        # If candidate lacks extracted skills, try to augment from resume
        if not cand.get('skills') or not cand.get('skills'):
            # try find resume document
            resume = None
            if cand.get('resumeId'):
                from app.repositories.resume import ResumeRepository
                rr = ResumeRepository()
                resume = await rr.get_by_id(cand.get('resumeId'))
            if resume:
                skills_list = await skills_repo.get_all_skills()
                from app.services.nlp import extract_skills_from_text
                extracted = extract_skills_from_text(resume.get('extractedText',''), skills_list)
                cand['extractedSkills'] = extracted
        else:
            cand['extractedSkills'] = cand.get('skills', [])

        job_skills = []
        matched = []
        missing = []
        score = cand.get('score', 0)

        if job_id:
            job_obj = await job_service.get_job_by_id(job_id)
            if not job_obj:
                raise HTTPException(status_code=404, detail='Job not found')

            job_skills = job_obj.get('requiredSkills', [])
            resume_text = cand.get('extractedText', '')
            if not resume_text and cand.get('resumeId'):
                from app.repositories.resume import ResumeRepository
                resume_doc = await ResumeRepository().get_by_id(cand.get('resumeId'))
                resume_text = resume_doc.get('extractedText', '') if resume_doc else ''

            if not resume_text and cand.get('extractedSkills'):
                resume_text = ' '.join(cand.get('extractedSkills', []))

            match_result = await match_resume_to_job(
                resume_text=resume_text,
                job_text=f"{job_obj.get('title','')} {job_obj.get('description','')}",
                required_skills=job_skills,
                extracted_skills=cand.get('extractedSkills', [])
            )
            matched = match_result.get('matchedSkills', [])
            missing = match_result.get('missingSkills', [])
            score = match_result.get('score', 0)

        return {
            'extractedSkills': cand.get('extractedSkills', []),
            'jobSkills': job_skills,
            'matchedSkills': matched,
            'missingSkills': missing,
            'score': score
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Debug candidate failed: {e}")
        raise HTTPException(status_code=500, detail="Debug analysis failed")


@router.post('/debug/reanalyze', status_code=status.HTTP_200_OK)
async def reanalyze_all():
    """Re-run skill extraction and matching for all stored resumes and jobs.

    This updates candidate documents with `extractedSkills`, `matchedSkills`, `missingSkills`, and `score` (best across jobs).
    """
    try:
        resumes = await resume_repo.get_all()
        jobs = await job_service.get_all_jobs()
        skills_list = await skills_repo.get_all_skills()

        updated = 0
        for r in resumes:
            # extract skills
            from app.services.nlp import extract_skills_from_text
            extracted = extract_skills_from_text(r.get('extractedText',''), skills_list)

            best_score = 0
            best_match = None
            # compute match against each job and pick best
            for job in jobs:
                match_result = await match_resume_to_job(
                    resume_text = r.get('extractedText',''),
                    job_text = f"{job.get('title','')} {job.get('description','')}",
                    required_skills = job.get('requiredSkills', []),
                    extracted_skills = extracted
                )
                if match_result.get('score', 0) > best_score:
                    best_score = match_result.get('score', 0)
                    best_match = {
                        'jobId': job.get('id') if job.get('id') else job.get('_id'),
                        'score': match_result.get('score', 0),
                        'matchedSkills': match_result.get('matchedSkills', []),
                        'missingSkills': match_result.get('missingSkills', [])
                    }

            candidate_data = {
                'candidateName': r.get('candidateName') or r.get('filename'),
                'email': r.get('email',''),
                'phone': r.get('phone',''),
                'skills': extracted,
                'extractedSkills': extracted,
                'score': best_score,
                'matchedSkills': best_match.get('matchedSkills', []) if best_match else [],
                'missingSkills': best_match.get('missingSkills', []) if best_match else [],
                'lastMatch': best_match
            }

            if candidate_data['email']:
                await repo.update_by_email(candidate_data['email'], candidate_data)
            else:
                await repo.create(candidate_data)
            updated += 1

        return { 'status': 'ok', 'updated': updated }
    except Exception as e:
        logger.error(f"Reanalyze failed: {e}")
        raise HTTPException(status_code=500, detail='Reanalyze failed')


@router.get("/{id}", status_code=status.HTTP_200_OK)
async def get_candidate(id: str):
    try:
        c = await repo.get_by_id(id)
        if not c:
            raise HTTPException(status_code=404, detail="Candidate not found")
        return c
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve candidate {id}: {e}")
        raise HTTPException(status_code=500, detail="Could not retrieve candidate")
