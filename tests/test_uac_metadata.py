from rise.uac_metadata import disambiguate_doc_ids, parse_uac_filename


def test_parse_official_minutes():
    meta = parse_uac_filename("Minutes_250109.pdf")
    assert meta.role == "minutes"
    assert meta.meeting_date == "2025-01-09"
    assert meta.item_number is None


def test_parse_draft_minutes_as_distinct_role():
    meta = parse_uac_filename(
        "Item1_Draft_Minutes_of_the_Meeting_on_11_January_2024_20240509.pdf"
    )
    assert meta.role == "draft_minutes"
    assert meta.meeting_date == "2024-05-09"
    assert meta.item_number == 1


def test_parse_agenda_item_and_table_of_contents():
    item = parse_uac_filename("ItemV_Strategic_Plan_20240509.pdf")
    toc = parse_uac_filename("TableOfContents_20240509.pdf")
    assert (item.role, item.item_number, item.meeting_date) == (
        "agenda_item",
        5,
        "2024-05-09",
    )
    assert toc.role == "table_of_contents"
    assert toc.meeting_date == "2024-05-09"


def test_parse_circulation_and_invalid_name():
    circulation = parse_uac_filename("240805_uac_paper_via_circulation.pdf")
    assert circulation.role == "circulation"
    assert circulation.meeting_date == "2024-08-05"
    assert parse_uac_filename("unrecognized.pdf") is None


def test_parse_circulation_with_zero_day_normalizes_to_first_day():
    circulation = parse_uac_filename("110300_uac_paper_via_circulation.pdf")
    assert circulation.meeting_date == "2011-03-01"


def test_parse_circulation_with_underscored_date():
    circulation = parse_uac_filename("1301_03_uac_paper_via_circulation.pdf")
    assert circulation.meeting_date == "2013-01-03"
    assert circulation.role == "circulation"


def test_disambiguate_doc_ids_changes_only_colliding_documents():
    first = parse_uac_filename("Item3_Personal Data Privacy Policy_20150505.pdf")
    second = parse_uac_filename("Item3_Personal_Data_Privacy_Policy_20150505.pdf")
    unique = parse_uac_filename("Minutes_150505.pdf")

    resolved = disambiguate_doc_ids([first, second, unique])

    assert resolved[0].doc_id != resolved[1].doc_id
    assert resolved[0].doc_id.startswith(first.doc_id + "_")
    assert resolved[1].doc_id.startswith(second.doc_id + "_")
    assert resolved[2].doc_id == unique.doc_id
