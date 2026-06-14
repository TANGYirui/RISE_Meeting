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
    "person_profile",
}


@dataclass(frozen=True)
class IntentResult:
    intent: str
    is_priority_intent: bool


@dataclass(frozen=True)
class FollowUpResult:
    is_follow_up: bool


@dataclass(frozen=True)
class ContextResolution:
    resolved_question: str
    used_memory: bool
    subject: str = ""


def classify_inquiry(question: str) -> IntentResult:
    normalized = " ".join(question.lower().split())
    if re.search(r"^\s*who\s+is\s+.+[?.!]?\s*$", normalized) or re.search(
        r".+\s*(?:是谁|是誰)[？?]?\s*$", question
    ):
        intent = "person_profile"
    elif re.search(r"\bwhat\s+topics?\b.*\b(discuss|talk|present)", normalized) or re.search(
        r"\btopics?\s+about\s+.+", normalized
    ):
        intent = "person_topics"
    elif re.search(r"\bwho\b.*\b(discuss|talk|present)", normalized):
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


def extract_topic(question: str, intent: str) -> str:
    """Extract the literal topic phrase used for high-recall full-corpus scans."""
    value = question.strip().strip("?.!。？ ")
    patterns = {
        "retrieve_topics": [r"(?i)\bon\s+(.+)$", r"(?i)\b(?:about|for)\s+(.+)$"],
        "topic_discussion": [r"(?i)\b(?:discussion|discussed)\s+(?:on|about)\s+(.+)$"],
        "people_by_topic": [r"(?i)\b(?:discussed|talked about|presented)\s+(?:about\s+)?(.+)$"],
        "person_topic_check": [r"(?i)\b(?:discuss|talk about|present)\s+(.+)$"],
    }
    for pattern in patterns.get(intent, []):
        match = re.search(pattern, value)
        if match:
            topic = match.group(1).strip()
            if topic.casefold() not in {"it", "this", "this topic", "that topic"}:
                return topic
    return ""


def _recent_person_subject(recent_turns: Sequence[ConversationTurn]) -> str:
    patterns = [
        r"(?i)^who\s+is\s+([A-Z][A-Za-z-]+(?:\s+[A-Z][A-Za-z-]+){1,3})",
        r"(?i)^what\s+topics?\s+did\s+([A-Z][A-Za-z-]+(?:\s+[A-Z][A-Za-z-]+){1,3})",
        r"(?i)^is\s+there\s+any\s+topics?\s+about\s+([A-Z][A-Za-z-]+(?:\s+[A-Z][A-Za-z-]+){1,3})",
    ]
    for turn in reversed(recent_turns):
        if turn.role != "user":
            continue
        for pattern in patterns:
            match = re.search(pattern, turn.content.strip())
            if match:
                return match.group(1).strip()
    return ""


def resolve_contextual_question(
    question: str,
    recent_turns: Sequence[ConversationTurn],
) -> ContextResolution:
    """Resolve only explicit pronoun follow-ups against bounded session history."""
    subject = _recent_person_subject(recent_turns)
    if not subject or not re.search(r"\b(?:she|he|her|him|they|them)\b", question, flags=re.I):
        return ContextResolution(question, False)
    resolved = re.sub(r"\b(?:she|he|her|him|they|them)\b", subject, question, count=1, flags=re.I)
    return ContextResolution(resolved, True, subject)


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
