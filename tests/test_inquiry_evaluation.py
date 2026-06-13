from rise.inquiry.evaluation import evaluate_inquiry


def test_evaluation_reports_confirmed_possible_and_minutes_recall():
    metrics = evaluate_inquiry(
        confirmed_topic_ids={"a"},
        possible_topic_ids={"b"},
        minutes_doc_ids={"m1"},
        gold_topic_ids={"a", "b"},
        gold_minutes_doc_ids={"m1", "m2"},
    )
    assert metrics["confirmed_topic_recall"] == 0.5
    assert metrics["confirmed_plus_possible_topic_recall"] == 1.0
    assert metrics["minutes_evidence_recall"] == 0.5
