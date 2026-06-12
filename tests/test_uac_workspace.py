from rise.uac_workspace import related_doc_ids


def test_item_hit_adds_official_minutes_and_overview_but_not_all_items():
    manifest = {
        "2024-05-09": {
            "minutes": ["minutes_240509"],
            "draft_minutes": ["item1_draft"],
            "agenda_item": ["item5", "item6"],
            "meeting_overview": ["meeting_2024_05_09"],
        }
    }
    docs = {
        "item5": {"meeting_date": "2024-05-09", "role": "agenda_item"},
        "minutes_240509": {"meeting_date": "2024-05-09", "role": "minutes"},
    }

    assert related_doc_ids(["item5"], docs, manifest, cap=5) == [
        "minutes_240509",
        "meeting_2024_05_09",
    ]


def test_overview_hit_adds_official_minutes_only():
    manifest = {
        "2024-05-09": {
            "minutes": ["minutes_240509"],
            "agenda_item": ["item5"],
            "meeting_overview": ["meeting_2024_05_09"],
        }
    }
    docs = {
        "meeting_2024_05_09": {"meeting_date": "2024-05-09", "role": "meeting_overview"}
    }
    assert related_doc_ids(["meeting_2024_05_09"], docs, manifest, cap=5) == ["minutes_240509"]

