from __future__ import annotations

import os
from typing import Dict, Iterator, Tuple

class OCRExtractor:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path

    def _configure_tesseract(self):
        import pytesseract

        candidates = [
            os.environ.get("TESSERACT_CMD"),
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            "/usr/bin/tesseract",
            "/usr/local/bin/tesseract",
        ]
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                pytesseract.pytesseract.tesseract_cmd = candidate
                break

        return pytesseract

    def _page_bounds(self, total_pages: int, page_from: int | None = None, page_to: int | None = None) -> Tuple[int, int]:
        start = max(1, int(page_from)) if page_from else 1
        end = min(total_pages, int(page_to)) if page_to else total_pages
        return start, max(start, end)

    def _iter_page_images(self, dpi: int = 300, page_from: int | None = None, page_to: int | None = None) -> Iterator[Tuple[int, object, int]]:
        """
        Yield one rendered page image at a time.

        OCR images can be very large, so streaming keeps large scanned PDFs from
        loading every selected page into memory before Tesseract starts.
        """
        errors = []
        for renderer in (
            self._iter_page_images_pymupdf,
            self._iter_page_images_pdfium,
            self._iter_page_images_pdf2image,
        ):
            try:
                yield from renderer(dpi=dpi, page_from=page_from, page_to=page_to)
                return
            except Exception as error:
                errors.append(f"{renderer.__name__}: {error}")

        raise RuntimeError("PDF rendering failed. " + "; ".join(errors))

    def _iter_page_images_pymupdf(self, dpi: int = 300, page_from: int | None = None, page_to: int | None = None):
        import fitz
        from PIL import Image

        doc = fitz.open(self.pdf_path)
        try:
            total_pages = len(doc)
            start, end = self._page_bounds(total_pages, page_from, page_to)
            matrix = fitz.Matrix(max(dpi / 72.0, 1.0), max(dpi / 72.0, 1.0))

            for page_num in range(start, end + 1):
                page = doc[page_num - 1]
                pixmap = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False)
                image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                yield page_num, image, total_pages
                image.close()
                pixmap = None
        finally:
            doc.close()

    def _iter_page_images_pdfium(self, dpi: int = 300, page_from: int | None = None, page_to: int | None = None):
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(self.pdf_path)
        try:
            total_pages = len(pdf)
            start, end = self._page_bounds(total_pages, page_from, page_to)
            scale = max(dpi / 72.0, 1.0)

            for page_index in range(start - 1, end):
                page = pdf[page_index]
                try:
                    bitmap = page.render(scale=scale)
                    image = bitmap.to_pil()
                    yield page_index + 1, image, total_pages
                    image.close()
                finally:
                    page.close()
        finally:
            pdf.close()

    def _iter_page_images_pdf2image(self, dpi: int = 300, page_from: int | None = None, page_to: int | None = None):
        from pdf2image import convert_from_path
        from PyPDF2 import PdfReader

        with open(self.pdf_path, "rb") as file:
            total_pages = len(PdfReader(file).pages)

        start, end = self._page_bounds(total_pages, page_from, page_to)
        for page_num in range(start, end + 1):
            images = convert_from_path(
                self.pdf_path,
                dpi=dpi,
                first_page=page_num,
                last_page=page_num,
            )
            if not images:
                continue
            image = images[0]
            yield page_num, image, total_pages
            image.close()

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
        start, end = self._page_bounds(total_pages, page_from, page_to)

        for page_index in range(start - 1, end):
            page = pdf[page_index]
            bitmap = page.render(scale=scale)
            images.append(bitmap.to_pil())
            page.close()
        pdf.close()
        return images
    
    def extract_text_ocr(self, dpi=300, page_from: int | None = None, page_to: int | None = None) -> Dict:
        """Extract text using OCR (for scanned PDFs)"""
        pytesseract = self._configure_tesseract()

        ocr_data = []
        total_pages = None
        start = None
        end = None

        for page_num, image, document_pages in self._iter_page_images(dpi=dpi, page_from=page_from, page_to=page_to):
            total_pages = document_pages
            start = page_num if start is None else start
            end = page_num
            text = pytesseract.image_to_string(image)
            
            ocr_data.append({
                'page': page_num,
                'text': text,
                'char_count': len(text)
            })
        
        return {
            'method': 'OCR (Tesseract)',
            'total_pages': len(ocr_data),
            'selected_range': {'from': start or 1, 'to': end or start or 1, 'document_pages': total_pages},
            'pages': ocr_data
        }
    
    def extract_with_config(self, config='--psm 6', page_from: int | None = None, page_to: int | None = None) -> Dict:
        """Extract with custom Tesseract config"""
        pytesseract = self._configure_tesseract()

        ocr_data = []
        total_pages = None
        start = None
        end = None

        for page_num, image, document_pages in self._iter_page_images(dpi=300, page_from=page_from, page_to=page_to):
            total_pages = document_pages
            start = page_num if start is None else start
            end = page_num
            text = pytesseract.image_to_string(image, config=config)
            
            ocr_data.append({
                'page': page_num,
                'text': text,
                'char_count': len(text)
            })
        
        return {
            'method': f'OCR (Tesseract with {config})',
            'total_pages': len(ocr_data),
            'selected_range': {'from': start or 1, 'to': end or start or 1, 'document_pages': total_pages},
            'pages': ocr_data
        }
