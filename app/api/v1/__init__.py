# api v1 router
from fastapi import APIRouter
from app.api.v1.resumes import router as resumes_router
from app.api.v1.jobs    import router as jobs_router
from app.api.v1.match   import router as match_router
from app.api.v1.candidates import router as candidates_router

router = APIRouter()
router.include_router(resumes_router)
router.include_router(jobs_router)
router.include_router(match_router)
router.include_router(candidates_router)
