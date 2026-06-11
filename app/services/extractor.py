import logging
from pathlib import Path
import pdfplumber
import docx

logger = logging.getLogger("uvicorn.error")

def extract_pdf(file_path: str) -> str:
    """
    Extract text from a PDF file using pdfplumber.
    """
    text_content = []
    try:
        with pdfplumber.open(file_path) as pdf:
            if not pdf.pages:
                raise ValueError("PDF document has no pages.")
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    text_content.append(page_text)
                else:
                    logger.warning(f"Could not extract text from page {i+1} of {file_path}")
    except Exception as e:
        logger.error(f"pdfplumber extraction error for {file_path}: {e}")
        raise ValueError(f"Failed to parse PDF document: {str(e)}")
        
    return "\n".join(text_content)

def extract_docx(file_path: str) -> str:
    """
    Extract text from a DOCX file using python-docx.
    """
    try:
        doc = docx.Document(file_path)
        paragraphs = []
        for p in doc.paragraphs:
            if p.text:
                paragraphs.append(p.text)
        return "\n".join(paragraphs)
    except Exception as e:
        logger.error(f"python-docx extraction error for {file_path}: {e}")
        raise ValueError(f"Failed to parse Word document: {str(e)}")

def extract_text(file_path: str, content_type: str) -> str:
    """
    Helper function to route a file to the correct extraction library.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    
    if suffix == ".pdf" or content_type == "application/pdf":
        return extract_pdf(file_path)
    elif suffix == ".docx" or content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return extract_docx(file_path)
    else:
        raise ValueError(f"Unsupported file format: {suffix or content_type}")
