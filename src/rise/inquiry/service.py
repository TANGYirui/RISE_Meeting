"""Application orchestration for structured meeting inquiries."""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from rise.retrieval import load_index, retrieve
from rise.uac_workspace import related_doc_ids

from .discovery import discover_candidates
from .intents import classify_inquiry, extract_topic
from .investigation import RiseInvestigator
from .llm import HKUSTBatchVerifier
from .models import ConversationTurn, Inquiry
from .people import (
    aggregate_people,
    analyze_person_documents,
    build_person_aliases,
    ensure_active_person_topics,
    extract_person_name,
    topic_has_active_person_evidence,
)
from .response_contracts import build_response, select_response_contract
from .store import InquiryStore
from .summaries import next_summary_batch
from .topics import assemble_topics
from .verification import verify_topics


def _default_verifier(topic, question: str) -> dict:
    terms = {term.casefold() for term in re.findall(r"[A-Za-z][A-Za-z-]{3,}", question)}
    haystack = " ".join(
        [topic.title, *(evidence.excerpt for evidence in topic.minutes_evidence)]
    ).casefold()
    matched = sorted(term for term in terms if term in haystack)
    if matched:
        return {"status": "confirmed", "reason": f"Matched verified evidence terms: {', '.join(matched[:8])}"}
    return {"status": "possible", "reason": "Retrieved by BM25 but requires semantic verification"}


