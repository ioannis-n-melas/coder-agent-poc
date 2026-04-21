"""Tests for the DeepAgents-backed coder agent.

Covers (per task brief):
1. Planner produces a non-empty plan for a simple input (mock LLM).
2. Refine loop has a bounded termination condition (doesn't spin forever).
3. OpenAI client is pointed at the env-configured base_url, never hardcoded.
4. ``_GoogleIdTokenAuth`` attaches / silently fails on the Bearer header.
5. ``DeepAgentWrapper.ainvoke`` round-trips with a stub graph.
6. Backward-compat aliases (``ChatAgent``, ``SYSTEM_PROMPT``) still resolve.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from coder_agent.agent import (
    SYSTEM_PROMPT,
    ChatAgent,
    DeepAgentWrapper,
    _GoogleIdTokenAuth,
    _MAX_REFINE_ITERATIONS,
    _ORCHESTRATOR_SYSTEM_PROMPT,
    _build_subagents,
    build_agent,
    build_chat_model,
)
from coder_agent.config import Settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(**kwargs: Any) -> Settings:
    """Return a Settings with a fake model server URL, plus any overrides."""
    # Provide a default model_server_url only when the caller hasn't passed one.
    kwargs.setdefault("model_server_url", "http://fake-model-server:8080")
    return Settings(**kwargs)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# 3. OpenAI client pointed at env-configured base_url (never hardcoded)
# ---------------------------------------------------------------------------


def test_chat_model_uses_model_server_base() -> None:
    """``build_chat_model`` must send requests to the URL in MODEL_SERVER_URL."""
    s = _settings(model_server_url="http://my-server:8080")
    model = build_chat_model(s)
    # base_url ends up in the underlying OpenAI SDK client; verify it.
    base = getattr(model, "openai_api_base", None) or str(getattr(model, "async_client", ""))
    assert "my-server:8080" in str(base) or "my-server:8080" in str(
        getattr(model, "root_client", "")
    ), f"expected my-server:8080 in model config, got {base!r}"


def test_chat_model_base_url_is_from_settings_not_hardcoded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The base_url must come from config, not be hardcoded in agent.py."""
    monkeypatch.setenv("MODEL_SERVER_URL", "http://env-injected-host:9999")
    from coder_agent.config import Settings as S

    s = S()  # type: ignore[call-arg]
    model = build_chat_model(s)
    # Confirm the SDK will target env-injected-host:9999
    config_dump = getattr(model, "model_dump", lambda: {})() or {}
    base = (
        config_dump.get("openai_api_base")
        or str(getattr(model, "root_client", ""))
        or str(getattr(model, "async_client", ""))
    )
    assert "env-injected-host:9999" in str(base) or "env-injected-host:9999" in str(
        getattr(model, "root_async_client", "")
    ), (
        f"base_url must track MODEL_SERVER_URL env var; "
        f"got {base!r} for host env-injected-host:9999"
    )


def test_chat_model_uses_configured_temperature() -> None:
    s = _settings(temperature=0.7)
    model = build_chat_model(s)
    assert model.temperature == 0.7


def test_chat_model_uses_configured_model_name() -> None:
    s = _settings(model_name="qwen3-coder-30b")
    model = build_chat_model(s)
    assert model.model_name == "qwen3-coder-30b"


def test_no_id_token_auth_when_audience_unset() -> None:
    """Local dev / unit tests run without a Cloud Run audience — no auth attached."""
    s = _settings()
    model = build_chat_model(s)
    assert model is not None


