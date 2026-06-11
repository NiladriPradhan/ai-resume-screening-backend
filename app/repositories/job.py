from datetime import datetime
from bson import ObjectId
from app.core.database import get_database


class JobRepository:
    """
    Repository layer for all MongoDB operations on the jobs collection.
    """

    @property
    def collection(self):
        db = get_database()
        if db is None:
            raise RuntimeError("Database connection not established")
        return db.jobs

    @staticmethod
    def _serialize(doc: dict) -> dict:
        """Convert _id ObjectId to string id field."""
        doc["id"] = str(doc["_id"])
        del doc["_id"]
        return doc

    async def create(self, job_data: dict) -> dict:
        """Insert a new job document."""
        job_data["createdAt"] = datetime.utcnow()
        result = await self.collection.insert_one(job_data)
        job_data["id"] = str(result.inserted_id)
        job_data.pop("_id", None)
        return job_data

    async def get_all(self) -> list:
        """Retrieve all job documents sorted by newest first."""
        cursor = self.collection.find().sort("createdAt", -1)
        jobs = []
        async for doc in cursor:
            jobs.append(self._serialize(doc))
        return jobs

    async def get_by_id(self, job_id: str) -> dict | None:
        """Retrieve a single job by its ObjectId string."""
        if not ObjectId.is_valid(job_id):
            return None
        doc = await self.collection.find_one({"_id": ObjectId(job_id)})
        return self._serialize(doc) if doc else None
