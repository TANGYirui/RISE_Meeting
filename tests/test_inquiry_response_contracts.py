from rise.inquiry.response_contracts import build_response, select_response_contract


def test_general_questions_select_adaptive_contracts():
    assert select_response_contract("general_inquiry", "Compare A and B") == "comparison"
    assert select_response_contract("general_inquiry", "How did tuition fees change over time?") == "chronological_history"
    assert select_response_contract("general_inquiry", "Explain the evidence about governance") == "evidence_synthesis"


def test_every_response_has_complete_shared_fields():
    response = build_response(
        contract="evidence_synthesis",
        conclusion="The records show recurring discussion.",
        searched_scope="All indexed UAC agenda papers and official Minutes",
        confirmed=[{"topic_id": "one", "sources": [{"source_url": "/api/sources/one/pdf"}]}],
        possible=[],
        evidence=[{"topic_id": "one", "excerpt": "Discussion evidence"}],
        actions=["Generate summaries"],
        audit={"queries": ["governance"]},
    )

    assert response["conclusion"]
    assert response["verified_count"] == 1
    assert response["searched_scope"]
    assert response["confirmed_results"]
    assert "possible_results" in response
    assert response["evidence"]
    assert response["actions"]
    assert response["retrieval_audit"]