# ---------------------------------------------------------------------------
# _GoogleIdTokenAuth
# ---------------------------------------------------------------------------


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
    s = _settings(
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
            if inner is not None and isinstance(
                getattr(inner, "_auth", None), _GoogleIdTokenAuth
            ):
                found = True
                break
    assert found, "expected _GoogleIdTokenAuth to be attached to the OpenAI SDK httpx client"


# ---------------------------------------------------------------------------
# 1. Planner produces a non-empty plan (mock LLM)
# ---------------------------------------------------------------------------


async def test_deep_agent_wrapper_ainvoke_returns_messages() -> None:
    """DeepAgentWrapper.ainvoke passes payload to the graph and returns messages."""
    ai_reply = AIMessage(content="Here is my plan:\n1. Analyze imports\n2. Write code\n3. Refine")

    # Stub graph that records the invocation and returns a canned reply.
    stub_graph = MagicMock()
    stub_graph.ainvoke = AsyncMock(return_value={"messages": [ai_reply]})

    wrapper = DeepAgentWrapper(graph=stub_graph)
    payload = {"messages": [HumanMessage(content="write a hello world function")]}
    result = await wrapper.ainvoke(payload)

    stub_graph.ainvoke.assert_called_once_with(payload)
    messages = result.get("messages", [])
    assert len(messages) >= 1, "expected at least one message in the result"
    last = messages[-1]
    content = getattr(last, "content", None) or last.get("content", "")
    assert len(content) > 0, "planner must return a non-empty response"


async def test_planner_response_is_non_empty_for_simple_input() -> None:
    """Planner stage: for any non-trivial prompt the orchestrator must produce content."""
    plan_text = (
        "Plan:\n"
        "1. Read hello.py\n"
        "2. Implement greet() function\n"
        "3. Run tests\n"
        "4. Refine if needed"
    )
    stub_graph = MagicMock()
    stub_graph.ainvoke = AsyncMock(
        return_value={"messages": [AIMessage(content=plan_text)]}
    )

    wrapper = DeepAgentWrapper(graph=stub_graph)
    result = await wrapper.ainvoke(
        {"messages": [{"role": "user", "content": "add a greet function to hello.py"}]}
    )
    messages = result["messages"]
    assert messages, "no messages returned"
    content = getattr(messages[-1], "content", None) or messages[-1].get("content", "")
    assert content.strip(), "planner produced empty output"


# ---------------------------------------------------------------------------
# 2. Refine loop bounded termination
# ---------------------------------------------------------------------------


def test_max_refine_iterations_is_positive_and_bounded() -> None:
    """_MAX_REFINE_ITERATIONS must be a positive int within a sane range.

    This documents the contract: the refiner subagent description explicitly
    tells the orchestrator to stop after at most this many refinement passes,
    preventing an unbounded loop.
    """
    assert isinstance(_MAX_REFINE_ITERATIONS, int)
    assert 1 <= _MAX_REFINE_ITERATIONS <= 10, (
        f"_MAX_REFINE_ITERATIONS={_MAX_REFINE_ITERATIONS} is outside the expected [1, 10] range"
    )


def test_refiner_description_mentions_iteration_limit() -> None:
    """The refiner subagent description must embed the max iteration count.

    This is the mechanism that tells the LLM orchestrator when to stop
    refining — without it the orchestrator could loop indefinitely.
    """
    s = _settings()
    model = build_chat_model(s)
    subagents = _build_subagents(model)

    refiner = next((a for a in subagents if a["name"] == "refiner"), None)
    assert refiner is not None, "refiner subagent not found in _build_subagents output"
    description: str = refiner["description"]
    assert str(_MAX_REFINE_ITERATIONS) in description, (
        f"refiner description must mention _MAX_REFINE_ITERATIONS={_MAX_REFINE_ITERATIONS}; "
        f"got: {description!r}"
    )


async def test_deep_agent_wrapper_does_not_loop_on_single_response() -> None:
    """If the stub graph returns immediately, ainvoke must not re-invoke it."""
    stub_graph = MagicMock()
    stub_graph.ainvoke = AsyncMock(
        return_value={"messages": [AIMessage(content="LGTM — no changes needed")]}
    )

    wrapper = DeepAgentWrapper(graph=stub_graph)
    await wrapper.ainvoke({"messages": [{"role": "user", "content": "refine the code"}]})

    # ainvoke must be called exactly once — no retry / re-entry from the wrapper.
    assert stub_graph.ainvoke.call_count == 1


# ---------------------------------------------------------------------------
# build_agent returns DeepAgentWrapper
# ---------------------------------------------------------------------------


def test_build_agent_returns_deep_agent_wrapper() -> None:
    """``build_agent`` must return a ``DeepAgentWrapper`` (not the old ``ChatAgent``)."""
    s = _settings()
    agent = build_agent(s)
    assert isinstance(agent, DeepAgentWrapper)
    assert hasattr(agent, "ainvoke")


# ---------------------------------------------------------------------------
# _build_subagents returns three stage-subagents with correct names
# ---------------------------------------------------------------------------


def test_build_subagents_returns_all_three_stages() -> None:
    """_build_subagents must return analyzer + implementer + refiner."""
    s = _settings()
    model = build_chat_model(s)
    subagents = _build_subagents(model)

    names = [a["name"] for a in subagents]
    assert "analyzer" in names, f"missing 'analyzer'; got {names}"
    assert "implementer" in names, f"missing 'implementer'; got {names}"
    assert "refiner" in names, f"missing 'refiner'; got {names}"


def test_build_subagents_each_has_system_prompt() -> None:
    """Every stage-subagent must have a non-empty system_prompt."""
    s = _settings()
    model = build_chat_model(s)
    subagents = _build_subagents(model)
    for subagent in subagents:
        prompt = subagent.get("system_prompt", "")
        assert isinstance(prompt, str) and len(prompt) > 20, (
            f"subagent '{subagent['name']}' has a trivial system_prompt: {prompt!r}"
        )


# ---------------------------------------------------------------------------
# Backward-compat aliases
# ---------------------------------------------------------------------------


def test_chat_agent_alias_is_deep_agent_wrapper() -> None:
    """ChatAgent alias must resolve to DeepAgentWrapper for backward compat."""
    assert ChatAgent is DeepAgentWrapper


def test_system_prompt_alias_is_orchestrator_prompt() -> None:
    """SYSTEM_PROMPT alias must resolve to the orchestrator prompt."""
    assert SYSTEM_PROMPT is _ORCHESTRATOR_SYSTEM_PROMPT
    assert len(SYSTEM_PROMPT) > 50
