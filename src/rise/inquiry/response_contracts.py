"""Complete response contracts shared by priority and general inquiries."""
from __future__ import annotations

from typing import Any, Sequence
import re


PRIORITY_CONTRACTS = {
    "topic_discussion": "topic_inventory",
    "retrieve_topics": "topic_inventory",
    "people_by_topic": "people_summary",
    "person_topic_check": "person_topic_verdict",
    "person_profile": "person_profile",
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
    rise_final_text: str = "",
) -> dict[str, Any]:
    """Build the mandatory complete envelope for every inquiry response."""
    rise_answer = parse_rise_final_text(rise_final_text)
    return {
        "contract": contract,
        "conclusion": rise_answer["exact_answer"] or conclusion,
        "result_summary": conclusion,
        "answer_explanation": rise_answer["explanation"],
        "answer_confidence": rise_answer["confidence"],
        "answer_source": "rise_investigation" if rise_answer["exact_answer"] else "verified_results",
        "verified_count": len(confirmed),
        "possible_count": len(possible),
        "searched_scope": searched_scope,
        "confirmed_results": list(confirmed),
        "possible_results": list(possible),
        "evidence": list(evidence),
        "actions": list(actions),
        "retrieval_audit": dict(audit),
    }


def parse_rise_final_text(text: str) -> dict[str, str]:
    """Parse the stable RISE final-answer format without trusting it as verification."""
    text = (text or "").strip()
    explanation = re.search(
        r"Explanation:\s*(.*?)(?=\s*Exact Answer:|\s*Confidence:|\Z)",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    exact = re.search(
        r"Exact Answer:\s*(.*?)(?=\s*Confidence:|\Z)",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    confidence = re.search(r"Confidence:\s*([^\r\n]+)", text, flags=re.IGNORECASE)
    return {
        "explanation": explanation.group(1).strip() if explanation else "",
        "exact_answer": exact.group(1).strip() if exact else "",
        "confidence": confidence.group(1).strip() if confidence else "",
    }