class InquiryService:
    def __init__(
        self,
        document_manifest: dict[str, dict],
        meeting_manifest: dict[str, dict[str, list[str]]],
        corpus_root: Path,
        retrieve_fn: Callable[[str, int], list[tuple[str, float]]],
        store: InquiryStore,
        *,
        verifier: Callable | None = None,
        investigator: Callable | None = None,
        discovery_depth: int = 500,
    ):
        self.document_manifest = document_manifest
        self.meeting_manifest = meeting_manifest
        self.corpus_root = Path(corpus_root)
        self.retrieve_fn = retrieve_fn
        self.store = store
        self.verifier = verifier or _default_verifier
        self.investigator = investigator
        self.discovery_depth = discovery_depth

    def _texts(self, doc_ids: set[str]) -> dict[str, str]:
        texts: dict[str, str] = {}
        for doc_id in doc_ids:
            record = self.document_manifest.get(doc_id, {})
            relpath = record.get("relpath")
            if relpath and (self.corpus_root / relpath).is_file():
                texts[doc_id] = (self.corpus_root / relpath).read_text(
                    encoding="utf-8", errors="replace"
                )
        return texts

    def create_inquiry(self, session_id: str, question: str) -> Inquiry:
        classified = classify_inquiry(question)
        person_name = extract_person_name(question) if classified.intent == "person_profile" else ""
        aliases = build_person_aliases(person_name)
        topic_query = extract_topic(question, classified.intent)
        queries = aliases or list(
            dict.fromkeys([question, topic_query] if topic_query else [question])
        )
        discovery = discover_candidates(
            queries,
            [] if person_name else ([topic_query] if topic_query else [question]),
            self.retrieve_fn,
            self.document_manifest,
            self.corpus_root,
            depth=self.discovery_depth,
        )
        expanded = set(discovery.doc_ids)
        person_profile = None
        if person_name:
            person_profile = analyze_person_documents(
                person_name, self.document_manifest, self.corpus_root
            )
            expanded = set(person_profile["active_doc_ids"])
        investigation_audit = {}
        if self.investigator is not None:
            investigation = self.investigator(question)
            expanded.update(investigation.doc_ids)
            investigation_audit = investigation.audit
        if not person_name:
            expanded.update(
                related_doc_ids(
                    list(expanded),
                    self.document_manifest,
                    self.meeting_manifest,
                    cap=100,
                )
            )
        texts = self._texts(expanded)
        topics = assemble_topics(expanded, self.document_manifest, texts)
        if person_name:
            topics = [
                topic
                for topic in topics
                if topic_has_active_person_evidence(topic, aliases, texts)
            ]
            topics = ensure_active_person_topics(
                topics, person_profile, self.document_manifest
            )
        for topic in topics:
            topic.relevance_score = max(
                (discovery.scores.get(doc_id, 0.0) for doc_id in topic.candidate_sources),
                default=0.0,
            )
            for source in [topic.agenda_document, *topic.minutes_documents]:
                if source:
                    source.source_url = f"/api/sources/{source.doc_id}/pdf"
                    source.has_source_pdf = True
        if person_name:
            for topic in topics:
                topic.verification_status = "confirmed"
                topic.verification_reason = (
                    f"Confirmed active participation by {person_name} in the source text."
                )
            verified = type(
                "PersonVerification",
                (),
                {"confirmed": topics, "possible": [], "rejected": []},
            )()
        else:
            verified = verify_topics(topics, question, self.verifier)
        people = aggregate_people(verified.confirmed)
        contract = select_response_contract(classified.intent, question)
        confirmed_payload = [topic.__dict__ | {"agenda_document": topic.agenda_document.__dict__ if topic.agenda_document else None} for topic in verified.confirmed]
        possible_payload = [topic.__dict__ | {"agenda_document": topic.agenda_document.__dict__ if topic.agenda_document else None} for topic in verified.possible]
        response = build_response(
            contract=contract,
            conclusion=self._conclusion(question, len(verified.confirmed), len(verified.possible)),
            searched_scope="All indexed UAC agenda papers and official Minutes",
            confirmed=confirmed_payload,
            possible=possible_payload,
            evidence=[
                evidence.__dict__
                for topic in [*verified.confirmed, *verified.possible]
                for evidence in topic.minutes_evidence
            ],
            actions=["Generate summaries", "Show possible results", "Inspect retrieval audit"],
            rise_final_text=investigation_audit.get("final_text", ""),
            audit={
                "queries": discovery.queries,
                "candidate_doc_count": len(expanded),
                "candidate_sources": discovery.sources,
                "rise_investigation": investigation_audit,
            },
        )
        if person_profile is not None:
            roles = person_profile["roles"]
            if roles:
                response["conclusion"] = f"{person_name}: {roles[-1]['role']}."
            response["answer_explanation"] = (
                f"Found {person_profile['mention_doc_count']} documents mentioning {person_name}; "
                f"{len(person_profile['active_doc_ids'])} contain active participation."
            )
            response["answer_source"] = "complete_person_scan"
            response["person_profile"] = {
                **person_profile,
                "active_doc_count": len(person_profile["active_doc_ids"]),
                "attendance_only_doc_count": len(person_profile["attendance_only_doc_ids"]),
            }
            response["retrieval_audit"]["person_scan"] = {
                "aliases": aliases,
                "mention_doc_count": person_profile["mention_doc_count"],
                "active_doc_count": len(person_profile["active_doc_ids"]),
                "attendance_only_doc_count": len(person_profile["attendance_only_doc_ids"]),
            }
        inquiry = Inquiry(
            inquiry_id=uuid.uuid4().hex,
            session_id=session_id,
            original_question=question,
            resolved_question=question,
            intent=classified.intent,
            is_priority_intent=classified.is_priority_intent,
            person=person_name,
            topic=topic_query,
            aliases=aliases,
            query_rewrites=queries,
            confirmed_topics=verified.confirmed,
            possible_topics=verified.possible,
            rejected_topics=verified.rejected,
            people=people,
            response=response,
            retrieval_audit=response["retrieval_audit"],
        )
        self.store.save_inquiry(inquiry)
        self.store.append_turn(session_id, ConversationTurn("user", question, inquiry.inquiry_id))
        self.store.append_turn(
            session_id, ConversationTurn("assistant", response["conclusion"], inquiry.inquiry_id)
        )
        return inquiry

    @staticmethod
    def _conclusion(question: str, confirmed: int, possible: int) -> str:
        return (
            f"Found {confirmed} confirmed UAC agenda topics for this inquiry"
            f" and {possible} possible topics requiring inspection."
        )

    def get_inquiry(self, inquiry_id: str) -> Inquiry | None:
        return self.store.get_inquiry(inquiry_id)

    def set_sort(self, inquiry_id: str, sort_order: str) -> Inquiry:
        inquiry = self.store.get_inquiry(inquiry_id)
        if inquiry is None:
            raise KeyError(inquiry_id)
        if sort_order not in {"relevance", "chronological_desc"}:
            raise ValueError(sort_order)
        inquiry.sort_order = sort_order
        if sort_order == "relevance":
            inquiry.confirmed_topics.sort(key=lambda topic: topic.relevance_score, reverse=True)
        else:
            inquiry.confirmed_topics.sort(key=lambda topic: topic.meeting_date, reverse=True)
        self.store.save_inquiry(inquiry)
        return inquiry

    def generate_next_summaries(
        self, inquiry_id: str, *, batch_size: int = 10
    ) -> tuple[Inquiry, int]:
        inquiry = self.store.get_inquiry(inquiry_id)
        if inquiry is None:
            raise KeyError(inquiry_id)
        batch, remaining = next_summary_batch(inquiry.confirmed_topics, batch_size=batch_size)
        for topic in batch:
            sources = [source for source in [topic.agenda_document, *topic.minutes_documents] if source]
            evidence = " ".join(value.excerpt for value in topic.minutes_evidence).strip()
            evidence_sentences = [
                sentence.strip()
                for sentence in re.split(r"(?<=[.!?])\s+", evidence)
                if sentence.strip()
            ][:2]
            detail = " ".join(evidence_sentences) if evidence_sentences else "No matching official Minutes passage was identified."
            topic.summary = (
                f"This UAC agenda topic is titled {topic.title} and was discussed on {topic.meeting_date}. "
                f"The retrieved agenda paper and meeting records identify it as relevant to the inquiry. "
                f"{detail}"
            )
            topic.summary_source_doc_ids = [source.doc_id for source in sources]
            topic.summary_source_files = [source.filename for source in sources]
            topic.summary_generated_at = datetime.now(timezone.utc).isoformat()
            topic.summary_status = "completed"
        self.store.save_inquiry(inquiry)
        return inquiry, remaining

    def reset_session(self, session_id: str) -> None:
        self.store.reset_session(session_id)


