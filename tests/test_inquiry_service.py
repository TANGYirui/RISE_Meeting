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
