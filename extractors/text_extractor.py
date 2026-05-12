from __future__ import annotations

from typing import Dict

class TextExtractor:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path

    def extract_with_pymupdf(self, page_from: int | None = None, page_to: int | None = None) -> Dict:
        """Extract text with PyMuPDF. This is much faster on large PDFs."""
        import fitz

        text_data = []
        doc = fitz.open(self.pdf_path)
        total_pages = len(doc)
        start = max(1, int(page_from)) if page_from else 1
        end = min(total_pages, int(page_to)) if page_to else total_pages

        for page_num in range(start, end + 1):
            page = doc[page_num - 1]
            text = page.get_text("text") or ""
            text_data.append({
                'page': page_num,
                'text': text,
                'char_count': len(text)
            })

        doc.close()

        return {
            'method': 'PyMuPDF',
            'total_pages': len(text_data),
            'selected_range': {'from': start, 'to': end, 'document_pages': total_pages},
            'pages': text_data
        }
        
    def extract_with_pdfplumber(self, page_from: int | None = None, page_to: int | None = None) -> Dict:
        """Extract text using pdfplumber (more accurate)"""
        import pdfplumber

        text_data = []
        
        with pdfplumber.open(self.pdf_path) as pdf:
            total_pages = len(pdf.pages)
            start = max(1, int(page_from)) if page_from else 1
            end = min(total_pages, int(page_to)) if page_to else total_pages

            for page_num in range(start, end + 1):
                page = pdf.pages[page_num - 1]
                text = page.extract_text()
                text_data.append({
                    'page': page_num,
                    'text': text,
                    'char_count': len(text) if text else 0
                })
        
        return {
            'method': 'pdfplumber',
            'total_pages': len(text_data),
            'selected_range': {'from': start, 'to': end, 'document_pages': total_pages},
            'pages': text_data
        }
    
    def extract_with_pypdf2(self, page_from: int | None = None, page_to: int | None = None) -> Dict:
        """Extract text using PyPDF2 (fallback)"""
        import PyPDF2

        text_data = []
        
        with open(self.pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)

            total_pages = len(pdf_reader.pages)
            start = max(1, int(page_from)) if page_from else 1
            end = min(total_pages, int(page_to)) if page_to else total_pages

            for page_num in range(start, end + 1):
                page = pdf_reader.pages[page_num - 1]
                text = page.extract_text()
                text_data.append({
                    'page': page_num,
                    'text': text,
                    'char_count': len(text) if text else 0
                })
        
        return {
            'method': 'PyPDF2',
            'total_pages': len(text_data),
            'selected_range': {'from': start, 'to': end, 'document_pages': total_pages},
            'pages': text_data
        }
    
    def extract_all(self, page_from: int | None = None, page_to: int | None = None) -> Dict:
        """Try multiple extraction methods"""
        try:
            return self.extract_with_pymupdf(page_from=page_from, page_to=page_to)
        except Exception as e:
            print(f"PyMuPDF failed: {e}, trying pdfplumber")
        try:
            return self.extract_with_pdfplumber(page_from=page_from, page_to=page_to)
        except Exception as e:
            print(f"pdfplumber failed: {e}, trying PyPDF2")
            return self.extract_with_pypdf2(page_from=page_from, page_to=page_to)
