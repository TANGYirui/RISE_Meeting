"""Conservative inquiry intent and follow-up resolution."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from .models import ConversationTurn


PRIORITY_INTENTS = {
    "topic_discussion",
    "retrieve_topics",
    "people_by_topic",
    "person_topic_check",
}


@dataclass(frozen=True)
class IntentResult:
    intent: str
    is_priority_intent: bool


@dataclass(frozen=True)
class FollowUpResult:
    is_follow_up: bool


def classify_inquiry(question: str) -> IntentResult:
    normalized = " ".join(question.lower().split())
    if re.search(r"\bwho\b.*\b(discuss|talk|present)", normalized):
        intent = "people_by_topic"
    elif re.search(r"\b(did|does|has|have)\b.+\b(discuss|talk|present)", normalized):
        intent = "person_topic_check"
    elif re.search(r"\b(retrieve|list|find|show)\b.*\b(all|papers?|agenda|topics?)\b", normalized):
        intent = "retrieve_topics"
    elif re.search(r"\b(is there|any)\b.*\b(discussion|discussed|discussion on)\b", normalized):
        intent = "topic_discussion"
    else:
        intent = "general_inquiry"
    return IntentResult(intent, intent in PRIORITY_INTENTS)


def resolve_follow_up(question: str, recent_turns: Sequence[ConversationTurn]) -> FollowUpResult:
    normalized = " ".join(question.lower().split()).strip("?.! ")
    controls = {
        "continue",
        "continue summarizing",
        "continue summary",
        "show more",
        "summarize next",
        "sort by relevance",
        "sort by date",
    }
    return FollowUpResult(bool(recent_turns) and normalized in controls)

