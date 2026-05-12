from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from io import BytesIO
from typing import Callable, Dict, List

from extractors.ocr_extractor import OCRExtractor


class AIOCRExtractor:
    def __init__(
        self,
        pdf_path: str,
        provider: str = "gemini",
        model: str = "gemini-2.5-flash",
        api_key: str | None = None,
    ):
        self.pdf_path = pdf_path
        self.provider = provider.lower()
        self.model = model
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.renderer = OCRExtractor(pdf_path)

    def extract_text_ai(
        self,
        dpi: int = 120,
        page_from: int | None = None,
        page_to: int | None = None,
        max_image_pixels: int = 4_000_000,
        progress_callback: Callable[[int, int | None], None] | None = None,
    ) -> Dict:
        if self.provider != "gemini":
            raise RuntimeError(f"Unsupported AI OCR provider: {self.provider}")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        pages = []
        all_records: List[Dict] = []
        warnings = []
        total_pages = None
        start = None
        end = None

        for page_num, image, document_pages in self.renderer._iter_page_images(
            dpi=dpi,
            page_from=page_from,
            page_to=page_to,
        ):
            total_pages = document_pages
            start = page_num if start is None else start
            end = page_num
            if progress_callback:
                progress_callback(page_num, document_pages)

            try:
                payload = self._image_to_jpeg_payload(image, max_image_pixels=max_image_pixels)
                parsed = self._extract_page_with_gemini(payload, page_num)
                text = str(parsed.get("text") or "")
                records = self._clean_records(parsed.get("records") or [], page_num)
                all_records.extend(records)
            except Exception as error:
                text = ""
                records = []
                warnings.append(f"AI OCR skipped page {page_num}: {error}")

            pages.append({
                "page": page_num,
                "text": text,
                "char_count": len(text),
                "ai_records": len(records),
            })

        return {
            "method": f"AI Vision OCR ({self.provider}:{self.model})",
            "total_pages": len(pages),
            "selected_range": {"from": start or 1, "to": end or start or 1, "document_pages": total_pages},
            "warnings": warnings,
            "pages": pages,
            "records": {"total_records": len(all_records), "records": all_records},
        }

    def _image_to_jpeg_payload(self, image, max_image_pixels: int) -> str:
        from PIL import ImageOps

        image = image.convert("RGB")
        image = ImageOps.autocontrast(image)
        width, height = image.size
        pixels = width * height
        if pixels > max_image_pixels:
            scale = (max_image_pixels / pixels) ** 0.5
            image = image.resize((max(1, int(width * scale)), max(1, int(height * scale))))

        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=82, optimize=True)
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    def _extract_page_with_gemini(self, image_b64: str, page_num: int) -> Dict:
        prompt = (
            "You are extracting data from a scanned Indian electoral roll PDF page. "
            "Extract every visible voter/elector entry on the page, including entries in all columns. "
            "Do not summarize, skip, or sample records. Return valid JSON only, with no markdown. "
            "Use this exact schema: "
            '{"text":"full readable page text with line breaks",'
            '"records":[{"serial_no":null,"epic_id":"","name":"","relation_type":"",'
            '"relation_name":"","house_number":"","age":null,"gender":""}]}. '
            "If a field is not visible, use null for numbers and empty string for text. "
            f"The page number is {page_num}; do not include commentary."
        )
        body = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}},
                ]
            }],
            "generationConfig": {
                "temperature": 0,
                "response_mime_type": "application/json",
            },
        }
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Gemini API error {error.code}: {detail}") from error

        text = (
            raw.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        return self._parse_json_text(text)

    def _parse_json_text(self, value: str) -> Dict:
        value = value.strip()
        if value.startswith("```"):
            value = re.sub(r"^```(?:json)?\s*", "", value)
            value = re.sub(r"\s*```$", "", value)
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", value, flags=re.DOTALL)
            if not match:
                raise
            parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else {"text": str(parsed), "records": []}

    def _clean_records(self, records, page_num: int) -> List[Dict]:
        cleaned = []
        if not isinstance(records, list):
            return cleaned

        for record in records:
            if not isinstance(record, dict):
                continue
            cleaned.append({
                "page": page_num,
                "serial_no": self._to_int(record.get("serial_no")),
                "epic_id": str(record.get("epic_id") or "").strip(),
                "name": str(record.get("name") or "").strip(),
                "relation_type": str(record.get("relation_type") or "").strip(),
                "relation_name": str(record.get("relation_name") or "").strip(),
                "house_number": str(record.get("house_number") or "").strip(),
                "age": self._to_int(record.get("age")),
                "gender": str(record.get("gender") or "").strip(),
            })
        return [record for record in cleaned if record["name"] or record["epic_id"]]

    def _to_int(self, value):
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
