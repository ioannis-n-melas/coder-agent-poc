"""Live-GPU contract tests — the OpenAI-compatible surface from ADR-0001.

These hit an actual vLLM server. They are skipped unless ``MODEL_SERVER_URL``
is set, so they are safe to run on a laptop without a GPU. CI should run them
in the deploy-gate job after devops-engineer builds & pushes the image and
boots a Cloud Run revision behind an authenticated URL.

The three assertions below are the ADR-0001 contract:
  1. GET /health returns 200 when the model is ready to serve.
  2. GET /v1/models lists the served model id by the name the agent addresses.
  3. POST /v1/chat/completions accepts an OpenAI-shaped request and returns
     an OpenAI-shaped response (id, choices, usage).

If any of these break, the agent breaks — that's the whole reason we own an
OpenAI-compatible contract rather than a bespoke RPC shape.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.gpu


def test_health_returns_200_when_ready(live_client: httpx.Client) -> None:
    resp = live_client.get("/health")
    # vLLM's /health returns 200 with an empty body once the engine has loaded
    # weights and is accepting requests. Anything else means we are not ready.
    assert resp.status_code == 200, resp.text


def test_models_endpoint_lists_served_model(
    live_client: httpx.Client, served_model_name: str
) -> None:
    resp = live_client.get("/v1/models")
    assert resp.status_code == 200, resp.text

    body = resp.json()
    # OpenAI-compatible shape: {"object": "list", "data": [{"id": "...", ...}]}
    assert body.get("object") == "list"
    ids = [m["id"] for m in body["data"]]
    assert served_model_name in ids, (
        f"served model '{served_model_name}' not in /v1/models: {ids}"
    )


def test_chat_completions_happy_path(
    live_client: httpx.Client, served_model_name: str
) -> None:
    """Non-streaming: the simplest end-to-end assertion.

    A small max_tokens keeps the test fast and cheap. We don't assert on the
    exact text (model output is non-deterministic); we assert on the OpenAI
    response shape — that's the contract.
    """
    resp = live_client.post(
        "/v1/chat/completions",
        json={
            "model": served_model_name,
            "messages": [{"role": "user", "content": "Reply with the single word: OK"}],
            "max_tokens": 8,
            "temperature": 0.0,
        },
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == served_model_name
    assert len(body["choices"]) >= 1

    choice = body["choices"][0]
    assert choice["message"]["role"] == "assistant"
    assert isinstance(choice["message"]["content"], str)
    assert len(choice["message"]["content"]) > 0


def test_chat_completions_streaming(
    live_client: httpx.Client, served_model_name: str
) -> None:
    """Streaming SSE — the path coder-agent actually uses in production.

    We don't assert on content; we assert that the server speaks the OpenAI
    SSE dialect (chunks are JSON-per-line, last line is [DONE]).
    """
    with live_client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": served_model_name,
            "messages": [{"role": "user", "content": "Say hi."}],
            "max_tokens": 8,
            "temperature": 0.0,
            "stream": True,
        },
    ) as resp:
        assert resp.status_code == 200, resp.read()

        saw_chunk = False
        saw_done = False
        for line in resp.iter_lines():
            if not line:
                continue
            if not line.startswith("data: "):
                continue
            payload = line[len("data: ") :]
            if payload == "[DONE]":
                saw_done = True
                break
            # Every non-DONE data line must be valid JSON per the OpenAI spec.
            import json

            chunk = json.loads(payload)
            assert chunk.get("object") == "chat.completion.chunk"
            saw_chunk = True

    assert saw_chunk, "no streaming chunks received"
    assert saw_done, "stream ended without [DONE] sentinel"
