from rise.inquiry.models import AgendaTopic, MinutesEvidence
from rise.inquiry.people import (
    aggregate_people,
    analyze_person_documents,
    build_person_aliases,
    extract_person_name,
)


def test_people_are_normalized_and_aggregated_across_topics():
    topics = [
        AgendaTopic(
            "a", "Fees", "2024-01-01", discussed_people=["Prof. Nancy Ip"],
            minutes_evidence=[MinutesEvidence("m1", "m1.pdf", "Prof. Nancy Ip presented fees")],
        ),
        AgendaTopic("b", "IT", "2025-01-01", discussed_people=["Nancy Ip"]),
    ]
    people = aggregate_people(topics)
    assert len(people) == 1
    assert people[0].name == "Nancy Ip"
    assert people[0].topic_ids == ["a", "b"]
    assert people[0].evidence[0].doc_id == "m1"


def test_person_name_and_aliases_cover_historical_name_orderings():
    name = extract_person_name("Who is Kar Yan Tam?")
    aliases = build_person_aliases(name)

    assert name == "Kar Yan Tam"
    assert {"Kar Yan Tam", "Tam Kar Yan", "Kar-Yan Tam", "K. Y. Tam", "K Y Tam"} <= set(aliases)


def test_person_document_analysis_separates_roles_participation_and_attendance(tmp_path):
    manifest = {
        "old": {
            "doc_id": "old", "filename": "minutes_old.pdf", "role": "minutes",
            "meeting_date": "2001-08-06", "relpath": "old.txt",
        },
        "absence": {
            "doc_id": "absence", "filename": "minutes_absence.pdf", "role": "minutes",
            "meeting_date": "2018-01-16", "relpath": "absence.txt",
        },
        "discussion": {
            "doc_id": "discussion", "filename": "minutes_discussion.pdf", "role": "minutes",
            "meeting_date": "2019-02-15", "relpath": "discussion.txt",
        },
    }
    (tmp_path / "old.txt").write_text(
        "Kar-Yan Tam, Associate Dean, School of Business and Management", encoding="utf-8"
    )
    (tmp_path / "absence.txt").write_text(
        "Professor Kar Yan Tam sent apologies for absence.", encoding="utf-8"
    )
    (tmp_path / "discussion.txt").write_text(
        "Professor Kar Yan Tam commented on the proposed financial management system.",
        encoding="utf-8",
    )

    result = analyze_person_documents("Kar Yan Tam", manifest, tmp_path)

    assert result["mention_doc_count"] == 3
    assert result["active_doc_ids"] == ["discussion"]
    assert result["attendance_only_doc_ids"] == ["absence", "old"]
    assert result["roles"] == [
        {
            "role": "Associate Dean, School of Business and Management",
            "years": ["2001"],
            "doc_ids": ["old"],
        }
    ]
    assert result["active_mentions"][0]["excerpt"].startswith("Professor Kar Yan Tam commented")


def test_person_profile_active_mentions_are_newest_first(tmp_path):
    manifest = {
        "old": {
            "doc_id": "old", "filename": "old.pdf", "role": "minutes",
            "meeting_date": "1995-01-01", "relpath": "old.txt",
        },
        "new": {
            "doc_id": "new", "filename": "new.pdf", "role": "minutes",
            "meeting_date": "2025-01-01", "relpath": "new.txt",
        },
    }
    (tmp_path / "old.txt").write_text("Professor Nancy Ip presented the old paper.", encoding="utf-8")
    (tmp_path / "new.txt").write_text(
        "| Professor Nancy Ip | Vice-President for Administration & Business |\n"
        "Professor Nancy Ip, Vice-President for Administration & Business, reported the new paper.",
        encoding="utf-8",
    )

    result = analyze_person_documents("Nancy Ip", manifest, tmp_path)

    assert [item["meeting_date"] for item in result["active_mentions"]] == [
        "2025-01-01", "1995-01-01"
    ]
    assert result["roles"][-1]["role"] == "Vice-President for Administration & Business"
    assert result["roles"][-1]["years"] == ["2025"]


def test_person_action_is_not_borrowed_from_another_subject_later_in_the_line(tmp_path):
    manifest = {
        "appointment": {
            "doc_id": "appointment", "filename": "appointment.pdf", "role": "minutes",
            "meeting_date": "2025-01-01", "relpath": "appointment.txt",
        },
        "group": {
            "doc_id": "group", "filename": "group.pdf", "role": "minutes",
            "meeting_date": "2002-01-01", "relpath": "group.txt",
        },
    }
    (tmp_path / "appointment.txt").write_text(
        "Prof Kar-Yan Tam as Acting Vice President; and Dr Eunice Cheng as Director. "
        "The Chair expressed a vote of thanks.",
        encoding="utf-8",
    )
    (tmp_path / "group.txt").write_text(
        "A working group (K Y Tam, S Y Cheng, and Angelina Prof Tu Yee) was expected to report.",
        encoding="utf-8",
    )

    result = analyze_person_documents("Kar Yan Tam", manifest, tmp_path)

    assert result["active_doc_ids"] == []
