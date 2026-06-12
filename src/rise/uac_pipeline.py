"""Checkpoint helpers for resumable UAC PDF extraction."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable


def load_checkpoint(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_checkpoint(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(records, indent=2), encoding="utf-8")
    os.replace(temp, path)


def pending_pdfs(pdfs: Iterable[Path], records: list[dict]) -> list[Path]:
    successful = {
        record.get("filename")
        for record in records
        if record.get("status") == "ok"
    }
    return [pdf for pdf in pdfs if pdf.name not in successful]


def upsert_record(records: list[dict], record: dict) -> list[dict]:
    by_filename = {
        existing["filename"]: existing
        for existing in records
        if existing.get("filename")
    }
    by_filename[record["filename"]] = record
    return [by_filename[name] for name in sorted(by_filename)]


def retain_matching_records(
    records: list[dict],
    expected_doc_ids: dict[str, str],
) -> tuple[list[dict], list[str]]:
    """Keep reusable records and report stale extracted paths to remove."""
    retained = []
    stale_relpaths = []
    for record in records:
        filename = record.get("filename")
        if filename not in expected_doc_ids:
            continue
        if record.get("doc_id") != expected_doc_ids[filename]:
            if record.get("relpath"):
                stale_relpaths.append(record["relpath"])
            continue
        retained.append(record)
    return retained, sorted(set(stale_relpaths))
