from app.repositories.job import JobRepository


class JobService:
    """
    Service layer for job description business logic.
    """

    def __init__(self):
        self.repository = JobRepository()

    async def create_job(self, title: str, description: str, required_skills: list[str]) -> dict:
        """
        Validate and persist a new job description document.
        required_skills are normalised to stripped, non-empty strings.
        """
        cleaned_skills = [s.strip() for s in required_skills if s.strip()]
        job_data = {
            "title": title.strip(),
            "description": description.strip(),
            "requiredSkills": cleaned_skills,
        }
        return await self.repository.create(job_data)

    async def get_all_jobs(self) -> list:
        return await self.repository.get_all()

    async def get_job_by_id(self, job_id: str) -> dict | None:
        return await self.repository.get_by_id(job_id)
