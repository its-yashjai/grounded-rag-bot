"""
Integration tests exercising the API through FastAPI's TestClient. These run
against the real ingestion/retrieval pipeline; only the outbound Groq network
call is mocked (see conftest.py), since no live network is available in CI/
this sandbox — swap the mock for a real GROQ_API_KEY to test the live call.
"""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.llm.base import LLMChunk

client = TestClient(app)


async def _fake_stream(self, system_prompt, user_prompt, temperature=0.2, max_tokens=1024, fast=False):
    for word in ["This ", "is ", "a ", "grounded ", "answer."]:
        yield LLMChunk(delta=word)
    yield LLMChunk(delta="", finished=True, input_tokens=100, output_tokens=5)


def _upload_sample():
    content = (
        b"Post-harvest losses are caused by inadequate storage, poor transport, "
        b"pest infestations, and lack of access to markets. Proper handling, "
        b"storage facilities, and timely transportation can reduce these losses.")
    return client.post(
        "/api/v1/documents/upload",
        files={"files": ("sample.txt", content, "text/plain")},
    )


def test_health_live():
    r = client.get("/api/v1/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_upload_rejects_unsupported_type():
    r = client.post(
        "/api/v1/documents/upload",
        files={"files": ("sample.exe", b"binary", "application/octet-stream")},
    )
    assert r.status_code == 400


def test_upload_and_list():
    r = _upload_sample()
    assert r.status_code == 200
    doc = r.json()["documents"][0]
    assert doc["processing_status"] == "ready"
    assert doc["chunk_count"] >= 1

    r2 = client.get("/api/v1/documents")
    assert r2.status_code == 200
    assert any(d["document_id"] == doc["document_id"] for d in r2.json())


def test_duplicate_upload_is_deduped():
    r1 = _upload_sample()
    r2 = _upload_sample()
    id1 = r1.json()["documents"][0]["document_id"]
    id2 = r2.json()["documents"][0]["document_id"]
    assert id1 == id2  # same content hash -> same document, not reprocessed


def test_chat_stream_returns_citations_and_tokens():
    _upload_sample()
    with patch("app.services.llm.groq_service.GroqProvider.stream_chat", _fake_stream):
        r = client.post("/api/v1/chat/stream", json={"message": "What causes post-harvest losses?"})
    assert r.status_code == 200
    assert "event: citations" in r.text
    assert "event: token" in r.text
    assert "event: done" in r.text


def test_metrics_summary_reflects_state():
    _upload_sample()
    r = client.get("/api/v1/metrics/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["documents"] >= 1
    assert "cache_hit_rate" in body
