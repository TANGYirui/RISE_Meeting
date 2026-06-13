from pathlib import Path
import re

from rise.inquiry.models import ConversationTurn
from rise.inquiry.investigation import InvestigationResult
from rise.inquiry.service import InquiryService
from rise.inquiry.store import InquiryStore


def test_service_builds_complete_general_response_and_reuses_cached_sort(tmp_path: Path):
    manifest = {
        "item3": {
            "doc_id": "item3", "filename": "Item3_Fees.pdf", "role": "agenda_item",
            "meeting_date": "2024-05-09", "item_number": 3, "title": "Tuition Fees",
            "relpath": "item3.txt",
        }
    }
    (tmp_path / "item3.txt").write_text("Tuition fee comparison", encoding="utf-8")
    calls = {"retrieve": 0}

    def retrieve(query, depth):
        calls["retrieve"] += 1
        return [("item3", 2.0)]

    service = InquiryService(
        manifest, {}, tmp_path, retrieve, InquiryStore(tmp_path / "state.sqlite"),
        verifier=lambda topic, question: {"status": "confirmed", "reason": "matched"},
    )

    inquiry = service.create_inquiry("session", "Compare tuition fee proposals")
    service.set_sort(inquiry.inquiry_id, "chronological_desc")

    assert inquiry.response["contract"] == "comparison"
    assert inquiry.response["conclusion"]
    assert inquiry.response["searched_scope"]
    assert inquiry.response["verified_count"] == 1
    assert calls["retrieve"] == 1


def test_unrelated_question_creates_new_inquiry(tmp_path: Path):
    service = InquiryService({}, {}, tmp_path, lambda query, depth: [], InquiryStore(tmp_path / "state.sqlite"))
    first = service.create_inquiry("session", "What is Nancy Ip's role?")
    second = service.create_inquiry("session", "What about ITSO?")
    assert first.inquiry_id != second.inquiry_id
    assert service.store.get_turns("session")[-1] == ConversationTurn("assistant", second.response["conclusion"], second.inquiry_id)


def test_summary_batch_records_source_provenance(tmp_path: Path):
    manifest = {
        "item": {
            "doc_id": "item", "filename": "Item1.pdf", "role": "agenda_item",
            "meeting_date": "2024-01-01", "item_number": 1, "title": "Fees", "relpath": "item.txt",
        }
    }
    (tmp_path / "item.txt").write_text("The proposal adjusts tuition fees. It explains the rationale.", encoding="utf-8")
    service = InquiryService(
        manifest, {}, tmp_path, lambda query, depth: [("item", 1.0)],
        InquiryStore(tmp_path / "db.sqlite"),
        verifier=lambda topic, question: {"status": "confirmed", "reason": "match"},
    )
    inquiry = service.create_inquiry("s", "Retrieve all papers on fees")
    updated, remaining = service.generate_next_summaries(inquiry.inquiry_id, batch_size=1)
    topic = updated.confirmed_topics[0]
    assert topic.summary_status == "completed"
    assert topic.summary_source_doc_ids == ["item"]
    assert topic.summary_source_files == ["Item1.pdf"]
    assert 3 <= len(re.findall(r"(?<=[.!?])\s+", topic.summary.strip())) + 1 <= 4
    assert remaining == 0


def test_rise_answer_is_visible_without_replacing_verified_result_groups(tmp_path: Path):
    service = InquiryService(
        {}, {}, tmp_path, lambda query, depth: [], InquiryStore(tmp_path / "db.sqlite"),
        investigator=lambda question: InvestigationResult(
            set(),
            {
                "final_text": (
                    "Explanation: The Agent found a role description in the corpus.\n"
                    "Exact Answer: Kar Yan Tam is Dean and Chair Professor.\n"
                    "Confidence: 91%"
                )
            },
        ),
    )

    inquiry = service.create_inquiry("s", "Who is Kar Yan Tam?")

    assert inquiry.response["conclusion"] == "Kar Yan Tam is Dean and Chair Professor."
    assert inquiry.response["answer_explanation"]
    assert inquiry.response["verified_count"] == 0


def test_person_profile_uses_alias_full_scan_and_only_confirms_active_participation(tmp_path: Path):
    manifest = {
        "absence": {
            "doc_id": "absence", "filename": "Minutes_absence.pdf", "role": "minutes",
            "meeting_date": "2018-01-16", "relpath": "absence.txt",
        },
        "discussion": {
            "doc_id": "discussion", "filename": "Minutes_discussion.pdf", "role": "minutes",
            "meeting_date": "2019-02-15", "relpath": "discussion.txt",
        },
    }
    (tmp_path / "absence.txt").write_text(
        "Item 1\nProfessor Kar Yan Tam sent apologies for absence.", encoding="utf-8"
    )
    (tmp_path / "discussion.txt").write_text(
        "Item 4\nProfessor Kar-Yan Tam commented on the proposed financial management system.",
        encoding="utf-8",
    )
    queries = []

    def retrieve(query, depth):
        queries.append(query)
        return []

    service = InquiryService(
        manifest, {}, tmp_path, retrieve, InquiryStore(tmp_path / "db.sqlite"),
        verifier=lambda topic, question: {"status": "confirmed", "reason": "LLM said yes"},
        investigator=lambda question: InvestigationResult(set(), {}),
    )

    inquiry = service.create_inquiry("s", "Who is Kar Yan Tam?")

    assert inquiry.intent == "person_profile"
    assert {"Kar Yan Tam", "Tam Kar Yan", "Kar-Yan Tam", "K. Y. Tam", "K Y Tam"} <= set(queries)
    assert [topic.meeting_date for topic in inquiry.confirmed_topics] == ["2019-02-15"]
    assert inquiry.response["person_profile"]["mention_doc_count"] == 2
    assert inquiry.response["person_profile"]["active_doc_count"] == 1


def test_topic_inquiry_exact_scans_extracted_topic_instead_of_whole_question(tmp_path: Path):
    manifest = {
        "fees": {
            "doc_id": "fees", "filename": "Fees.pdf", "role": "agenda_item",
            "meeting_date": "2024-01-01", "item_number": 2, "title": "Fees",
            "relpath": "fees.txt",
        }
    }
    (tmp_path / "fees.txt").write_text("A proposal concerning tuition fees.", encoding="utf-8")
    service = InquiryService(
        manifest, {}, tmp_path, lambda query, depth: [], InquiryStore(tmp_path / "db.sqlite"),
        verifier=lambda topic, question: {"status": "confirmed", "reason": "exact topic phrase"},
    )

    inquiry = service.create_inquiry("s", "Retrieve all UAC papers on tuition fees")

    assert inquiry.topic == "tuition fees"
    assert inquiry.response["verified_count"] == 1
    assert "exact_scan:tuition fees" in inquiry.retrieval_audit["candidate_sources"]["fees"]
