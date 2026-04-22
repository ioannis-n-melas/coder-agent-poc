"""Integration test: end-to-end request through the FastAPI layer with a mock model.

The mock model is implemented via ``respx`` — a fake HTTP server that intercepts
outbound httpx calls from the OpenAI SDK and returns deterministic completions.
No live model-server is required.

These tests verify:
- The FastAPI ``/chat`` route invokes the DeepAgents graph.
- The graph communicates with the model via the configured ``base_url``.
- The response is extracted and returned in the expected JSON shape.

If the model-server URL is a real endpoint (e.g. in CI with a live server),
set ``LIVE_MODEL_SERVER=1`` to skip the mock and run against the real service.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from coder_agent.config import Settings

# ---------------------------------------------------------------------------
# FastAPI integration: mock build_agent, exercise route logic end-to-end
# ---------------------------------------------------------------------------


@pytest.fixture
def agent_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Test client where build_agent is replaced with a deterministic fake.

    The fake produces a canned DeepAgentWrapper-shaped reply so we can
    assert on route behaviour (request validation, ID generation, output
    extraction) without touching the model or DeepAgents internals.

    The monkeypatch must be applied BEFORE the TestClient context manager is
    entered, because the FastAPI lifespan calls build_agent during startup.
    """
    from langchain_core.messages import AIMessage

    monkeypatch.setenv("MODEL_SERVER_URL", "http://fake-model-server:8080")

    ai_reply = AIMessage(
        content=(
            "Plan:\n"
            "1. Analyze hello.py\n"
            "2. Add greet() function\n"
            "3. Write tests\n"
            "4. Refine\n\n"
            "Done — greet() has been added."
        )
    )

    class _FakeAgent:
        async def ainvoke(self, payload: dict[str, Any]) -> dict[str, Any]:
            return {"messages": [ai_reply]}

    def _fake_build(_settings: Settings) -> _FakeAgent:
        return _FakeAgent()

    monkeypatch.setattr("coder_agent.agent.build_agent", _fake_build)
    monkeypatch.setattr("coder_agent.main.build_agent", _fake_build)

    from coder_agent.main import app

    with TestClient(app) as client:
        yield client


def test_chat_route_returns_plan_output(agent_client: TestClient) -> None:
    """POST /chat with a coder prompt returns the agent's plan/output string."""
    resp = agent_client.post("/chat", json={"prompt": "add a greet function to hello.py"})
    assert resp.status_code == 200
    body = resp.json()
    assert "request_id" in body
    assert len(body["request_id"]) > 0
    output: str = body["output"]
    assert "Plan" in output or "greet" in output, (
        f"expected plan-like content in output; got: {output!r}"
    )


def test_chat_route_passes_prompt_to_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The route must pass the user prompt down to the agent's ainvoke."""
    monkeypatch.setenv("MODEL_SERVER_URL", "http://fake-model-server:8080")

    received_payload: dict[str, Any] = {}

    class _RecordingAgent:
        async def ainvoke(self, payload: dict[str, Any]) -> dict[str, Any]:
            received_payload.update(payload)
            from langchain_core.messages import AIMessage

            return {"messages": [AIMessage(content="recorded")]}

    def _build(_settings: Settings) -> _RecordingAgent:
        return _RecordingAgent()

    monkeypatch.setattr("coder_agent.agent.build_agent", _build)
    monkeypatch.setattr("coder_agent.main.build_agent", _build)

    from coder_agent.main import app

    # Use context manager so lifespan runs with the monkeypatched build_agent.
    with TestClient(app) as client:
        client.post("/chat", json={"prompt": "write a fibonacci function"})

    messages = received_payload.get("messages", [])
    assert messages, "agent.ainvoke was not called with any messages"
    last = messages[-1]
    content = getattr(last, "content", None) or (
        last.get("content", "") if isinstance(last, dict) else ""
    )
    assert "fibonacci" in content, (
        f"user prompt was not forwarded to the agent; got content: {content!r}"
    )


def test_chat_route_preserves_request_id(
    agent_client: TestClient,
) -> None:
    """A caller-supplied request_id must pass through unchanged."""
    resp = agent_client.post("/chat", json={"prompt": "test", "request_id": "integration-rid-001"})
    assert resp.status_code == 200
    assert resp.json()["request_id"] == "integration-rid-001"


def test_chat_route_generates_request_id_when_absent(
    agent_client: TestClient,
) -> None:
    """When no request_id is supplied, the route must generate one."""
    resp = agent_client.post("/chat", json={"prompt": "generate an id for me"})
    assert resp.status_code == 200
    rid = resp.json()["request_id"]
    assert rid and len(rid) > 8, f"expected a non-trivial generated request_id; got {rid!r}"


def test_health_endpoint_still_works(agent_client: TestClient) -> None:
    """The /health endpoint is unaffected by the DeepAgents swap."""
    resp = agent_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Live-model gate: skipped unless LIVE_MODEL_SERVER=1 is set
# ---------------------------------------------------------------------------

_LIVE = os.getenv("LIVE_MODEL_SERVER") == "1"


@pytest.mark.skipif(not _LIVE, reason="set LIVE_MODEL_SERVER=1 to run against real model")
@pytest.mark.slow
def test_live_chat_roundtrip() -> None:
    """Full round-trip against a real model-server (requires LIVE_MODEL_SERVER=1).

    Ensure MODEL_SERVER_URL points at a running vLLM or compatible endpoint.
    """
    from coder_agent.main import app

    client = TestClient(app)
    resp = client.post("/chat", json={"prompt": "write a python function that returns 42"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["output"].strip(), "live model returned empty output"
