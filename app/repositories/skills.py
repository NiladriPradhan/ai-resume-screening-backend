import logging
from app.core.database import get_database

logger = logging.getLogger("uvicorn.error")

class SkillsRepository:
    """
    Repository layer for managing the list of keyword skills in MongoDB.
    """
    
    @property
    def collection(self):
        db = get_database()
        if db is None:
            raise RuntimeError("Database connection not established")
        return db.skills

    async def get_all_skills(self) -> list[str]:
        """
        Query MongoDB to retrieve the full list of skill keyword strings.
        """
        try:
            cursor = self.collection.find()
            skills = []
            async for doc in cursor:
                if "name" in doc:
                    skills.append(doc["name"])
            return skills
        except Exception as e:
            logger.error(f"Error querying skills collection: {e}")
            return []

    async def seed_default_skills(self, default_skills: list[str]) -> None:
        """
        Seeding method called on application startup if no skills records exist.
        """
        try:
            count = await self.collection.count_documents({})
            if count == 0:
                docs = [{"name": skill} for skill in default_skills]
                await self.collection.insert_many(docs)
                logger.info(f"Database successfully seeded with {len(default_skills)} default skills.")
            else:
                logger.info("Database skills collection is already populated. Seeding skipped.")
        except Exception as e:
            logger.error(f"Error seeding database skills: {e}")
