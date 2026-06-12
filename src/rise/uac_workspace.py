"""Bounded same-meeting evidence expansion for RISE workspaces."""
from __future__ import annotations


def related_doc_ids(
    hit_doc_ids: list[str],
    documents: dict[str, dict],
    meetings: dict[str, dict[str, list[str]]],
    *,
    cap: int = 20,
) -> list[str]:
    """Return bounded related evidence without adding every meeting item."""
    hit_set = set(hit_doc_ids)
    related: list[str] = []
    for doc_id in hit_doc_ids:
        record = documents.get(doc_id)
        if not record:
            continue
        meeting = meetings.get(record.get("meeting_date", ""), {})
        role = record.get("role")
        candidates: list[str] = []
        if role in {"agenda_item", "draft_minutes", "circulation"}:
            candidates.extend(meeting.get("minutes", []))
            candidates.extend(meeting.get("meeting_overview", []))
        elif role in {"minutes", "meeting_overview"}:
            candidates.extend(meeting.get("minutes", []))
            if role == "minutes":
                candidates.extend(meeting.get("meeting_overview", []))
        for candidate in candidates:
            if candidate not in hit_set and candidate not in related:
                related.append(candidate)
                if len(related) >= cap:
                    return related
    return related

