"""Plain chat loop for the coder agent (POC).

We deliberately do NOT use DeepAgents here. DeepAgents emits structured
tool-call messages with ``content: null`` that llama.cpp's Hermes-2-Pro
Jinja template parser rejects (``Expected 'content' to be a string or an
array``). For a single-turn "write hello world" POC we don't need tools,
subagents, or planning middlewares — a straight ``ChatOpenAI`` round-trip
is enough.

See ``docs/adr/0009-strip-deepagents-for-poc-chat.md`` for the full story
and the trigger to bring DeepAgents (or a tool-capable runtime) back.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from coder_agent.config import Settings

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a concise coding assistant. Answer with idiomatic, typed code. No filler commentary."
)


class _GoogleIdTokenAuth(httpx.Auth):
    """httpx Auth that attaches a Google-minted ID token as Bearer on every request.

    Used when the model-server is a private Cloud Run service — IAM requires
    callers to present an ID token with the service URL as the audience.
    The coder-agent runs as ``coder-agent-sa`` which has ``run.invoker`` on
    model-server, so the metadata server mints a token for it automatically.

    Falls back to ADC locally (e.g. ``gcloud auth application-default login``)
    so tests against a remote Cloud Run model-server also work from a dev box.
    """

    requires_request_body = False

    def __init__(self, audience: str) -> None:
        self._audience = audience
        self._request: Any = None  # google.auth.transport.requests.Request — lazy init

    def _mint_token(self) -> str:
        # Lazy imports keep module import cheap and testable without google-auth.
        from google.auth.transport.requests import Request
        from google.oauth2 import id_token

        if self._request is None:
            self._request = Request()
        token: str = id_token.fetch_id_token(self._request, self._audience)  # type: ignore[no-untyped-call]
        return token

    def auth_flow(self, request: httpx.Request) -> Any:
        try:
            token = self._mint_token()
            request.headers["Authorization"] = f"Bearer {token}"
        except Exception as exc:
            # Surface a clear signal in logs; the upstream 401 will still bubble up.
            log.error("id_token.mint_failed", extra={"audience": self._audience, "error": str(exc)})
        yield request


def build_chat_model(settings: Settings) -> ChatOpenAI:
    """Return a LangChain chat model pointed at the self-hosted model-server.

    The model-server exposes an OpenAI-compatible endpoint at `{settings.model_server_base}`.
    No real API key is required; we pass a placeholder to satisfy the SDK.

    When ``settings.model_server_audience`` is set (Cloud Run), we attach a
    Google ID token to every outgoing request. When not set (local docker-compose,
    unit tests), we send no auth header.
    """
    audience = settings.model_server_audience
    http_client: httpx.Client | None = None
    http_async_client: httpx.AsyncClient | None = None
    if audience:
        auth = _GoogleIdTokenAuth(audience)
        http_client = httpx.Client(auth=auth, timeout=settings.request_timeout_seconds)
        http_async_client = httpx.AsyncClient(auth=auth, timeout=settings.request_timeout_seconds)

    return ChatOpenAI(
        model=settings.model_name,
        base_url=settings.model_server_base,
        api_key="not-used-by-llama-cpp",  # type: ignore[arg-type]
        temperature=settings.temperature,
        max_tokens=settings.max_tokens_per_response,  # type: ignore[call-arg]
        timeout=settings.request_timeout_seconds,
        http_client=http_client,
        http_async_client=http_async_client,
    )


class ChatAgent:
    """Thin wrapper around a ``ChatOpenAI`` model providing an ``ainvoke`` method.

    Accepts a ``{"messages": [{"role": ..., "content": ...}]}`` payload — same
    shape the FastAPI route previously handed to DeepAgents — and returns a
    ``{"messages": [<reply>]}`` dict so the route can stay structurally stable.
    """

    def __init__(self, model: ChatOpenAI, system_prompt: str = SYSTEM_PROMPT) -> None:
        self._model = model
        self._system_prompt = system_prompt

    def _to_lc_messages(self, raw_messages: list[dict[str, Any]]) -> list[BaseMessage]:
        messages: list[BaseMessage] = [SystemMessage(content=self._system_prompt)]
        for m in raw_messages:
            role = m.get("role")
            content = m.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "system":
                # Override default system prompt if caller explicitly passed one.
                messages[0] = SystemMessage(content=content)
            else:
                # Ignore assistant turns etc. for the single-turn POC.
                continue
        return messages

    async def ainvoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw = payload.get("messages", [])
        lc_messages = self._to_lc_messages(raw)
        reply = await self._model.ainvoke(lc_messages)
        return {"messages": [reply]}


def build_agent(settings: Settings) -> ChatAgent:
    """Build the chat agent used by the /chat route.

    Returns a ``ChatAgent`` with an ``ainvoke({'messages': [...]})`` interface,
    matching the shape ``main.py`` expects so the FastAPI contract is preserved.
    """
    model = build_chat_model(settings)
    return ChatAgent(model=model)
