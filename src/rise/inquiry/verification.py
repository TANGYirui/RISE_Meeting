"""Structured candidate verification and confidence grouping."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from .models import AgendaTopic


@dataclass
class VerificationResult:
    confirmed: list[AgendaTopic] = field(default_factory=list)
    possible: list[AgendaTopic] = field(default_factory=list)
    rejected: list[AgendaTopic] = field(default_factory=list)


def verify_topics(
    topics: Iterable[AgendaTopic],
    question: str,
    verifier: Callable[[AgendaTopic, str], dict],
) -> VerificationResult:
    result = VerificationResult()
    topics = list(topics)
    batch_decisions = verifier.verify_many(topics, question) if hasattr(verifier, "verify_many") else None
    for topic in topics:
        try:
            decision = batch_decisions.get(topic.topic_id, {}) if batch_decisions is not None else verifier(topic, question)
            status = decision.get("status", "possible")
            reason = decision.get("reason", "")
        except Exception as exc:
            status = "possible"
            reason = f"Verification unavailable: {exc}"
        if status not in {"confirmed", "possible", "rejected"}:
            status = "possible"
        topic.verification_status = status
        topic.verification_reason = reason
        getattr(result, status).append(topic)
    return result
