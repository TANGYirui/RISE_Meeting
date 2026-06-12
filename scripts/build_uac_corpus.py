#!/usr/bin/env python3
"""Convert meeting PDFs and build a meeting-aware RISE corpus."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from rise.uac_corpus import build_corpus
from rise.uac_extract import DoclingBackend, extract_pdf
from rise.uac_metadata import disambiguate_doc_ids, parse_uac_filename
from rise.uac_pipeline import (
    load_checkpoint,
    pending_pdfs,
    retain_matching_records,
    save_checkpoint,
    upsert_record,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        required=True,
        metavar="RAW_DATA_PATH",
        help="Directory containing the source PDF files.",
    )
    parser.add_argument("--extracted-dir", type=Path, default=REPO_ROOT / "corpus" / "uac_extracted")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "runs" / "uac_corpus")
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--meeting-date",
        help="Only convert documents whose filename metadata has this ISO meeting date.",
    )
    args = parser.parse_args()

    checkpoint_path = args.out / "extraction_records.json"
    records = load_checkpoint(checkpoint_path)
    all_pdfs = sorted(args.source_dir.glob("*.pdf"))
    parsed = [parse_uac_filename(pdf.name) for pdf in all_pdfs]
    metadata = disambiguate_doc_ids([record for record in parsed if record is not None])
    metadata_by_filename = {record.filename: record for record in metadata}
    pdfs = all_pdfs
    if args.meeting_date:
        pdfs = [
            pdf
            for pdf in pdfs
            if metadata_by_filename.get(pdf.name) is not None
            and metadata_by_filename[pdf.name].meeting_date == args.meeting_date
        ]
    if args.limit:
        pdfs = pdfs[:args.limit]
    selected_filenames = {pdf.name for pdf in pdfs}
    expected_doc_ids = {
        filename: record.doc_id
        for filename, record in metadata_by_filename.items()
        if filename in selected_filenames
    }
    untouched_records = [
        record
        for record in records
        if record.get("filename") not in selected_filenames
    ]
    selected_records, stale_relpaths = retain_matching_records(records, expected_doc_ids)
    records = sorted(untouched_records + selected_records, key=lambda record: record.get("filename", ""))
    extracted_root = args.extracted_dir.resolve()
    for relpath in stale_relpaths:
        stale_path = (extracted_root / relpath).resolve()
        if str(stale_path).startswith(str(extracted_root)) and stale_path.is_file():
            stale_path.unlink()
    pending = pending_pdfs(pdfs, records)
    backend = DoclingBackend()
    print(f"selected={len(pdfs)} completed={len(pdfs) - len(pending)} pending={len(pending)}", flush=True)
    for processed, pdf in enumerate(pending, start=1):
        metadata = metadata_by_filename.get(pdf.name)
        if metadata is None:
            record = {"filename": pdf.name, "status": "failed", "error": "unrecognized filename", "relpath": ""}
            records = upsert_record(records, record)
            save_checkpoint(records, checkpoint_path)
            continue
        record = extract_pdf(pdf, metadata, args.extracted_dir, backend=backend)
        records = upsert_record(records, record)
        save_checkpoint(records, checkpoint_path)
        print(
            f"{pdf.name}: {record['status']} "
            f"(selected progress {processed}/{len(pending)}; total records {len(records)})",
            flush=True,
        )
    args.out.mkdir(parents=True, exist_ok=True)
    save_checkpoint(records, checkpoint_path)
    print(json.dumps(build_corpus(records, args.extracted_dir, args.out), indent=2))


if __name__ == "__main__":
    main()
