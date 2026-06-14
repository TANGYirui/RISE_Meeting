"""Normalize and aggregate people across verified AgendaTopics."""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from .models import AgendaTopic, MinutesEvidence, PersonSummary, SourceRef


ACTIVE_VERBS = re.compile(
    r"\b(?:ask(?:ed|s)?|comment(?:ed|s)?|discuss(?:ed|es)?|explain(?:ed|s)?|"
    r"introduc(?:ed|es)?|present(?:ed|s)?|propos(?:ed|es)?|report(?:ed|s)?|"
    r"suggest(?:ed|s)?|clarif(?:ied|ies)?|express(?:ed|es)?|respond(?:ed|s)?|"
    r"recommend(?:ed|s)?|tabled|raised|highlight(?:ed|s)?|shared|enquired|"
    r"briefed|supplemented|reaffirmed|elaborated|led|"
    r"noted|gave\s+an?\s+update|spoke|talk(?:ed|s)?)\b",
    re.I,
)
ATTENDANCE_ONLY = re.compile(
    r"\b(?:apologies?|absence|absent|represented\s+by|attendance|present:)\b",
    re.I,
)
ROLE_PATTERN = re.compile(
    r"\b(?:Associate\s+Dean(?:,\s*[^,|;\n.]{1,80})?|"
    r"Dean(?:,\s*[^,|;\n.]{1,80})?|"
    r"Chair\s+Professor(?:,\s*[^,|;\n.]{1,80})?|Senate\s+Representative|"
    r"AVP-[A-Z-]+|(?:Acting\s+)?(?:Associate\s+)?Vice-President"
    r"(?:\s+for\s+[^,|;\n.]{1,80}|,\s*[^,|;\n.]{1,80})?|"
    r"President(?:\s+\(Designate\))?(?:,\s*Chair)?|Provost|"
    r"Director(?:,\s*[^,|;\n.]{1,80})?)"
    r"(?=\s+(?:Professor|Prof\.?|Dr|Mr|Mrs|Ms)\b|[,|;\n.]|$)",
    re.I,
)
PROFILE_ROLES = {"agenda_item", "minutes"}
ROLE_KEYWORDS = re.compile(
    r"\b(?:President|Provost|Vice-President|VP[-A-Z]*|VPRD|VPAB|Dean|"
    r"Chair|Director|Representative|Head|Officer|Professor)\b",
    re.I,
)


def normalize_person(name: str) -> str:
    return re.sub(r"^(?:prof(?:essor)?|dr|mr|mrs|ms)\.?\s+", "", name.strip(), flags=re.I)


