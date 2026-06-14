from pathlib import Path

from fastapi.testclient import TestClient

from rise.inquiry.service import InquiryService
from rise.inquiry.source_pdfs import SourcePdfResolver
from rise.inquiry.store import InquiryStore
from services.frontend.app.main import create_app


def test_api_serves_inquiry_static_frontend_and_original_pdf(tmp_path: Path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "Item3.pdf").write_bytes(b"%PDF")
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "item3.txt").write_text("tuition fees", encoding="utf-8")
    manifest = {
        "item3": {
            "doc_id": "item3", "filename": "Item3.pdf", "role": "agenda_item",
            "meeting_date": "2024-05-09", "item_number": 3, "title": "Fees", "relpath": "item3.txt",
        }
    }
    service = InquiryService(
        manifest, {}, corpus, lambda query, depth: [("item3", 1.0)],
        InquiryStore(tmp_path / "state.sqlite"),
        verifier=lambda topic, question: {"status": "confirmed", "reason": "match"},
    )
    client = TestClient(create_app(service, SourcePdfResolver(raw, manifest)))

    assert client.get("/api/health").json()["status"] == "ok"
    response = client.post("/api/inquiries", json={"session_id": "s", "question": "Retrieve all papers on fees"})
    assert response.status_code == 200
    assert response.json()["response"]["verified_count"] == 1
    assert client.get("/").status_code == 200
    frontend = client.get("/").text
    assert "RISE Meeting" in frontend
    assert 'id="chat-transcript"' in frontend
    assert 'id="chat-composer"' in frontend
    assert "Accuracy-first UAC inquiry" not in frontend
    assert "Ask across complete UAC agenda papers" not in frontend
    frontend_js = client.get("/static/js/app.js").text
    assert 'event.key === "Enter"' in frontend_js
    assert "!event.shiftKey" in frontend_js
    assert '<details class="supporting-results">' in frontend_js
    assert '<details class="supporting-results" open>' not in frontend_js
    assert "Summarize next ${Math.min(10, pendingSummaries)} results" in frontend_js
    assert client.get("/api/sources/item3/pdf").content == b"%PDF"
    inquiry_id = response.json()["inquiry_id"]
    summary = client.post(f"/api/inquiries/{inquiry_id}/continue-summaries")
    assert summary.status_code == 200
    assert summary.json()["inquiry"]["confirmed_topics"][0]["summary_status"] == "completed"


def test_stream_endpoint_emits_status_and_result(tmp_path: Path):
    service = InquiryService({}, {}, tmp_path, lambda query, depth: [], InquiryStore(tmp_path / "state.sqlite"))
    client = TestClient(create_app(service, None))
    response = client.post("/api/inquiries/stream", json={"session_id": "s", "question": "General question"})
    assert response.status_code == 200
    assert "event: status" in response.text
    assert "event: result" in response.text
