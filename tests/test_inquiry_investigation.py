from rise.inquiry.investigation import InvestigationResult
from rise.inquiry.service import InquiryService
from rise.inquiry.store import InquiryStore


def test_service_merges_rise_investigation_candidates_and_audit(tmp_path):
    manifest = {
        "item": {
            "doc_id": "item", "filename": "Item1.pdf", "role": "agenda_item",
            "meeting_date": "2024-01-01", "item_number": 1, "title": "Topic",
            "relpath": "item.txt",
        }
    }
    (tmp_path / "item.txt").write_text("topic", encoding="utf-8")
    service = InquiryService(
        manifest, {}, tmp_path, lambda query, depth: [], InquiryStore(tmp_path / "db.sqlite"),
        verifier=lambda topic, question: {"status": "confirmed", "reason": "agent evidence"},
        investigator=lambda question: InvestigationResult(
            {"item"}, {"final_text": "Agent found the topic", "queries": ["topic alias"]}
        ),
    )

    inquiry = service.create_inquiry("s", "Explain the topic")

    assert inquiry.confirmed_topics[0].topic_id == "2024-01-01:item1"
    assert inquiry.retrieval_audit["rise_investigation"]["final_text"] == "Agent found the topic"
