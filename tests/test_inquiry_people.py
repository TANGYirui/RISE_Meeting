from rise.inquiry.models import AgendaTopic, MinutesEvidence
from rise.inquiry.people import aggregate_people


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
