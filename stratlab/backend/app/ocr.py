"""Text from scanned PDFs (pages that are pictures, with no text layer), read by an AI model that sees the pages.

Some Indian companies file their call transcripts and presentations as scans. Mistral's OCR model is tried first
(made for documents, and part of its free tier), then Google Gemini, which reads PDFs directly. Each is used only
when its key is set. Only the first OCR_PAGES pages are read, to keep within the free quotas."""
import base64
import time

import httpx

from .config import settings

OCR_PAGES = 30
GEMINI_LIMIT = 14 * 1024 * 1024      # Gemini takes up to 20 MB per request inline; base64 adds a third


class OCRError(Exception):
    pass


def available() -> bool:
    return bool(settings.MISTRAL_API_KEY or settings.GEMINI_API_KEY)


def _mistral(data: bytes, http: httpx.Client) -> str:
    r = http.post("https://api.mistral.ai/v1/ocr", timeout=120,
                  headers={"Authorization": f"Bearer {settings.MISTRAL_API_KEY}"},
                  json={"model": "mistral-ocr-latest",
                        "document": {"type": "document_url",
                                     "document_url": "data:application/pdf;base64," + base64.b64encode(data).decode()},
                        "pages": list(range(OCR_PAGES))})
    if r.status_code == 400 and "page" in r.text.lower():     # a short document: the page list runs past its end
        r = http.post("https://api.mistral.ai/v1/ocr", timeout=120,
                      headers={"Authorization": f"Bearer {settings.MISTRAL_API_KEY}"},
                      json={"model": "mistral-ocr-latest",
                            "document": {"type": "document_url",
                                         "document_url": "data:application/pdf;base64," + base64.b64encode(data).decode()}})
    if r.status_code >= 400:
        raise OCRError(f"Mistral OCR: {r.status_code}")
    pages = (r.json() or {}).get("pages") or []
    return "\n\n".join(str(p.get("markdown") or "") for p in pages[:OCR_PAGES])


def _gemini(data: bytes, http: httpx.Client) -> str:
    if len(data) > GEMINI_LIMIT:
        raise OCRError("Gemini: the PDF is too large to send")
    from .ai_writer import _GEMINI_BASE, _candidates
    body = {"contents": [{"role": "user", "parts": [
                {"inline_data": {"mime_type": "application/pdf", "data": base64.b64encode(data).decode()}},
                {"text": f"Transcribe the text of the first {OCR_PAGES} pages of this document exactly as written, "
                         "page by page, keeping numbers and names as they are. Plain text only, no commentary."}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 32768, "thinkingConfig": {"thinkingBudget": 0}}}
    last = "no model"
    for model in _candidates()[:3]:
        r = http.post(f"{_GEMINI_BASE}/models/{model}:generateContent", json=body, timeout=180,
                      headers={"x-goog-api-key": settings.GEMINI_API_KEY})
        if r.status_code == 400 and "thinking" in r.text.lower():
            body["generationConfig"].pop("thinkingConfig", None)
            r = http.post(f"{_GEMINI_BASE}/models/{model}:generateContent", json=body, timeout=180,
                          headers={"x-goog-api-key": settings.GEMINI_API_KEY})
        if r.status_code >= 400:
            last = f"{r.status_code}"
            continue
        try:
            parts = r.json()["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, ValueError, TypeError):
            last = "empty reply"
            continue
        out = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if out.strip():
            return out
        last = "empty reply"
    raise OCRError(f"Gemini: {last}")


def read_pdf(data: bytes, http: httpx.Client | None = None) -> str:
    """The text of a scanned PDF, from the first OCR service that answers; '' when none is set up."""
    http = http or httpx.Client()
    errors = []
    for name, fn, key in (("mistral", _mistral, settings.MISTRAL_API_KEY), ("gemini", _gemini, settings.GEMINI_API_KEY)):
        if not key:
            continue
        try:
            text = fn(data, http)
            if text.strip():
                return text
            errors.append(f"{name}: no text")
        except (OCRError, httpx.HTTPError, ValueError) as e:
            errors.append(str(e)[:80])
            time.sleep(0.2)
    if errors:
        raise OCRError("; ".join(errors))
    return ""
