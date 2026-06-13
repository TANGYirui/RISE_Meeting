from rise.inquiry.models import AgendaTopic
from rise.inquiry.verification import verify_topics


def test_verifier_groups_topics_and_keeps_failures_possible():
    topics = [
        AgendaTopic("a", "A", "2024-01-01"),
        AgendaTopic("b", "B", "2024-01-01"),
        AgendaTopic("c", "C", "2024-01-01"),
    ]

    def verifier(topic, question):
        if topic.topic_id == "a":
            return {"status": "confirmed", "reason": "direct evidence"}
        if topic.topic_id == "b":
            return {"status": "rejected", "reason": "unrelated"}
        raise RuntimeError("temporary API failure")

    result = verify_topics(topics, "question", verifier)
    assert [topic.topic_id for topic in result.confirmed] == ["a"]
    assert [topic.topic_id for topic in result.possible] == ["c"]
    assert [topic.topic_id for topic in result.rejected] == ["b"]
