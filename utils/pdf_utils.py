import PyPDF2
from typing import Dict

def get_pdf_metadata(pdf_path: str) -> Dict:
    """Extract PDF metadata"""
    with open(pdf_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        metadata = pdf_reader.metadata
        
        return {
            'total_pages': len(pdf_reader.pages),
            'title': metadata.get('/Title', 'N/A') if metadata else 'N/A',
            'author': metadata.get('/Author', 'N/A') if metadata else 'N/A',
            'subject': metadata.get('/Subject', 'N/A') if metadata else 'N/A',
            'creator': metadata.get('/Creator', 'N/A') if metadata else 'N/A',
            'producer': metadata.get('/Producer', 'N/A') if metadata else 'N/A',
        }

def is_scanned_pdf(pdf_path: str) -> bool:
    """Check if PDF is scanned (image-based)"""
    with open(pdf_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        
        # Check first page
        if len(pdf_reader.pages) > 0:
            text = pdf_reader.pages[0].extract_text() or ''
            # If very little text, likely scanned
            return len(text.strip()) < 50
    
    return False