def build_service_from_env(repo_root: Path | None = None) -> InquiryService:
    root = Path(repo_root or Path.cwd())
    corpus_root = root / os.getenv("RISE_CORPUS_DIR", "runs/uac_corpus/files")
    bm25_root = root / os.getenv("RISE_BM25_DIR", "runs/uac_bm25")
    document_path = root / os.getenv(
        "RISE_DOCUMENT_MANIFEST", "runs/uac_corpus/document_manifest.json"
    )
    meeting_path = root / os.getenv(
        "RISE_MEETING_MANIFEST", "runs/uac_corpus/meeting_manifest.json"
    )
    db_path = root / os.getenv("RISE_INQUIRY_DB", "result/inquiry_app.sqlite")
    documents = json.loads(document_path.read_text(encoding="utf-8"))
    meetings = json.loads(meeting_path.read_text(encoding="utf-8"))
    retriever, doc_ids = load_index(bm25_root)
    filename_path = root / os.getenv(
        "RISE_FILENAME_MAP", "runs/uac_corpus/filename_docid_map.json"
    )
    relpath_to_docid = json.loads(filename_path.read_text(encoding="utf-8"))["relpath_to_docid"]
    docid_to_relpath = {doc_id: relpath for relpath, doc_id in relpath_to_docid.items()}
    related = lambda hits: related_doc_ids(hits, documents, meetings, cap=100)
    investigator = RiseInvestigator(
        retriever=retriever,
        doc_ids=doc_ids,
        docid_to_relpath=docid_to_relpath,
        corpus_root=corpus_root,
        result_root=root / "result" / "inquiry_agent",
        related_doc_ids_fn=related,
        max_model_calls=int(os.getenv("RISE_INQUIRY_AGENT_MAX_CALLS", "20")),
    )
    return InquiryService(
        documents,
        meetings,
        corpus_root,
        lambda query, depth: retrieve(retriever, doc_ids, query, k=depth),
        InquiryStore(db_path, memory_window=int(os.getenv("RISE_INQUIRY_MEMORY_WINDOW", "10"))),
        verifier=HKUSTBatchVerifier(
            batch_size=int(os.getenv("RISE_INQUIRY_VERIFY_BATCH_SIZE", "20"))
        ),
        investigator=investigator,
    )
