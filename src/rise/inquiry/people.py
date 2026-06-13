"""Normalize and aggregate people across verified AgendaTopics."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

from .models import AgendaTopic, PersonSummary


def normalize_person(name: str) -> str:
    return re.sub(r"^(?:prof(?:essor)?|dr|mr|mrs|ms)\.?\s+", "", name.strip(), flags=re.I)


def aggregate_people(topics: Iterable[AgendaTopic]) -> list[PersonSummary]:
    grouped: dict[str, PersonSummary] = {}
    aliases: dict[str, set[str]] = defaultdict(set)
    for topic in topics:
        for raw_name in topic.discussed_people:
            name = normalize_person(raw_name)
            key = name.casefold()
            aliases[key].add(raw_name)
            summary = grouped.setdefault(key, PersonSummary(name))
            if topic.topic_id not in summary.topic_ids:
                summary.topic_ids.append(topic.topic_id)
            summary.evidence.extend(topic.minutes_evidence)
    for key, summary in grouped.items():
        summary.aliases = sorted(aliases[key])
    return sorted(grouped.values(), key=lambda value: value.name.casefold())

