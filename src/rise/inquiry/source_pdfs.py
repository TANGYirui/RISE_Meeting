"""Resolve original PDFs by manifest doc_id without exposing raw paths."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import quote


class SourcePdfResolver:
    def __init__(self, raw_root: Path, document_manifest: dict[str, dict[str, Any]]):
        self.raw_root = Path(raw_root).resolve()
        self.document_manifest = document_manifest

    @classmethod
    def from_env(cls, document_manifest: dict[str, dict[str, Any]]) -> "SourcePdfResolver":
        raw_root = os.getenv("RISE_RAW_PDF_DIR", "").strip()
        if not raw_root:
            raise RuntimeError("RISE_RAW_PDF_DIR is not configured")
        return cls(Path(raw_root), document_manifest)

    def resolve(self, doc_id: str) -> Path:
        record = self.document_manifest.get(doc_id)
        if not record:
            raise FileNotFoundError(doc_id)
        filename = str(record.get("filename", ""))
        candidate = (self.raw_root / filename).resolve()
        if candidate.suffix.lower() != ".pdf":
            raise ValueError("source is not a PDF")
        try:
            candidate.relative_to(self.raw_root)
        except ValueError as exc:
            raise ValueError("source filename escapes configured PDF root") from exc
        if not candidate.is_file():
            raise FileNotFoundError(doc_id)
        return candidate

    def source_metadata(self, doc_id: str) -> dict[str, Any]:
        try:
            self.resolve(doc_id)
        except (FileNotFoundError, ValueError):
            return {"has_source_pdf": False, "source_url": ""}
        return {
            "has_source_pdf": True,
            "source_url": f"/api/sources/{quote(doc_id, safe='')}/pdf",
        }
