"""Serializable domain models used by the inquiry application."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SourceRef:
    doc_id: str
    filename: str
    role: str = ""
    source_url: str = ""
    has_source_pdf: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceRef":
        return cls(**data)


@dataclass
class MinutesEvidence:
    doc_id: str
    filename: str
    excerpt: str
    line_start: int | None = None
    line_end: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MinutesEvidence":
        return cls(**data)


@dataclass
class AgendaTopic:
    topic_id: str
    title: str
    meeting_date: str
    item_number: int | None = None
    topic_kind: str = "agenda"
    agenda_document: SourceRef | None = None
    minutes_documents: list[SourceRef] = field(default_factory=list)
    minutes_evidence: list[MinutesEvidence] = field(default_factory=list)
    discussed_people: list[str] = field(default_factory=list)
    relevance_score: float = 0.0
    verification_status: str = "possible"
    verification_reason: str = ""
    candidate_sources: list[str] = field(default_factory=list)
    summary: str = ""
    summary_source_doc_ids: list[str] = field(default_factory=list)
    summary_source_files: list[str] = field(default_factory=list)
    summary_generated_at: str = ""
    summary_status: str = "not_requested"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgendaTopic":
        payload = dict(data)
        agenda = payload.get("agenda_document")
        payload["agenda_document"] = SourceRef.from_dict(agenda) if agenda else None
        payload["minutes_documents"] = [
            SourceRef.from_dict(value) for value in payload.get("minutes_documents", [])
        ]
        payload["minutes_evidence"] = [
            MinutesEvidence.from_dict(value) for value in payload.get("minutes_evidence", [])
        ]
        return cls(**payload)


@dataclass
class PersonSummary:
    name: str
    aliases: list[str] = field(default_factory=list)
    topic_ids: list[str] = field(default_factory=list)
    evidence: list[MinutesEvidence] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PersonSummary":
        payload = dict(data)
        payload["evidence"] = [
            MinutesEvidence.from_dict(value) for value in payload.get("evidence", [])
        ]
        return cls(**payload)


@dataclass
class ConversationTurn:
    role: str
    content: str
    inquiry_id: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationTurn":
        return cls(**data)


@dataclass
class Inquiry:
    inquiry_id: str
    session_id: str
    original_question: str
    resolved_question: str
    intent: str
    is_priority_intent: bool = False
    topic: str = ""
    person: str = ""
    aliases: list[str] = field(default_factory=list)
    query_rewrites: list[str] = field(default_factory=list)
    confirmed_topics: list[AgendaTopic] = field(default_factory=list)
    possible_topics: list[AgendaTopic] = field(default_factory=list)
    rejected_topics: list[AgendaTopic] = field(default_factory=list)
    people: list[PersonSummary] = field(default_factory=list)
    sort_order: str = "chronological_desc"
    turns: list[ConversationTurn] = field(default_factory=list)
    response: dict[str, Any] = field(default_factory=dict)
    retrieval_audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Inquiry":
        payload = dict(data)
        for key in ("confirmed_topics", "possible_topics", "rejected_topics"):
            payload[key] = [AgendaTopic.from_dict(value) for value in payload.get(key, [])]
        payload["people"] = [PersonSummary.from_dict(value) for value in payload.get("people", [])]
        payload["turns"] = [ConversationTurn.from_dict(value) for value in payload.get("turns", [])]
        return cls(**payload)
