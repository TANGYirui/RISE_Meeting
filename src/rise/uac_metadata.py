"""Filename-derived metadata for HKUST UAC meeting documents."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


@dataclass(frozen=True)
class UACDocumentMetadata:
    doc_id: str
    filename: str
    role: str
    meeting_date: str
    item_number: int | None = None
    title: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _doc_id(filename: str) -> str:
    stem = re.sub(r"\(\d+\)$", "", Path(filename).stem)
    return re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")


def _iso_yymmdd(raw: str) -> str:
    year = int(raw[:2]) + (1900 if int(raw[:2]) >= 50 else 2000)
    month = max(1, int(raw[2:4]))
    day = max(1, int(raw[4:6]))
    return f"{year:04d}-{month:02d}-{day:02d}"


def _iso_yyyymmdd(raw: str) -> str:
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def _roman_to_int(raw: str) -> int:
    total = 0
    for index, char in enumerate(raw):
        value = ROMAN_VALUES[char]
        total += -value if index + 1 < len(raw) and ROMAN_VALUES[raw[index + 1]] > value else value
    return total


def parse_uac_filename(filename: str) -> UACDocumentMetadata | None:
    stem = Path(filename).stem
    match = re.match(r"^Item(\d+|[IVXLC]+)[_ ](.+?)[_ ](\d{8})(?:\(\d+\))?$", stem)
    if match:
        raw_item, raw_title, raw_date = match.groups()
        title = raw_title.replace("_", " ").strip()
        return UACDocumentMetadata(
            _doc_id(filename),
            filename,
            "draft_minutes" if "draft minutes" in title.lower() else "agenda_item",
            _iso_yyyymmdd(raw_date),
            int(raw_item) if raw_item.isdigit() else _roman_to_int(raw_item),
            title,
        )
    match = re.match(r"^Minutes_(\d{6})$", stem)
    if match:
        return UACDocumentMetadata(_doc_id(filename), filename, "minutes", _iso_yymmdd(match.group(1)))
    match = re.match(r"^TableOfContents_(\d{8})(?:\(\d+\))?$", stem)
    if match:
        return UACDocumentMetadata(_doc_id(filename), filename, "table_of_contents", _iso_yyyymmdd(match.group(1)))
    match = re.match(r"^(\d{6}|\d{4}_\d{2})_uac_papers?_via_circ", stem, re.IGNORECASE)
    if match:
        return UACDocumentMetadata(
            _doc_id(filename),
            filename,
            "circulation",
            _iso_yymmdd(match.group(1).replace("_", "")),
        )
    match = re.match(r"^(\d{6})-(.+)$", stem)
    if match:
        return UACDocumentMetadata(_doc_id(filename), filename, "historical", _iso_yymmdd(match.group(1)), title=match.group(2))
    return None


def disambiguate_doc_ids(metadata: list[UACDocumentMetadata]) -> list[UACDocumentMetadata]:
    """Append a stable suffix only when normalized filenames collide."""
    grouped: dict[str, list[UACDocumentMetadata]] = defaultdict(list)
    for record in metadata:
        grouped[record.doc_id].append(record)

    resolved: list[UACDocumentMetadata] = []
    for record in metadata:
        if len(grouped[record.doc_id]) == 1:
            resolved.append(record)
            continue
        suffix = sha256(record.filename.encode("utf-8")).hexdigest()[:8]
        resolved.append(replace(record, doc_id=f"{record.doc_id}_{suffix}"))
    return resolved
