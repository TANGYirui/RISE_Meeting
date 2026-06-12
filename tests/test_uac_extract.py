from pathlib import Path

from rise.uac_extract import ExtractionResult, write_extraction
from rise.uac_metadata import parse_uac_filename


def test_write_extraction_adds_navigation_metadata_and_page_markers(tmp_path):
    metadata = parse_uac_filename("Item5_Net_Zero_Action_Plan_20240509.pdf")
    result = ExtractionResult(
        markdown="# Net-Zero Action Plan\n\n## Background\n\nEvidence.",
        page_count=2,
        backend="fake",
        status="ok",
    )

    record = write_extraction(metadata, result, tmp_path)
    text = (tmp_path / record["relpath"]).read_text(encoding="utf-8")

    assert "role: agenda_item" in text
    assert "meeting_date: 2024-05-09" in text
    assert "# Net-Zero Action Plan" in text
    assert record["status"] == "ok"


def test_write_extraction_shortens_long_disk_filename_without_changing_doc_id(tmp_path):
    metadata = parse_uac_filename(
        "Item3_"
        + "Very_Long_Descriptive_Title_" * 20
        + "20241122.pdf"
    )
    result = ExtractionResult(markdown="Evidence.", page_count=1, backend="fake")

    record = write_extraction(metadata, result, tmp_path)
    output_path = tmp_path / record["relpath"]

    assert output_path.is_file()
    assert len(output_path.name) <= 128
    assert record["doc_id"] == metadata.doc_id
