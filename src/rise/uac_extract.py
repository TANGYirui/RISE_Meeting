"""Convert UAC PDFs into complete navigable documents for RISE."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from .uac_metadata import UACDocumentMetadata


@dataclass(frozen=True)
class ExtractionResult:
    markdown: str
    page_count: int
    backend: str
    status: str = "ok"
    error: str = ""


class DoclingBackend:
    """Lazy Docling adapter so metadata/corpus tools do not require Docling."""

    def __init__(self) -> None:
        self._converter = None

    def convert(self, pdf_path: Path) -> ExtractionResult:
        from docling.document_converter import DocumentConverter

        if self._converter is None:
            self._converter = DocumentConverter()
        conversion = self._converter.convert(pdf_path)
        document = conversion.document
        return ExtractionResult(
            markdown=document.export_to_markdown(),
            page_count=len(getattr(document, "pages", {}) or {}),
            backend="docling",
        )


def _disk_filename(doc_id: str, max_length: int = 128) -> str:
    filename = f"{doc_id}.txt"
    if len(filename) <= max_length:
        return filename
    suffix = sha256(doc_id.encode("utf-8")).hexdigest()[:12]
    prefix_length = max_length - len(suffix) - len("_.txt")
    return f"{doc_id[:prefix_length]}_{suffix}.txt"


def write_extraction(
    metadata: UACDocumentMetadata,
    result: ExtractionResult,
    output_root: Path,
) -> dict:
    """Write one complete document and return its manifest record."""
    role_dir = output_root / metadata.role
    role_dir.mkdir(parents=True, exist_ok=True)
    path = role_dir / _disk_filename(metadata.doc_id)
    header = [
        "---",
        f"doc_id: {metadata.doc_id}",
        f"role: {metadata.role}",
        f"meeting_date: {metadata.meeting_date}",
        f"item_number: {metadata.item_number if metadata.item_number is not None else ''}",
        f"source_pdf: {metadata.filename}",
        f"extraction_backend: {result.backend}",
        f"page_count: {result.page_count}",
        "---",
        "",
    ]
    path.write_text("\n".join(header) + result.markdown.strip() + "\n", encoding="utf-8")
    record = metadata.to_dict() | asdict(result)
    record.pop("markdown")
    record["relpath"] = path.relative_to(output_root).as_posix()
    return record


def extract_pdf(
    pdf_path: Path,
    metadata: UACDocumentMetadata,
    output_root: Path,
    backend=None,
) -> dict:
    backend = backend or DoclingBackend()
    try:
        result = backend.convert(pdf_path)
    except Exception as exc:
        result = ExtractionResult("", 0, type(backend).__name__, "failed", f"{type(exc).__name__}: {exc}")
    if result.status != "ok":
        return metadata.to_dict() | {
            "status": result.status,
            "backend": result.backend,
            "page_count": result.page_count,
            "error": result.error,
            "relpath": "",
        }
    return write_extraction(metadata, result, output_root)
