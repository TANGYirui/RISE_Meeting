"""Complete response contracts shared by priority and general inquiries."""
from __future__ import annotations

from typing import Any, Sequence


PRIORITY_CONTRACTS = {
    "topic_discussion": "topic_inventory",
    "retrieve_topics": "topic_inventory",
    "people_by_topic": "people_summary",
    "person_topic_check": "person_topic_verdict",
}


def select_response_contract(intent: str, question: str) -> str:
    if intent in PRIORITY_CONTRACTS:
        return PRIORITY_CONTRACTS[intent]
    normalized = question.lower()
    if any(word in normalized for word in ("compare", "difference", "versus", " vs ")):
        return "comparison"
    if any(word in normalized for word in ("history", "over time", "timeline", "changed", "change over")):
        return "chronological_history"
    return "evidence_synthesis"


def build_response(
    *,
    contract: str,
    conclusion: str,
    searched_scope: str,
    confirmed: Sequence[dict[str, Any]],
    possible: Sequence[dict[str, Any]],
    evidence: Sequence[dict[str, Any]],
    actions: Sequence[str],
    audit: dict[str, Any],
) -> dict[str, Any]:
    """Build the mandatory complete envelope for every inquiry response."""
    return {
        "contract": contract,
        "conclusion": conclusion,
        "verified_count": len(confirmed),
        "possible_count": len(possible),
        "searched_scope": searched_scope,
        "confirmed_results": list(confirmed),
        "possible_results": list(possible),
        "evidence": list(evidence),
        "actions": list(actions),
        "retrieval_audit": dict(audit),
    }

