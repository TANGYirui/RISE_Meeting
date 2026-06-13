"""Assemble user-visible AgendaTopic records from source documents."""
from __future__ import annotations

import hashlib
import re
from typing import Iterable, Mapping

from .models import AgendaTopic, MinutesEvidence, SourceRef


VISIBLE_ROLES = {"agenda_item", "minutes"}
ITEM_HEADING = re.compile(r"(?im)^(?:agenda\s+)?item\s+([0-9]+|[ivxlc]+)\b[^\n]*")


def _source(record: dict) -> SourceRef:
    return SourceRef(
        record["doc_id"],
        record.get("filename", ""),
        record.get("role", ""),
        record.get("source_url", ""),
        bool(record.get("has_source_pdf", False)),
    )


def _minutes_sections(doc_id: str, record: dict, text: str) -> list[tuple[int, MinutesEvidence, str]]:
    matches = list(ITEM_HEADING.finditer(text))
    sections: list[tuple[int, MinutesEvidence, str]] = []
    for index, match in enumerate(matches):
        raw_item = match.group(1)
        if not raw_item.isdigit():
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        excerpt = text[match.start():end].strip()
        line_start = text[:match.start()].count("\n") + 1
        line_end = line_start + excerpt.count("\n")
        title = match.group(0).strip()
        sections.append(
            (
                int(raw_item),
                MinutesEvidence(doc_id, record.get("filename", ""), excerpt, line_start, line_end),
                title,
            )
        )
    return sections


def assemble_topics(
    candidate_doc_ids: Iterable[str],
    document_manifest: Mapping[str, dict],
    texts: Mapping[str, str],
) -> list[AgendaTopic]:
    candidates = set(candidate_doc_ids)
    agenda_by_key: dict[tuple[str, int], AgendaTopic] = {}
    minutes_by_key: dict[tuple[str, int], list[tuple[SourceRef, MinutesEvidence, str]]] = {}

    for doc_id in candidates:
        record = document_manifest.get(doc_id)
        if not record or record.get("role") not in VISIBLE_ROLES:
            continue
        if record.get("role") == "agenda_item" and record.get("item_number") is not None:
            item = int(record["item_number"])
            date = record.get("meeting_date", "")
            agenda_by_key[(date, item)] = AgendaTopic(
                topic_id=f"{date}:item{item}",
                title=record.get("title") or f"Item {item}",
                meeting_date=date,
                item_number=item,
                agenda_document=_source(record),
                candidate_sources=[doc_id],
            )
        elif record.get("role") == "minutes":
            for item, evidence, title in _minutes_sections(doc_id, record, texts.get(doc_id, "")):
                minutes_by_key.setdefault((record.get("meeting_date", ""), item), []).append(
                    (_source(record), evidence, title)
                )

    for doc_id, record in document_manifest.items():
        if record.get("role") != "agenda_item" or record.get("item_number") is None:
            continue
        key = (record.get("meeting_date", ""), int(record["item_number"]))
        if key in minutes_by_key and key not in agenda_by_key:
            agenda_by_key[key] = AgendaTopic(
                topic_id=f"{key[0]}:item{key[1]}",
                title=record.get("title") or f"Item {key[1]}",
                meeting_date=key[0],
                item_number=key[1],
                agenda_document=_source(record),
                candidate_sources=[doc_id, "same_meeting_pairing"],
            )

    topics: list[AgendaTopic] = []
    for key in sorted(set(agenda_by_key) | set(minutes_by_key)):
        topic = agenda_by_key.get(key)
        minutes = minutes_by_key.get(key, [])
        if topic is None:
            date, item = key
            seed = f"{date}:{item}:{minutes[0][1].excerpt if minutes else ''}"
            topic = AgendaTopic(
                topic_id=f"{date}:minutes-only:{hashlib.sha256(seed.encode()).hexdigest()[:10]}",
                title=minutes[0][2] if minutes else f"Minutes Item {item}",
                meeting_date=date,
                item_number=item,
                topic_kind="minutes_only",
            )
        for source, evidence, _ in minutes:
            if source.doc_id not in {value.doc_id for value in topic.minutes_documents}:
                topic.minutes_documents.append(source)
            topic.minutes_evidence.append(evidence)
            topic.candidate_sources.append(source.doc_id)
        topics.append(topic)
    return topics
