from rise.inquiry.models import AgendaTopic, ConversationTurn, Inquiry, SourceRef


def test_inquiry_round_trip_preserves_topics_sources_and_turns():
    topic = AgendaTopic(
        topic_id="2024-05-09:item3",
        title="Tuition fees",
        meeting_date="2024-05-09",
        item_number=3,
        agenda_document=SourceRef("item3", "Item3_Tuition_Fees_20240509.pdf"),
        summary_source_doc_ids=["item3", "minutes_240509"],
    )
    inquiry = Inquiry(
        inquiry_id="inq-1",
        session_id="session-1",
        original_question="Retrieve all papers on tuition fees",
        resolved_question="Retrieve all UAC agenda topics on tuition fees",
        intent="retrieve_topics",
        confirmed_topics=[topic],
        sort_order="chronological_desc",
        turns=[ConversationTurn("user", "Retrieve all papers on tuition fees")],
    )

    restored = Inquiry.from_dict(inquiry.to_dict())

    assert restored.confirmed_topics[0].topic_id == "2024-05-09:item3"
    assert restored.confirmed_topics[0].agenda_document.doc_id == "item3"
    assert restored.confirmed_topics[0].summary_source_doc_ids == ["item3", "minutes_240509"]
    assert restored.sort_order == "chronological_desc"
    assert len(restored.turns) == 1
