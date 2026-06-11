from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import connect_to_mongo, close_mongo_connection, get_database
from app.api.v1 import router as api_v1_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Connect to MongoDB
    try:
        await connect_to_mongo()
        
        # Seed default skills
        from app.repositories.skills import SkillsRepository
        DEFAULT_SKILLS = [
            "Python", "JavaScript", "React.js", "React", "Node.js", "MongoDB", "SQL",
            "Machine Learning", "Deep Learning", "TensorFlow", "OpenCV", "YOLO",
            "OCR", "Data Science", "Scikit-learn", "FastAPI",
            "Git", "GitHub"
        ]
        skills_repo = SkillsRepository()
        await skills_repo.seed_default_skills(DEFAULT_SKILLS)
    except Exception as e:
        # Log and allow application startup so we can diagnose connection issues
        import logging
        logger = logging.getLogger("uvicorn.error")
        logger.error(f"Could not connect to MongoDB or seed database during startup. Error: {e}")
    yield
    # Shutdown: Clean up connections
    await close_mongo_connection()

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Include API Router
app.include_router(api_v1_router, prefix=settings.API_V1_STR)

# CORS Configuration
if settings.CORS_ORIGINS:
    # app.add_middleware(
    #     CORSMiddleware,
    #     allow_origins=[str(origin) for origin in settings.CORS_ORIGINS],
    #     allow_credentials=True,
    #     allow_methods=["*"],
    #     allow_headers=["*"],
    # )
    app.add_middleware(
        CORSMiddleware,
         allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
     )

@app.get("/health", tags=["health"])
async def health_check():
    """
    Health check endpoint to verify server status and database connectivity.
    """
    db = get_database()
    db_status = "unconnected"
    if db is not None:
        try:
            # Check connection using MongoDB ping command
            await db.client.admin.command("ping")
            db_status = "connected"
        except Exception:
            db_status = "error"
            
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "database_status": db_status
    }

@app.get("/")
async def root():
    return {
        "message": f"Welcome to the {settings.PROJECT_NAME} API. Access documentation at /docs"
    }