def extract_person_name(question: str) -> str:
    """Extract a person name from common profile-question forms."""
    value = question.strip().strip("?.!。？ ")
    patterns = [
        r"(?i)^who\s+is\s+(.+)$",
        r"(?i)^what\s+(?:roles?|positions?)\s+(?:has|does|did)\s+(.+?)(?:\s+hold|\s+have)?$",
        r"^(.+?)\s*(?:是谁|是誰)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, value)
        if match:
            return normalize_person(match.group(1).strip())
    return ""


def build_person_aliases(name: str) -> list[str]:
    """Generate conservative aliases suitable for complete exact scans."""
    canonical = normalize_person(name)
    if not canonical:
        return []
    aliases = [canonical]
    parts = canonical.split()
    if len(parts) == 3:
        first, middle, last = parts
        aliases.extend(
            [
                f"{last} {first} {middle}",
                f"{first}-{middle} {last}",
                f"{first[0]}. {middle[0]}. {last}",
                f"{first[0]} {middle[0]} {last}",
            ]
        )
    return list(dict.fromkeys(aliases))


def _matching_lines(text: str, aliases: list[str]) -> list[str]:
    lowered = [alias.casefold() for alias in aliases]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return [line for line in lines if any(alias in line.casefold() for alias in lowered)]


def _alias_windows(line: str, aliases: list[str], radius: int = 240) -> list[str]:
    folded = line.casefold()
    windows = []
    for alias in aliases:
        start = folded.find(alias.casefold())
        if start >= 0:
            windows.append(line[max(0, start - radius): start + len(alias) + radius])
    return windows


def _active_excerpt(line: str, aliases: list[str]) -> str:
    folded = line.casefold()
    for alias in aliases:
        start = folded.find(alias.casefold())
        if start < 0:
            continue
        end = start + len(alias)
        after = line[end:end + 220]
        before = line[max(0, start - 100):start]
        local = line[max(0, start - 120):end + 220]
        direct = ACTIVE_VERBS.search(after)
        bridge = after[:direct.start()] if direct else ""
        borrowed_action = bool(
            re.search(r"[;•.]", bridge)
            or re.search(r"\b(?:Professor|Prof\.?|Dr|Mr|Mrs|Ms)\b", bridge, flags=re.I)
            or re.search(r"\b[A-Z]\s+[A-Z]\s+[A-Z][a-z]+\b", bridge)
            or re.search(r"\band\s+[A-Z]", bridge)
        )
        passive = re.search(
            r"\b(?:presented|introduced|explained|reported|proposed|suggested|"
            r"commented|asked|clarified|discussed|tabled|raised|highlighted)\s+by\s+"
            r"(?:Professor|Prof\.?)?\s*$",
            before,
            flags=re.I,
        )
        if (
            (direct and direct.start() <= 160 and not borrowed_action or passive)
            and not ATTENDANCE_ONLY.search(local)
        ):
            return line[max(0, start - 120):end + 240].strip()
    return ""


def _clean_role(role: str) -> str:
    role = re.sub(r"\s+", " ", role).strip(" ,|")
    role = re.sub(r"\s*\|\s*$", "", role).strip()
    role = re.sub(r"\s+effective\s+from\b.*$", "", role, flags=re.I).strip(" ,")
    if role.endswith(")") and "(" not in role:
        role = role[:-1].rstrip()
    return re.sub(r",\s*", ", ", role)


def _valid_role(role: str) -> bool:
    return bool(
        role
        and len(role) <= 120
        and ROLE_KEYWORDS.search(role)
        and not re.search(r"\b(?:Professor|Prof\.?|Dr|Mr|Mrs|Ms)\b", role, flags=re.I)
        and not re.search(r"\b(?:reported|presented|introduced|discussed|expressed)\b", role, flags=re.I)
        and not role.lower().startswith("then ")
        and "representing " not in role.lower()
        and "summary for " not in role.lower()
    )


def _subject_bound_roles(line: str, aliases: list[str]) -> list[str]:
    """Extract roles attached to the named subject, never a nearby other person."""
    folded = line.casefold()
    roles: list[str] = []

    if "|" in line:
        cells = [cell.strip() for cell in line.split("|")]
        for index, cell in enumerate(cells):
            if any(alias.casefold() in cell.casefold() for alias in aliases):
                for candidate in cells[index + 1:index + 2]:
                    role = _clean_role(candidate)
                    if _valid_role(role):
                        roles.append(role)

    for alias in aliases:
        position = folded.find(alias.casefold())
        if position < 0:
            continue
        escaped = re.escape(line[position:position + len(alias)])
        honorific_name = rf"(?:Professor|Prof\.?|Dr|Mr|Mrs|Ms)?\s*{escaped}"
        patterns = [
            rf"{honorific_name}\s+has\s+been\s+appointed\s+as\s+(.+?)(?=\s+effective\b|[.;]|$)",
            rf"{honorific_name}\s*,\s*(.+?)(?=,\s*(?:reported|presented|briefed|"
            rf"supplemented|asked|commented|noted|expressed)\b|[.;]|$)",
            rf"({ROLE_PATTERN.pattern})\s+(?:Professor|Prof\.?|Dr|Mr|Mrs|Ms)\s+{escaped}",
        ]
        for pattern in patterns:
            match = re.search(pattern, line, flags=re.I)
            if not match:
                continue
            role = _clean_role(match.group(1))
            if _valid_role(role):
                roles.append(role)
    return list(dict.fromkeys(role for role in roles if role))


def analyze_person_documents(
    name: str,
    document_manifest: dict[str, dict],
    corpus_root: Path,
) -> dict:
    """Audit every document mentioning a person and classify the evidence."""
    aliases = build_person_aliases(name)
    active_mentions: list[dict] = []
    active_doc_ids: list[str] = []
    attendance_only_doc_ids: list[str] = []
    mention_doc_ids: list[str] = []
    roles: dict[str, dict] = {}
    role_facts: list[dict] = []

    for doc_id, record in document_manifest.items():
        if record.get("role") not in PROFILE_ROLES:
            continue
        relpath = record.get("relpath")
        path = Path(corpus_root) / relpath if relpath else None
        if not path or not path.is_file():
            continue
        lines = _matching_lines(path.read_text(encoding="utf-8", errors="replace"), aliases)
        if not lines:
            continue
        mention_doc_ids.append(doc_id)
        is_active = False
        for line in lines:
            for role in _subject_bound_roles(line, aliases):
                role_key = role.casefold()
                entry = roles.setdefault(role_key, {"role": role, "years": [], "doc_ids": []})
                year = str(record.get("meeting_date", ""))[:4]
                if year and year not in entry["years"]:
                    entry["years"].append(year)
                if doc_id not in entry["doc_ids"]:
                    entry["doc_ids"].append(doc_id)
                role_facts.append(
                    {
                        "role": role,
                        "meeting_date": record.get("meeting_date", ""),
                        "doc_id": doc_id,
                        "filename": record.get("filename", ""),
                    }
                )
            active_excerpt = _active_excerpt(line, aliases)
            if active_excerpt:
                is_active = True
                active_mentions.append(
                    {
                        "doc_id": doc_id,
                        "filename": record.get("filename", ""),
                        "meeting_date": record.get("meeting_date", ""),
                        "excerpt": active_excerpt,
                    }
                )
        if is_active:
            active_doc_ids.append(doc_id)
        else:
            attendance_only_doc_ids.append(doc_id)

    for entry in roles.values():
        entry["years"].sort()
        entry["doc_ids"].sort()
    role_list = sorted(
        roles.values(), key=lambda value: (value["years"][-1] if value["years"] else "", value["role"])
    )
    active_mentions.sort(key=lambda value: value.get("meeting_date", ""), reverse=True)
    role_facts.sort(
        key=lambda value: (value.get("meeting_date", ""), len(value.get("role", ""))),
        reverse=True,
    )
    return {
        "name": name,
        "aliases": aliases,
        "mention_doc_count": len(mention_doc_ids),
        "mention_doc_ids": sorted(mention_doc_ids),
        "active_doc_ids": sorted(active_doc_ids),
        "attendance_only_doc_ids": sorted(attendance_only_doc_ids),
        "active_mentions": active_mentions,
        "roles": role_list,
        "current_role": role_facts[0] if role_facts else None,
    }


def topic_has_active_person_evidence(
    topic: AgendaTopic,
    aliases: list[str],
    texts: dict[str, str],
) -> bool:
    """Return true only when a topic contains a named person's active participation."""
    lowered = [alias.casefold() for alias in aliases]
    passages = [evidence.excerpt for evidence in topic.minutes_evidence]
    if topic.agenda_document:
        passages.append(texts.get(topic.agenda_document.doc_id, ""))
    for passage in passages:
        for line in passage.splitlines():
            folded = line.casefold()
            if any(alias in folded for alias in lowered) and _active_excerpt(line, aliases):
                return True
    return False


def ensure_active_person_topics(
    topics: list[AgendaTopic],
    person_profile: dict,
    document_manifest: dict[str, dict],
) -> list[AgendaTopic]:
    """Preserve active-person evidence even when legacy Minutes headings cannot be parsed."""
    represented = {
        doc_id
        for topic in topics
        for doc_id in topic.candidate_sources
    }
    first_mentions = {
        mention["doc_id"]: mention
        for mention in person_profile.get("active_mentions", [])
    }
    for doc_id in person_profile.get("active_doc_ids", []):
        if doc_id in represented:
            continue
        record = document_manifest.get(doc_id, {})
        mention = first_mentions.get(doc_id, {})
        source = SourceRef(doc_id, record.get("filename", ""), record.get("role", ""))
        evidence = MinutesEvidence(
            doc_id,
            record.get("filename", ""),
            mention.get("excerpt", ""),
        )
        topics.append(
            AgendaTopic(
                topic_id=f"person-evidence:{doc_id}",
                title=record.get("title") or record.get("filename", doc_id),
                meeting_date=record.get("meeting_date", ""),
                topic_kind="person_evidence",
                agenda_document=source if record.get("role") == "agenda_item" else None,
                minutes_documents=[source] if record.get("role") == "minutes" else [],
                minutes_evidence=[evidence],
                candidate_sources=[doc_id],
            )
        )
    return sorted(topics, key=lambda topic: (topic.meeting_date, topic.topic_id))


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


PERSON_ACTION = re.compile(
    r"\b(?:Professor|Prof\.?|Dr|Mr|Mrs|Ms)\s+"
    r"([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){1,3})"
    r"(?:,\s*[^.;]{0,120})?\s+"
    r"(?:asked|briefed|commented|discussed|explained|expressed|introduced|"
    r"noted|presented|proposed|reported|supplemented|tabled)\b",
    re.I,
)


def extract_active_people(topics: Iterable[AgendaTopic]) -> list[PersonSummary]:
    """Extract active speakers from verified evidence using subject-bound actions."""
    grouped: dict[str, PersonSummary] = {}
    for topic in topics:
        passages = [evidence.excerpt for evidence in topic.minutes_evidence]
        for passage in passages:
            for match in PERSON_ACTION.finditer(passage):
                name = normalize_person(match.group(1))
                key = name.casefold()
                summary = grouped.setdefault(key, PersonSummary(name))
                if topic.topic_id not in summary.topic_ids:
                    summary.topic_ids.append(topic.topic_id)
                summary.evidence.extend(topic.minutes_evidence)
    return sorted(grouped.values(), key=lambda value: value.name.casefold())
