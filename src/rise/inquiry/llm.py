"""HKUST GenAI structured verification for candidate AgendaTopics."""
from __future__ import annotations

import json
from typing import Iterable

from rise.api_retry import chat_with_retry
from rise.decompose import _extract_json, make_client, resolve_model

from .models import AgendaTopic


VERIFY_PROMPT = """You verify whether UAC meeting agenda topics are relevant to a user inquiry.
Use the title and official Minutes evidence. Return JSON only:
{"decisions":[{"topic_id":"...","status":"confirmed|possible|rejected","reason":"short evidence-based reason"}]}
Confirmed requires direct topical evidence. Possible preserves ambiguous candidates. Never silently omit a topic."""


class HKUSTBatchVerifier:
    def __init__(self, *, client=None, model: str | None = None, batch_size: int = 20):
        self.model = model or resolve_model()
        self.client = client or make_client(self.model)
        self.batch_size = batch_size

    def verify_many(self, topics: list[AgendaTopic], question: str) -> dict[str, dict]:
        decisions: dict[str, dict] = {}
        for offset in range(0, len(topics), self.batch_size):
            batch = topics[offset:offset + self.batch_size]
            payload = [
                {
                    "topic_id": topic.topic_id,
                    "title": topic.title,
                    "meeting_date": topic.meeting_date,
                    "minutes_evidence": [evidence.excerpt[:800] for evidence in topic.minutes_evidence[:3]],
                }
                for topic in batch
            ]
            try:
                response = chat_with_retry(
                    self.client,
                    model=self.model,
                    messages=[
                        {"role": "system", "content": VERIFY_PROMPT},
                        {"role": "user", "content": f"INQUIRY:\n{question}\n\nCANDIDATES:\n{json.dumps(payload, ensure_ascii=False)}"},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0,
                    max_tokens=4096,
                )
                data = _extract_json(response.choices[0].message.content or "{}")
                for decision in data.get("decisions", []):
                    topic_id = decision.get("topic_id")
                    if topic_id:
                        decisions[topic_id] = {
                            "status": decision.get("status", "possible"),
                            "reason": decision.get("reason", ""),
                        }
            except Exception as exc:
                for topic in batch:
                    decisions[topic.topic_id] = {
                        "status": "possible",
                        "reason": f"HKUST verification unavailable: {exc}",
                    }
        return decisions
