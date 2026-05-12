from __future__ import annotations

from typing import Dict

class OCRExtractor:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path

    def _pdf_to_images(self, dpi: int = 300, page_from: int | None = None, page_to: int | None = None):
        """
        Convert PDF pages to PIL Images.

        Primary: pdf2image (Poppler-based)
        Fallback: pypdfium2 renderer (bundled wheel, no Poppler/PyMuPDF DLLs)
        """
        try:
            from pdf2image import convert_from_path
            kwargs = {}
            if page_from:
                kwargs["first_page"] = max(1, int(page_from))
            if page_to:
                kwargs["last_page"] = max(1, int(page_to))
            return convert_from_path(self.pdf_path, dpi=dpi, **kwargs)
        except Exception as pdf2image_error:
            try:
                return self._pdf_to_images_pdfium(dpi=dpi, page_from=page_from, page_to=page_to)
            except Exception as pdfium_error:
                raise RuntimeError(
                    f"PDF rendering failed. pdf2image: {pdf2image_error}; pypdfium2: {pdfium_error}"
                ) from pdfium_error

    def _pdf_to_images_pdfium(self, dpi: int = 300, page_from: int | None = None, page_to: int | None = None):
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(self.pdf_path)
        images = []
        scale = max(dpi / 72.0, 1.0)
        total_pages = len(pdf)
        start = max(1, int(page_from)) if page_from else 1
        end = min(total_pages, int(page_to)) if page_to else total_pages

        for page_index in range(start - 1, end):
            page = pdf[page_index]
            bitmap = page.render(scale=scale)
            images.append(bitmap.to_pil())
            page.close()
        pdf.close()
        return images
    
    def extract_text_ocr(self, dpi=300, page_from: int | None = None, page_to: int | None = None) -> Dict:
        """Extract text using OCR (for scanned PDFs)"""
        import pytesseract

        # Convert PDF to images
        images = self._pdf_to_images(dpi=dpi, page_from=page_from, page_to=page_to)
        
        ocr_data = []
        start = max(1, int(page_from)) if page_from else 1
        for offset, image in enumerate(images):
            page_num = start + offset
            # Perform OCR
            text = pytesseract.image_to_string(image)
            
            ocr_data.append({
                'page': page_num,
                'text': text,
                'char_count': len(text)
            })
        
        return {
            'method': 'OCR (Tesseract)',
            'total_pages': len(ocr_data),
            'selected_range': {'from': start, 'to': (start + len(images) - 1) if images else start},
            'pages': ocr_data
        }
    
    def extract_with_config(self, config='--psm 6', page_from: int | None = None, page_to: int | None = None) -> Dict:
        """Extract with custom Tesseract config"""
        import pytesseract

        images = self._pdf_to_images(dpi=300, page_from=page_from, page_to=page_to)
        
        ocr_data = []
        start = max(1, int(page_from)) if page_from else 1
        for offset, image in enumerate(images):
            page_num = start + offset
            text = pytesseract.image_to_string(image, config=config)
            
            ocr_data.append({
                'page': page_num,
                'text': text,
                'char_count': len(text)
            })
        
        return {
            'method': f'OCR (Tesseract with {config})',
            'total_pages': len(ocr_data),
            'selected_range': {'from': start, 'to': (start + len(images) - 1) if images else start},
            'pages': ocr_data
        }
