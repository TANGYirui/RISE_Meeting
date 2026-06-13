from rise.inquiry.models import AgendaTopic
from rise.inquiry.summaries import next_summary_batch


def test_summary_batch_skips_completed_topics():
    topics = [
        AgendaTopic("a", "A", "2024-01-01", summary_status="completed"),
        AgendaTopic("b", "B", "2024-01-01"),
        AgendaTopic("c", "C", "2024-01-01"),
    ]
    batch, remaining = next_summary_batch(topics, batch_size=1)
    assert [topic.topic_id for topic in batch] == ["b"]
    assert remaining == 1
