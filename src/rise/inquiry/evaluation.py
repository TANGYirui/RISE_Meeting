"""Recall metrics for structured inquiry results."""
from __future__ import annotations

from typing import Iterable


def _recall(found: set[str], gold: set[str]) -> float:
    return len(found & gold) / len(gold) if gold else 0.0


def evaluate_inquiry(
    *,
    confirmed_topic_ids: Iterable[str],
    possible_topic_ids: Iterable[str],
    minutes_doc_ids: Iterable[str],
    gold_topic_ids: Iterable[str],
    gold_minutes_doc_ids: Iterable[str],
) -> dict[str, float]:
    confirmed = set(confirmed_topic_ids)
    possible = set(possible_topic_ids)
    gold_topics = set(gold_topic_ids)
    found_minutes = set(minutes_doc_ids)
    gold_minutes = set(gold_minutes_doc_ids)
    return {
        "confirmed_topic_recall": _recall(confirmed, gold_topics),
        "confirmed_plus_possible_topic_recall": _recall(confirmed | possible, gold_topics),
        "minutes_evidence_recall": _recall(found_minutes, gold_minutes),
        "confirmed_precision": len(confirmed & gold_topics) / len(confirmed) if confirmed else 0.0,
    }

