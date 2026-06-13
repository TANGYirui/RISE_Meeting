from pathlib import Path

import pytest

from rise.inquiry.source_pdfs import SourcePdfResolver


def test_source_pdf_resolves_manifest_filename_without_exposing_path(tmp_path: Path):
    raw = tmp_path / "raw"
    raw.mkdir()
    source = raw / "Item3_Tuition_Fees_20240509.pdf"
    source.write_bytes(b"%PDF")
    manifest = {
        "item3": {"filename": source.name, "role": "agenda_item"},
        "meeting": {"filename": "overview.txt", "role": "meeting_overview"},
    }

    resolver = SourcePdfResolver(raw, manifest)

    assert resolver.resolve("item3") == source
    assert resolver.source_metadata("item3") == {
        "has_source_pdf": True,
        "source_url": "/api/sources/item3/pdf",
    }
    assert resolver.source_metadata("meeting")["has_source_pdf"] is False


def test_source_pdf_rejects_unknown_traversal_and_non_pdf(tmp_path: Path):
    manifest = {
        "escape": {"filename": "../secret.pdf", "role": "agenda_item"},
        "text": {"filename": "notes.txt", "role": "agenda_item"},
    }
    resolver = SourcePdfResolver(tmp_path, manifest)

    with pytest.raises(FileNotFoundError):
        resolver.resolve("unknown")
    with pytest.raises(ValueError):
        resolver.resolve("escape")
    with pytest.raises(ValueError):
        resolver.resolve("text")
