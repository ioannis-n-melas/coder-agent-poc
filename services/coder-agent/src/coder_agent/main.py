"""FastAPI entrypoint for the coder-agent service."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from coder_agent import __version__
from coder_agent.agent import build_agent
from coder_agent.config import Settings, get_settings
from coder_agent.logging_setup import configure_logging

log = logging.getLogger(__name__)


# ── lifespan ────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the agent once at startup and attach to app.state."""
    settings = get_settings()
    configure_logging(settings.log_level)
    log.info(
        "starting",
        extra={"version": __version__, "model_server": settings.model_server_base},
    )
    app.state.settings = settings
    app.state.agent = build_agent(settings)
    yield
    log.info("shutting down")


app = FastAPI(title="coder-agent", version=__version__, lifespan=lifespan)


# ── request / response models ──────────────────────────────────────
class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=16000)
    request_id: str | None = Field(default=None)


class ChatResponse(BaseModel):
    request_id: str
    output: str


class HealthResponse(BaseModel):
    status: str
    version: str


class ReadyResponse(BaseModel):
    status: str
    model_server_reachable: bool


# ── routes ─────────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


@app.get("/ready", response_model=ReadyResponse)
async def ready() -> ReadyResponse:
    settings: Settings = app.state.settings
    # If the model-server is on private Cloud Run, we need a Google ID token to
    # even reach /health. Reuse the same auth flow as the agent's chat calls.
    from coder_agent.agent import _GoogleIdTokenAuth  # local import — avoids cycle at boot

    auth = (
        _GoogleIdTokenAuth(settings.model_server_audience)
        if settings.model_server_audience
        else None
    )
    try:
        async with httpx.AsyncClient(timeout=5.0, auth=auth) as client:
            resp = await client.get(f"{settings.model_server_base.removesuffix('/v1')}/health")
        reachable = resp.status_code == 200
    except httpx.HTTPError:
        reachable = False
    return ReadyResponse(
        status="ok" if reachable else "degraded",
        model_server_reachable=reachable,
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Run the agent loop for a single prompt and return the final output."""
    rid = req.request_id or str(uuid.uuid4())
    log.info("chat.start", extra={"request_id": rid, "prompt_len": len(req.prompt)})

    agent = app.state.agent
    try:
        result: dict[str, Any] = await agent.ainvoke(
            {"messages": [{"role": "user", "content": req.prompt}]},
        )
    except Exception as exc:
        log.exception("chat.error", extra={"request_id": rid})
        raise HTTPException(status_code=502, detail=f"agent failed: {exc}") from exc

    messages = result.get("messages", [])
    final = messages[-1] if messages else None
    output = getattr(final, "content", None) or (
        final.get("content") if isinstance(final, dict) else ""
    )

    log.info("chat.done", extra={"request_id": rid, "output_len": len(output or "")})
    return ChatResponse(request_id=rid, output=output or "")
