from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict


class SupabaseStore:
    """Small Supabase REST client for result persistence without extra deps."""

    def __init__(self) -> None:
        self.url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
        self.key = (
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_KEY")
            or os.environ.get("SUPABASE_ANON_KEY")
            or ""
        )
        self.table = os.environ.get("SUPABASE_RESULTS_TABLE", "extraction_results")
        self.bucket = os.environ.get("SUPABASE_STORAGE_BUCKET", "")

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.key)

    def save_result(self, job_id: str, filename: str, result: Dict[str, Any]) -> Dict[str, Any]:
        if not self.enabled:
            return {"enabled": False}

        saved: Dict[str, Any] = {"enabled": True}
        errors = []

        if self.table:
            try:
                saved["table"] = self._upsert_result(job_id, filename, result)
            except Exception as exc:
                errors.append(f"table: {exc}")

        if self.bucket:
            try:
                saved["result_json"] = self.upload_json(
                    f"results/{job_id}_{self._safe_name(filename)}_results.json",
                    result,
                )
            except Exception as exc:
                errors.append(f"storage: {exc}")

        if errors:
            saved["warning"] = "Supabase save partially failed: " + "; ".join(errors)
        return saved

    def upload_file(self, local_path: str, remote_path: str, content_type: str) -> str:
        if not (self.enabled and self.bucket):
            raise RuntimeError("Supabase storage is not configured.")

        with open(local_path, "rb") as handle:
            data = handle.read()
        return self._storage_upload(remote_path, data, content_type)

    def upload_json(self, remote_path: str, payload: Dict[str, Any]) -> str:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return self._storage_upload(remote_path, data, "application/json")

    def _upsert_result(self, job_id: str, filename: str, result: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "id": job_id,
            "filename": filename,
            "result": result,
        }
        endpoint = f"{self.url}/rest/v1/{self.table}"
        headers = self._headers(
            {
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=representation",
            }
        )
        response = self._request(endpoint, "POST", json.dumps(payload).encode("utf-8"), headers)
        return {"table": self.table, "rows": len(json.loads(response or "[]"))}

    def _storage_upload(self, remote_path: str, data: bytes, content_type: str) -> str:
        remote_path = "/".join(part for part in remote_path.split("/") if part)
        endpoint = f"{self.url}/storage/v1/object/{self.bucket}/{remote_path}"
        headers = self._headers(
            {
                "Content-Type": content_type,
                "Cache-Control": "3600",
                "x-upsert": "true",
            }
        )
        self._request(endpoint, "POST", data, headers)
        return f"{self.url}/storage/v1/object/public/{self.bucket}/{remote_path}"

    def _headers(self, extra: Dict[str, str] | None = None) -> Dict[str, str]:
        headers = {"apikey": self.key, "Authorization": f"Bearer {self.key}"}
        if extra:
            headers.update(extra)
        return headers

    def _request(self, url: str, method: str, data: bytes, headers: Dict[str, str]) -> str:
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{exc.code} {detail}") from exc

    @staticmethod
    def _safe_name(filename: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "-", filename).strip("-") or "document"
