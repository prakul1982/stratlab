"""Scanned PDFs read by the AI services' OCR: Mistral first, Gemini next, each only with its key."""
import json

import httpx
import pytest

from app import ocr
from app.config import settings


def test_mistral_then_gemini(monkeypatch):
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "m")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "g")
    monkeypatch.setattr("app.ai_writer._candidates", lambda: ["gemini-2.5-flash"])
    monkeypatch.setattr(ocr.time, "sleep", lambda s: None)
    state = {"mistral": 200}
    sent = []

    def handler(r):
        sent.append(r.url.host)
        if r.url.host == "api.mistral.ai":
            body = json.loads(r.content)
            assert body["document"]["document_url"].startswith("data:application/pdf;base64,") and r.headers["authorization"] == "Bearer m"
            if state["mistral"] != 200:
                return httpx.Response(state["mistral"], json={"message": "rate limited"})
            return httpx.Response(200, json={"pages": [{"index": 0, "markdown": "Page one"}, {"index": 1, "markdown": "Page two"}]})
        body = json.loads(r.content)
        assert body["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "application/pdf"
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "Gemini read it"}]}}]})
    http = httpx.Client(transport=httpx.MockTransport(handler))
    assert ocr.read_pdf(b"%PDF-1.4 scan", http) == "Page one\n\nPage two" and sent == ["api.mistral.ai"]
    state["mistral"] = 429
    assert ocr.read_pdf(b"%PDF-1.4 scan", http) == "Gemini read it"
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    with pytest.raises(ocr.OCRError, match="Mistral OCR: 429"):
        ocr.read_pdf(b"%PDF-1.4 scan", http)
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "")
    assert not ocr.available() and ocr.read_pdf(b"%PDF", http) == ""
