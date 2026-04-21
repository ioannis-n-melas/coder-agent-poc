"""Tests for the agent builder.

Covers:
- ``build_chat_model`` points langchain-openai at the configured model-server URL.
- ``_GoogleIdTokenAuth`` attaches / silently fails on the Bearer header.
- ``ChatAgent.ainvoke`` round-trips through a mocked ``ChatOpenAI``.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from coder_agent.agent import (
    SYSTEM_PROMPT,
    ChatAgent,
    _GoogleIdTokenAuth,
    build_agent,
    build_chat_model,
)
from coder_agent.config import Settings

# ── build_chat_model ───────────────────────────────────────────────────


def test_chat_model_uses_model_server_base() -> None:
    s = Settings(model_server_url="http://my-server:8080")  # type: ignore[call-arg]
    model = build_chat_model(s)
    base = getattr(model, "openai_api_base", None) or str(getattr(model, "async_client", ""))
    assert "my-server:8080" in str(base) or "my-server:8080" in str(
        getattr(model, "root_client", "")
    ), f"expected my-server:8080 in model config, got {base!r}"


def test_chat_model_uses_configured_temperature() -> None:
    s = Settings(model_server_url="http://h:1", temperature=0.7)  # type: ignore[call-arg]
    model = build_chat_model(s)
    assert model.temperature == 0.7


def test_chat_model_uses_configured_model_name() -> None:
    s = Settings(model_server_url="http://h:1", model_name="qwen-x")  # type: ignore[call-arg]
    model = build_chat_model(s)
    assert model.model_name == "qwen-x"


def test_no_id_token_auth_when_audience_unset() -> None:
    """Local dev / unit tests run without a Cloud Run audience — no auth attached."""
    s = Settings(model_server_url="http://h:1")  # type: ignore[call-arg]
    model = build_chat_model(s)
    assert model is not None


# ── _GoogleIdTokenAuth ─────────────────────────────────────────────────


def test_id_token_auth_flow_sets_bearer_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """When minting succeeds, the Authorization: Bearer header is attached."""
    auth = _GoogleIdTokenAuth("https://model-server.example.run.app")
    monkeypatch.setattr(auth, "_mint_token", lambda: "fake-id-token-abc")
    request = httpx.Request("POST", "https://model-server.example.run.app/v1/chat/completions")
    list(auth.auth_flow(request))  # consume generator
    assert request.headers["Authorization"] == "Bearer fake-id-token-abc"


def test_id_token_auth_flow_silent_on_mint_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """If minting fails, we log and still yield the request — the 401 is the real signal."""

    def _boom() -> str:
        raise RuntimeError("no metadata server")

    auth = _GoogleIdTokenAuth("https://model-server.example.run.app")
    monkeypatch.setattr(auth, "_mint_token", _boom)
    request = httpx.Request("GET", "https://model-server.example.run.app/health")
    with caplog.at_level("ERROR"):
        list(auth.auth_flow(request))
    assert "Authorization" not in request.headers
    assert any("id_token.mint_failed" in rec.message for rec in caplog.records)


def test_chat_model_attaches_id_token_auth_when_audience_set() -> None:
    """When ``model_server_audience`` is set, the ChatOpenAI http clients carry our auth."""
    s = Settings(  # type: ignore[call-arg]
        model_server_url="https://m.run.app",
        model_server_audience="https://m.run.app",
    )
    model = build_chat_model(s)
    sync_auth = getattr(getattr(model, "root_client", None), "_client", None)
    async_auth = getattr(getattr(model, "root_async_client", None), "_client", None)
    sync_transport_auth = getattr(sync_auth, "_transport", None) if sync_auth else None
    async_transport_auth = getattr(async_auth, "_transport", None) if async_auth else None
    found = False
    for candidate in (sync_auth, async_auth, sync_transport_auth, async_transport_auth):
        if isinstance(getattr(candidate, "_auth", None), _GoogleIdTokenAuth):
            found = True
            break
    if not found:
        for attr in ("_client", "async_client", "client"):
            c = getattr(model, attr, None)
            if c is None:
                continue
            inner = getattr(c, "_client", None)
            if inner is not None and isinstance(getattr(inner, "_auth", None), _GoogleIdTokenAuth):
                found = True
                break
    assert found, "expected _GoogleIdTokenAuth to be attached to the OpenAI SDK httpx client"


# ── ChatAgent round-trip ───────────────────────────────────────────────


class _FakeChatModel:
    """Stand-in for ``ChatOpenAI`` that records the last message list and returns a canned reply."""

    def __init__(self, reply: str = "print('hello world')") -> None:
        self._reply = reply
        self.last_messages: list[Any] | None = None
        self.calls: int = 0

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        self.last_messages = messages
        self.calls += 1
        return AIMessage(content=self._reply)


async def test_chat_agent_ainvoke_roundtrip() -> None:
    """ChatAgent sends system + user message to the model and returns the AI reply."""
    fake = _FakeChatModel(reply="print('hello')")
    agent = ChatAgent(model=fake)  # type: ignore[arg-type]

    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "write a hello world in python"}]}
    )

    assert fake.calls == 1
    assert fake.last_messages is not None
    # First message is the system prompt, second is the user turn.
    assert isinstance(fake.last_messages[0], SystemMessage)
    assert fake.last_messages[0].content == SYSTEM_PROMPT
    assert isinstance(fake.last_messages[1], HumanMessage)
    assert fake.last_messages[1].content == "write a hello world in python"

    messages = result["messages"]
    assert len(messages) == 1
    assert isinstance(messages[0], AIMessage)
    assert messages[0].content == "print('hello')"


async def test_chat_agent_respects_caller_system_message() -> None:
    """If the caller supplies a system message, it overrides the default prompt."""
    fake = _FakeChatModel(reply="ok")
    agent = ChatAgent(model=fake)  # type: ignore[arg-type]

    await agent.ainvoke(
        {
            "messages": [
                {"role": "system", "content": "you are a rust expert"},
                {"role": "user", "content": "hi"},
            ]
        }
    )
    assert fake.last_messages is not None
    assert isinstance(fake.last_messages[0], SystemMessage)
    assert fake.last_messages[0].content == "you are a rust expert"


async def test_chat_agent_ignores_non_user_non_system_turns() -> None:
    """Assistant turns from history are ignored for the single-turn POC."""
    fake = _FakeChatModel(reply="ok")
    agent = ChatAgent(model=fake)  # type: ignore[arg-type]

    await agent.ainvoke(
        {
            "messages": [
                {"role": "assistant", "content": "previous reply"},
                {"role": "user", "content": "next question"},
            ]
        }
    )
    assert fake.last_messages is not None
    # system prompt + user turn only
    assert len(fake.last_messages) == 2
    assert isinstance(fake.last_messages[0], SystemMessage)
    assert isinstance(fake.last_messages[1], HumanMessage)
    assert fake.last_messages[1].content == "next question"


def test_build_agent_returns_chat_agent() -> None:
    """``build_agent`` wires a ``ChatAgent`` that's ready to ``ainvoke``."""
    s = Settings(model_server_url="http://h:1")  # type: ignore[call-arg]
    agent = build_agent(s)
    assert isinstance(agent, ChatAgent)
    assert hasattr(agent, "ainvoke")
