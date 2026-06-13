from rise.inquiry.topics import assemble_topics


def test_agenda_and_official_minutes_are_merged_and_auxiliary_docs_are_hidden():
    manifest = {
        "item3": {
            "doc_id": "item3", "filename": "Item3_Tuition.pdf", "role": "agenda_item",
            "meeting_date": "2024-05-09", "item_number": 3, "title": "Tuition Fees",
        },
        "minutes": {
            "doc_id": "minutes", "filename": "Minutes_240509.pdf", "role": "minutes",
            "meeting_date": "2024-05-09", "item_number": None, "title": "",
        },
        "toc": {
            "doc_id": "toc", "filename": "TableOfContents.pdf", "role": "table_of_contents",
            "meeting_date": "2024-05-09", "item_number": None, "title": "",
        },
    }
    texts = {"minutes": "Item 3 Tuition Fees\nNancy Ip presented the proposed adjustment."}

    topics = assemble_topics({"item3", "minutes", "toc"}, manifest, texts)

    assert len(topics) == 1
    assert topics[0].topic_id == "2024-05-09:item3"
    assert topics[0].agenda_document.doc_id == "item3"
    assert topics[0].minutes_documents[0].doc_id == "minutes"
    assert "Nancy Ip" in topics[0].minutes_evidence[0].excerpt


def test_unpaired_minutes_section_becomes_minutes_only_topic():
    manifest = {
        "minutes": {
            "doc_id": "minutes", "filename": "Minutes_240509.pdf", "role": "minutes",
            "meeting_date": "2024-05-09", "item_number": None, "title": "",
        },
    }
    topics = assemble_topics({"minutes"}, manifest, {"minutes": "Item 9 New matter\nA decision was recorded."})
    assert topics[0].topic_kind == "minutes_only"
    assert topics[0].item_number == 9


def test_minutes_candidate_pairs_matching_agenda_even_when_agenda_was_not_retrieved():
    manifest = {
        "item9": {
            "doc_id": "item9", "filename": "Item9.pdf", "role": "agenda_item",
            "meeting_date": "2024-05-09", "item_number": 9, "title": "New matter",
        },
        "minutes": {
            "doc_id": "minutes", "filename": "Minutes.pdf", "role": "minutes",
            "meeting_date": "2024-05-09", "item_number": None, "title": "",
        },
    }
    topics = assemble_topics({"minutes"}, manifest, {"minutes": "Item 9 New matter\nDecision recorded."})
    assert topics[0].topic_kind == "agenda"
    assert topics[0].agenda_document.doc_id == "item9"
