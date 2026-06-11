import os
import re
import asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from app.repositories.resume import ResumeRepository
from app.services.extractor import extract_text

# Thread pool executor for offloading synchronous CPU-bound file parsing operations
executor = ThreadPoolExecutor(max_workers=4)

class ResumeService:
    """
    Service layer containing business logic and orchestrating files, extractors, and repository tasks.
    """
    
    def __init__(self):
        self.repository = ResumeRepository()

    async def _extract_text_async(self, file_path: str, content_type: str) -> str:
        """
        Execute synchronous text extraction inside an executor thread pool to avoid blocking the event loop.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(executor, extract_text, file_path, content_type)

    def _parse_basic_info(self, text: str) -> tuple:
        """
        Helper to pull candidate contact info using regex patterns.
        """
        # Match standard email address
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        email = email_match.group(0) if email_match else ""

        # Match phone numbers (e.g. +1-234-567-8901, (123) 456-7890, etc.)
        phone_match = re.search(r'\+?\d{1,4}?[-.\s]?\(?\d{1,3}?\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}', text)
        phone = phone_match.group(0) if phone_match else ""

        # Guess candidate name: check the first few lines of text
        candidate_name = ""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        if lines:
            # Check the first non-empty line. If it is brief, guess it is the name.
            first_line = lines[0]
            if len(first_line) < 50 and any(c.isalpha() for c in first_line):
                candidate_name = first_line

        return candidate_name, email, phone

    async def extract_and_save_resume(self, file_path: str, filename: str, content_type: str) -> dict:
        """
        Uploads a resume file stream, executes extraction, runs regex, and logs it.
        """
        # Run CPU-bound text extraction asynchronously
        extracted_text = await self._extract_text_async(file_path, content_type)
        
        # Heuristically parse contact details
        candidate_name, email, phone = self._parse_basic_info(extracted_text)

        resume_data = {
            "filename": filename,
            "extractedText": extracted_text,
            "uploadDate": datetime.utcnow(),
            "candidateName": candidate_name,
            "email": email,
            "phone": phone
        }

        # Persist document metadata in MongoDB
        return await self.repository.create(resume_data)

    async def get_all_resumes(self) -> list:
        """
        Get all resumes in collection.
        """
        return await self.repository.get_all()

    async def get_resume_by_id(self, resume_id: str) -> dict:
        """
        Get resume by id.
        """
        return await self.repository.get_by_id(resume_id)

    async def delete_resume(self, resume_id: str) -> bool:
        """
        Remove local stored file and remove DB document entry.
        """
        resume = await self.repository.get_by_id(resume_id)
        if not resume:
            return False

        # Delete local file from disk
        file_path = os.path.join("uploads", resume["filename"])
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                import logging
                logger = logging.getLogger("uvicorn.error")
                logger.error(f"Failed to delete physical file {file_path}: {e}")

        # Delete any candidate documents directly associated with this resume
        try:
            from app.repositories.candidate import CandidateRepository
            candidate_repo = CandidateRepository()
            deleted_count = await candidate_repo.delete_by_resume_id(resume_id)
            if deleted_count > 0:
                logger = logging.getLogger("uvicorn.error")
                logger.info(f"Deleted {deleted_count} candidate records associated with resume {resume_id}")
        except Exception as e:
            import logging
            logger = logging.getLogger("uvicorn.error")
            logger.error(f"Failed to delete candidate records for resume {resume_id}: {e}")

        # Delete document from MongoDB
        return await self.repository.delete(resume_id)
