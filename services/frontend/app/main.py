"""FastAPI entry point for the RISE Meeting inquiry frontend."""
from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

from rise.inquiry.service import InquiryService, build_service_from_env
from rise.inquiry.source_pdfs import SourcePdfResolver


REPO_ROOT = Path(__file__).resolve().parents[3]
STATIC_ROOT = Path(__file__).resolve().parent / "static"


class InquiryRequest(BaseModel):
    session_id: str
    question: str


class SortRequest(BaseModel):
    sort_order: str


def create_app(
    service: InquiryService | None = None,
    resolver: SourcePdfResolver | None = None,
) -> FastAPI:
    app = FastAPI(title="RISE Meeting", version="0.1.0")
    app.state.service = service
    app.state.resolver = resolver

    def require_service() -> InquiryService:
        if app.state.service is None:
            raise HTTPException(503, "Inquiry assets are not loaded")
        return app.state.service

    @app.get("/api/health")
    def health():
        return {"status": "ok" if app.state.service is not None else "degraded"}

    @app.post("/api/inquiries")
    def create_inquiry(request: InquiryRequest):
        return require_service().create_inquiry(request.session_id, request.question).to_dict()

    @app.post("/api/inquiries/stream")
    def create_inquiry_stream(request: InquiryRequest):
        def events():
            yield "event: status\ndata: " + json.dumps({"phase": "retrieve", "message": "Searching complete UAC documents..."}) + "\n\n"
            inquiry = require_service().create_inquiry(request.session_id, request.question)
            yield "event: result\ndata: " + json.dumps(inquiry.to_dict(), ensure_ascii=False) + "\n\n"
        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/api/inquiries/{inquiry_id}")
    def get_inquiry(inquiry_id: str):
        inquiry = require_service().get_inquiry(inquiry_id)
        if inquiry is None:
            raise HTTPException(404, "Inquiry not found")
        return inquiry.to_dict()

    @app.patch("/api/inquiries/{inquiry_id}/sort")
    def set_sort(inquiry_id: str, request: SortRequest):
        try:
            return require_service().set_sort(inquiry_id, request.sort_order).to_dict()
        except KeyError as exc:
            raise HTTPException(404, "Inquiry not found") from exc
        except ValueError as exc:
            raise HTTPException(400, "Invalid sort order") from exc

    @app.post("/api/sessions/{session_id}/reset")
    def reset_session(session_id: str):
        require_service().reset_session(session_id)
        return {"status": "reset"}

    @app.post("/api/inquiries/{inquiry_id}/continue-summaries")
    def continue_summaries(inquiry_id: str):
        try:
            inquiry, remaining = require_service().generate_next_summaries(inquiry_id)
        except KeyError as exc:
            raise HTTPException(404, "Inquiry not found") from exc
        return {"inquiry": inquiry.to_dict(), "remaining": remaining}

    @app.get("/api/sources/{doc_id}/pdf")
    def source_pdf(doc_id: str):
        if app.state.resolver is None:
            raise HTTPException(503, "Original PDF root is not configured")
        try:
            return FileResponse(app.state.resolver.resolve(doc_id), media_type="application/pdf")
        except FileNotFoundError as exc:
            raise HTTPException(404, "Original PDF not found") from exc
        except ValueError as exc:
            raise HTTPException(400, "Invalid source") from exc

    @app.get("/", response_class=HTMLResponse)
    def frontend():
        return HTMLResponse((STATIC_ROOT / "index.html").read_text(encoding="utf-8"))

    @app.get("/static/{asset_path:path}")
    def static_asset(asset_path: str):
        path = (STATIC_ROOT / asset_path).resolve()
        try:
            path.relative_to(STATIC_ROOT.resolve())
        except ValueError as exc:
            raise HTTPException(400, "Invalid asset path") from exc
        if not path.is_file():
            raise HTTPException(404, "Asset not found")
        return FileResponse(path)

    return app


def _default_app() -> FastAPI:
    load_dotenv(REPO_ROOT / ".env")
    try:
        service = build_service_from_env(REPO_ROOT)
    except Exception:
        service = None
    resolver = None
    if service is not None:
        try:
            resolver = SourcePdfResolver.from_env(service.document_manifest)
        except Exception:
            pass
    return create_app(service, resolver)


app = _default_app()
