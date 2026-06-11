from bson import ObjectId
from app.core.database import get_database

class ResumeRepository:
    """
    Repository class to encapsulate database interactions for Resumes.
    """
    
    @property
    def collection(self):
        db = get_database()
        if db is None:
            raise RuntimeError("Database connection not established")
        return db.resumes

    async def create(self, resume_data: dict) -> dict:
        """
        Insert a new resume document into the database.
        """
        result = await self.collection.insert_one(resume_data)
        resume_data["id"] = str(result.inserted_id)
        # Remove original mongodb object id if it exists in data to avoid serialization issues
        if "_id" in resume_data:
            del resume_data["_id"]
        return resume_data

    async def get_all(self) -> list:
        """
        Retrieve all resume documents.
        """
        cursor = self.collection.find()
        resumes = []
        async for doc in cursor:
            doc["id"] = str(doc["_id"])
            del doc["_id"]
            resumes.append(doc)
        return resumes

    async def get_by_id(self, resume_id: str) -> dict:
        """
        Retrieve a single resume document by its ObjectId.
        """
        if not ObjectId.is_valid(resume_id):
            return None
        doc = await self.collection.find_one({"_id": ObjectId(resume_id)})
        if doc:
            doc["id"] = str(doc["_id"])
            del doc["_id"]
            return doc
        return None

    async def delete(self, resume_id: str) -> bool:
        """
        Delete a resume document by its ObjectId.
        """
        if not ObjectId.is_valid(resume_id):
            return False
        result = await self.collection.delete_one({"_id": ObjectId(resume_id)})
        return result.deleted_count > 0
