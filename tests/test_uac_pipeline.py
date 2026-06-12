import json

from rise.uac_pipeline import (
    load_checkpoint,
    pending_pdfs,
    retain_matching_records,
    save_checkpoint,
)


def test_pending_pdfs_skips_successes_and_retries_failures(tmp_path):
    ok = tmp_path / "ok.pdf"
    failed = tmp_path / "failed.pdf"
    new = tmp_path / "new.pdf"
    for path in (ok, failed, new):
        path.write_bytes(b"%PDF")

    records = [
        {"filename": "ok.pdf", "status": "ok"},
        {"filename": "failed.pdf", "status": "failed"},
    ]

    assert pending_pdfs([ok, failed, new], records) == [failed, new]


def test_checkpoint_round_trip_replaces_same_filename(tmp_path):
    path = tmp_path / "extraction_records.json"
    save_checkpoint([{"filename": "a.pdf", "status": "failed"}], path)
    save_checkpoint(
        [
            {"filename": "a.pdf", "status": "ok"},
            {"filename": "b.pdf", "status": "ok"},
        ],
        path,
    )

    records = load_checkpoint(path)

    assert json.loads(path.read_text(encoding="utf-8")) == records
    assert records == [
        {"filename": "a.pdf", "status": "ok"},
        {"filename": "b.pdf", "status": "ok"},
    ]


def test_retain_matching_records_invalidates_changed_doc_ids():
    records = [
        {"filename": "same.pdf", "doc_id": "old", "relpath": "minutes/old.txt"},
        {"filename": "stable.pdf", "doc_id": "stable", "relpath": "minutes/stable.txt"},
    ]

    retained, stale = retain_matching_records(
        records,
        {"same.pdf": "new", "stable.pdf": "stable"},
    )

    assert retained == [records[1]]
    assert stale == ["minutes/old.txt"]
