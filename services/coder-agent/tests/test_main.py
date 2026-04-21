"""Tests for FastAPI routes."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_ok(app_client: TestClient) -> None:
    resp = app_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_chat_empty_prompt_rejected(app_client: TestClient) -> None:
    resp = app_client.post("/chat", json={"prompt": ""})
    assert resp.status_code == 422


def test_chat_missing_prompt_rejected(app_client: TestClient) -> None:
    resp = app_client.post("/chat", json={})
    assert resp.status_code == 422


def test_chat_happy_path(app_client: TestClient) -> None:
    resp = app_client.post("/chat", json={"prompt": "write a hello world"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["output"].startswith("echo:")
    assert len(body["request_id"]) > 0


def test_chat_request_id_preserved(app_client: TestClient) -> None:
    resp = app_client.post("/chat", json={"prompt": "test", "request_id": "rid-123"})
    assert resp.status_code == 200
    assert resp.json()["request_id"] == "rid-123"


def test_ready_reports_model_server_unreachable(app_client: TestClient) -> None:
    # conftest wires MODEL_SERVER_URL to a fake host that won't resolve
    resp = app_client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_server_reachable"] is False
    assert body["status"] == "degraded"
