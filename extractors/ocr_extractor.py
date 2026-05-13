from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, Iterator, Tuple

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

    def _prepare_for_tesseract(self, image, max_pixels: int = 6_000_000):
        from PIL import Image, ImageOps

        image = image.convert("L")
        width, height = image.size
        pixels = width * height

        if pixels > max_pixels:
            scale = (max_pixels / pixels) ** 0.5
            next_size = (max(1, int(width * scale)), max(1, int(height * scale)))
            image = image.resize(next_size, Image.Resampling.LANCZOS)

        image = ImageOps.autocontrast(image)
        return image.point(lambda value: 255 if value > 175 else 0, mode="1")

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
    
    def extract_text_ocr(
        self,
        dpi=300,
        page_from: int | None = None,
        page_to: int | None = None,
        page_timeout: int = 90,
        tesseract_config: str = "--oem 1 --psm 6",
        max_image_pixels: int = 6_000_000,
        progress_callback: Callable[[int, int | None], None] | None = None,
    ) -> Dict:
        """Extract text using OCR (for scanned PDFs)"""
        pytesseract = self._configure_tesseract()

        ocr_data = []
        warnings = []
        total_pages = None
        start = None
        end = None

        for page_num, image, document_pages in self._iter_page_images(dpi=dpi, page_from=page_from, page_to=page_to):
            total_pages = document_pages
            start = page_num if start is None else start
            end = page_num
            if progress_callback:
                progress_callback(page_num, document_pages)

            prepared = self._prepare_for_tesseract(image, max_pixels=max_image_pixels)
            try:
                text = pytesseract.image_to_string(
                    prepared,
                    config=tesseract_config,
                    timeout=page_timeout,
                )
            except RuntimeError as error:
                text = ""
                warnings.append(f"OCR skipped page {page_num}: {error}")
            finally:
                prepared.close()
            
            ocr_data.append({
                'page': page_num,
                'text': text,
                'char_count': len(text)
            })
        
        return {
            'method': 'OCR (Tesseract)',
            'total_pages': len(ocr_data),
            'selected_range': {'from': start or 1, 'to': end or start or 1, 'document_pages': total_pages},
            'warnings': warnings,
            'pages': ocr_data
        }

    def extract_text_ocr_parallel(
        self,
        dpi=300,
        page_from: int | None = None,
        page_to: int | None = None,
        page_timeout: int = 90,
        tesseract_config: str = "--oem 1 --psm 6",
        max_image_pixels: int = 6_000_000,
        workers: int = 2,
        progress_callback: Callable[[int, int | None], None] | None = None,
    ) -> Dict:
        import PyPDF2

        with open(self.pdf_path, "rb") as file:
            total_pages = len(PyPDF2.PdfReader(file).pages)

        start, end = self._page_bounds(total_pages, page_from, page_to)
        page_numbers = list(range(start, end + 1))
        max_workers = max(1, min(int(workers), len(page_numbers)))

        if max_workers <= 1:
            return self.extract_text_ocr(
                dpi=dpi,
                page_from=page_from,
                page_to=page_to,
                page_timeout=page_timeout,
                tesseract_config=tesseract_config,
                max_image_pixels=max_image_pixels,
                progress_callback=progress_callback,
            )

        pages = []
        warnings = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self._ocr_single_page,
                    page_num,
                    dpi,
                    page_timeout,
                    tesseract_config,
                    max_image_pixels,
                    total_pages,
                ): page_num
                for page_num in page_numbers
            }

            for future in as_completed(futures):
                page_num = futures[future]
                if progress_callback:
                    progress_callback(page_num, total_pages)
                result = future.result()
                pages.append(result["page"])
                warnings.extend(result["warnings"])

        pages.sort(key=lambda page: page["page"])
        return {
            'method': f'OCR (Tesseract parallel x{max_workers})',
            'total_pages': len(pages),
            'selected_range': {'from': start, 'to': end, 'document_pages': total_pages},
            'warnings': warnings,
            'pages': pages
        }

    def _ocr_single_page(self, page_num, dpi, page_timeout, tesseract_config, max_image_pixels, total_pages):
        pytesseract = self._configure_tesseract()
        warnings = []
        text = ""

        for rendered_page, image, _document_pages in self._iter_page_images(dpi=dpi, page_from=page_num, page_to=page_num):
            prepared = self._prepare_for_tesseract(image, max_pixels=max_image_pixels)
            try:
                text = pytesseract.image_to_string(
                    prepared,
                    config=tesseract_config,
                    timeout=page_timeout,
                )
            except RuntimeError as error:
                warnings.append(f"OCR skipped page {rendered_page}: {error}")
            finally:
                prepared.close()
            break

        return {
            "page": {"page": page_num, "text": text, "char_count": len(text)},
            "warnings": warnings,
            "document_pages": total_pages,
        }
    
    def extract_with_config(
        self,
        config='--psm 6',
        page_from: int | None = None,
        page_to: int | None = None,
        page_timeout: int = 90,
        max_image_pixels: int = 6_000_000,
    ) -> Dict:
        """Extract with custom Tesseract config"""
        pytesseract = self._configure_tesseract()

        ocr_data = []
        warnings = []
        total_pages = None
        start = None
        end = None

        for page_num, image, document_pages in self._iter_page_images(dpi=300, page_from=page_from, page_to=page_to):
            total_pages = document_pages
            start = page_num if start is None else start
            end = page_num
            prepared = self._prepare_for_tesseract(image, max_pixels=max_image_pixels)
            try:
                text = pytesseract.image_to_string(prepared, config=config, timeout=page_timeout)
            except RuntimeError as error:
                text = ""
                warnings.append(f"OCR skipped page {page_num}: {error}")
            finally:
                prepared.close()
            
            ocr_data.append({
                'page': page_num,
                'text': text,
                'char_count': len(text)
            })
        
        return {
            'method': f'OCR (Tesseract with {config})',
            'total_pages': len(ocr_data),
            'selected_range': {'from': start or 1, 'to': end or start or 1, 'document_pages': total_pages},
            'warnings': warnings,
            'pages': ocr_data
        }
