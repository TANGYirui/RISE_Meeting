from types import SimpleNamespace

from rise.inquiry.llm import HKUSTBatchVerifier
from rise.inquiry.models import AgendaTopic


def test_hkust_batch_verifier_returns_structured_decisions():
    message = SimpleNamespace(content='{"decisions":[{"topic_id":"a","status":"confirmed","reason":"direct"}]}')
    response = SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")], usage=None)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response)))
    verifier = HKUSTBatchVerifier(client=client, model="test-model", batch_size=10)

    decisions = verifier.verify_many([AgendaTopic("a", "Fees", "2024-01-01")], "fees")

    assert decisions["a"] == {"status": "confirmed", "reason": "direct"}
