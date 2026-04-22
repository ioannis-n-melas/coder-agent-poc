"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from coder_agent.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    """Settings with a fake model server URL."""
    return Settings(model_server_url="http://fake-model-server:8080")  # type: ignore[call-arg]


@pytest.fixture
def env_model_server(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Set the MODEL_SERVER_URL env var for tests that import get_settings()."""
    monkeypatch.setenv("MODEL_SERVER_URL", "http://fake-model-server:8080")
    yield


@pytest.fixture
def app_client(env_model_server: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """FastAPI test client with the agent build stubbed out.

    We replace build_agent so tests don't need a running model-server.
    The stub returns a fake DeepAgentWrapper-shaped object whose ainvoke
    echoes the prompt — same shape DeepAgentWrapper provides.
    """

    class _FakeAgent:
        async def ainvoke(self, payload: dict[str, Any]) -> dict[str, Any]:
            # Support both BaseMessage objects and role/content dicts.
            messages = payload.get("messages", [])
            last = messages[-1] if messages else {}
            content = getattr(last, "content", None) or (
                last.get("content", "") if isinstance(last, dict) else ""
            )
            return {"messages": [{"role": "assistant", "content": f"echo: {content}"}]}

    def _fake_build(_settings: Settings) -> _FakeAgent:
        return _FakeAgent()

    monkeypatch.setattr("coder_agent.agent.build_agent", _fake_build)
    monkeypatch.setattr("coder_agent.main.build_agent", _fake_build)

    from coder_agent.main import app

    with TestClient(app) as client:
        yield client
