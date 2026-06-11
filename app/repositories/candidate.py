from bson import ObjectId
from app.core.database import get_database


class CandidateRepository:
    """
    Repository for candidate documents and ranking storage.
    """

    @property
    def collection(self):
        db = get_database()
        if db is None:
            raise RuntimeError("Database connection not established")
        return db.candidates

    async def create(self, candidate_data: dict) -> dict:
        result = await self.collection.insert_one(candidate_data)
        candidate_data["id"] = str(result.inserted_id)
        if "_id" in candidate_data:
            del candidate_data["_id"]
        return candidate_data

    async def update_by_email(self, email: str, data: dict) -> dict:
        """Update (or upsert) candidate record by email and return the new document."""
        if not email:
            return None
        await self.collection.update_one({"email": email}, {"$set": data}, upsert=True)
        doc = await self.collection.find_one({"email": email})
        if doc:
            doc["id"] = str(doc["_id"])
            del doc["_id"]
        return doc

    async def get_all(self) -> list:
        cursor = self.collection.find()
        out = []
        async for doc in cursor:
            doc["id"] = str(doc["_id"])
            del doc["_id"]
            out.append(doc)
        return out

    async def get_by_id(self, cid: str) -> dict:
        if not ObjectId.is_valid(cid):
            return None
        doc = await self.collection.find_one({"_id": ObjectId(cid)})
        if not doc:
            return None
        doc["id"] = str(doc["_id"])
        del doc["_id"]
        return doc

    async def get_ranked(self, job_id: str | None = None) -> list:
        """Return candidates sorted by score descending.
        If job_id is provided, prefer candidates with lastMatch.jobId == job_id
        and sort by lastMatch.score. Otherwise sort by top-level score.
        """
        query = {}
        sort_field = []
        if job_id:
            query = {"lastMatch.jobId": job_id}
            sort_field = [("lastMatch.score", -1)]
        else:
            sort_field = [("score", -1)]

        cursor = self.collection.find(query).sort(sort_field)
        out = []
        async for doc in cursor:
            doc["id"] = str(doc["_id"])
            del doc["_id"]
            out.append(doc)
        return out

    async def delete_by_resume_id(self, resume_id: str) -> int:
        """Delete candidate documents tied to a given resumeId."""
        result = await self.collection.delete_many({"resumeId": resume_id})
        return result.deleted_count

    async def delete_by_email(self, email: str) -> int:
        """Delete candidate documents tied to a given email."""
        if not email:
            return 0
        result = await self.collection.delete_many({"email": email})
        return result.deleted_count
