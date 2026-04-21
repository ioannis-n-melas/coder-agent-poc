"""Coder agent built on DeepAgents — plan → analyze → implement → refine.

ADR-0012 re-introduces DeepAgents after ADR-0009 stripped it for the POC.
The root cause of ADR-0009 (``content: null`` rejections from llama.cpp's
Jinja template) is gone: vLLM (ADR-0010) handles OpenAI tool-calling cleanly.

Shape: one top-level ``create_deep_agent`` graph acting as the orchestrator
(planner), with three declared subagents — analyzer, implementer, refiner —
that it can delegate to via the built-in ``task`` tool. This is ADR-0012
shape (A): four stages as DeepAgents subagents, orchestrated by the planner.
The planner itself embodies the "plan" stage; the three subagents handle the
remaining three stages.

The public surface is unchanged: ``build_agent(settings)`` returns an object
with an ``ainvoke({"messages": [...]})`` method — same shape main.py always
expected, same shape the FastAPI route always passed in.

ADR-0001 is preserved: no vLLM or llama.cpp imports anywhere in this module.
The model is a ``ChatOpenAI`` instance pointed at ``settings.model_server_base``
(an env-var-configured OpenAI-compatible URL). Swapping runtimes remains a URL
change only.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage
from langgraph.graph.state import CompiledStateGraph
from deepagents import create_deep_agent
from deepagents.backends import StateBackend

from coder_agent.config import Settings

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompts for each stage-subagent
# ---------------------------------------------------------------------------

_ORCHESTRATOR_SYSTEM_PROMPT = """\
You are a coder-agent orchestrator.  When the user asks you to work on code,
follow these four stages in order:

1. **Plan**: Break the request into concrete sub-tasks.  Think about what
   files need to be read, written, or changed, and what the expected outcome
   of each step is.  Output a brief numbered plan.

2. **Analyze**: Delegate to the "analyzer" subagent to examine the relevant
   code, understand the codebase structure, and gather facts needed to
   implement the plan.

3. **Implement**: Delegate to the "implementer" subagent to write or modify
   the code according to the plan and the analyzer's findings.

4. **Refine**: Delegate to the "refiner" subagent to review the implementation,
   check for errors, run any available tests, and apply improvements.

After all four stages complete, synthesize the results and return a concise
summary of what was done.

Be direct.  Do not pad responses.  Do not explain what you are about to do —
just do it.
"""

_ANALYZER_SYSTEM_PROMPT = """\
You are the Analyze stage of a coder-agent pipeline.  Your job:

- Read the relevant files indicated in the task description.
- Understand the current structure: function signatures, imports, types,
  patterns, and conventions used in the codebase.
- Identify what specifically needs to change and why.
- Return a concise structured report: which files, which lines, what
  must change, and any constraints or risks to be aware of.

Do not write any code.  Return only analysis and findings.
"""

_IMPLEMENTER_SYSTEM_PROMPT = """\
You are the Implement stage of a coder-agent pipeline.  Your job:

- Read the analyzer's report from the task description.
- Write or modify the code files as specified.
- Follow the existing style, types, and conventions of the codebase.
- Prefer minimal, targeted edits over rewrites.
- After writing, list every file you changed and what you changed.

Return a summary: files changed, what was added/removed/modified.
"""

_REFINER_SYSTEM_PROMPT = """\
You are the Refine stage of a coder-agent pipeline.  Your job:

- Review the implementation described in the task.
- Check for: type errors, logic bugs, missing edge-case handling,
  inconsistency with surrounding code, and violated conventions.
- If tests exist for the changed code, read them and verify the
  implementation satisfies them.
- Propose and apply targeted corrections — only where needed.
- Return a verdict: "LGTM" (no changes needed) or a list of corrections
  applied, each with a brief reason.
"""

# Maximum number of refine iterations before we stop.
# DeepAgents' recursion limit is its own safety net, but we add an explicit
# guard via the subagent description so the orchestrator knows when to stop.
_MAX_REFINE_ITERATIONS = 3

# ---------------------------------------------------------------------------
# Google ID-token auth (unchanged from POC — ADR-0009 kept this)
# ---------------------------------------------------------------------------


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
            log.error(
                "id_token.mint_failed",
                extra={"audience": self._audience, "error": str(exc)},
            )
        yield request


# ---------------------------------------------------------------------------
# Chat-model factory (unchanged from POC except public name stays consistent)
# ---------------------------------------------------------------------------


def build_chat_model(settings: Settings) -> ChatOpenAI:
    """Return a LangChain ChatOpenAI pointed at the env-configured model-server.

    Passes ``base_url=settings.model_server_base`` (derived from
    ``MODEL_SERVER_URL`` env var) so the model is backend-agnostic (ADR-0001).
    When ``model_server_audience`` is set, attaches Google ID-token auth for
    private Cloud Run (unchanged from POC).
    """
    audience = settings.model_server_audience
    http_client: httpx.Client | None = None
    http_async_client: httpx.AsyncClient | None = None
    if audience:
        auth = _GoogleIdTokenAuth(audience)
        http_client = httpx.Client(auth=auth, timeout=settings.request_timeout_seconds)
        http_async_client = httpx.AsyncClient(
            auth=auth, timeout=settings.request_timeout_seconds
        )

    return ChatOpenAI(
        model=settings.model_name,
        base_url=settings.model_server_base,
        api_key="not-used-by-self-hosted-runtime",  # type: ignore[arg-type]
        temperature=settings.temperature,
        max_tokens=settings.max_tokens_per_response,  # type: ignore[call-arg]
        timeout=settings.request_timeout_seconds,
        http_client=http_client,
        http_async_client=http_async_client,
    )


# ---------------------------------------------------------------------------
# DeepAgent graph factory
# ---------------------------------------------------------------------------


def _build_subagents(model: ChatOpenAI) -> list[dict[str, Any]]:
    """Return the three stage-subagent specs (analyzer, implementer, refiner).

    Each subagent shares the same ``ChatOpenAI`` instance so they all talk
    to the same env-configured model-server (ADR-0001 preserved).

    We explicitly set ``tools=[]`` for all subagents: they use the filesystem
    tools injected by DeepAgents' built-in ``FilesystemMiddleware`` (ls, read,
    write, edit, glob, grep) rather than any custom tools.  Passing an empty
    list here just means "no additional tools beyond what middleware injects."
    """
    return [
        {
            "name": "analyzer",
            "description": (
                "Reads and analyzes the relevant code files. "
                "Use this after planning to gather the facts needed to implement. "
                "Provide it a clear description of what to analyze and what to report."
            ),
            "system_prompt": _ANALYZER_SYSTEM_PROMPT,
            "model": model,
            "tools": [],
        },
        {
            "name": "implementer",
            "description": (
                "Writes or modifies code files based on the plan and analyzer findings. "
                "Use this after analysis is complete. "
                "Provide it the full plan, analyzer report, and target file paths."
            ),
            "system_prompt": _IMPLEMENTER_SYSTEM_PROMPT,
            "model": model,
            "tools": [],
        },
        {
            "name": "refiner",
            "description": (
                f"Reviews and corrects the implementation. "
                f"Use this after implementation. "
                f"It will iterate up to {_MAX_REFINE_ITERATIONS} times then stop. "
                f"Provide it the implementation summary and file paths to review."
            ),
            "system_prompt": _REFINER_SYSTEM_PROMPT,
            "model": model,
            "tools": [],
        },
    ]


def build_deep_agent(settings: Settings) -> CompiledStateGraph:  # type: ignore[type-arg]
    """Build and return the DeepAgents plan→analyze→implement→refine graph.

    Returns a ``CompiledStateGraph`` whose ``ainvoke`` accepts:
        ``{"messages": [HumanMessage | {"role": ..., "content": ...}]}``

    This is the same shape ``main.py`` always passed to the agent — the
    FastAPI surface is unchanged.
    """
    model = build_chat_model(settings)
    subagents = _build_subagents(model)

    graph = create_deep_agent(
        model=model,
        system_prompt=_ORCHESTRATOR_SYSTEM_PROMPT,
        subagents=subagents,  # type: ignore[arg-type]
        backend=StateBackend(),
        name="coder-agent",
    )

    log.info(
        "deep_agent.built",
        extra={
            "model_name": settings.model_name,
            "model_server_base": settings.model_server_base,
            "subagents": [s["name"] for s in subagents],
        },
    )
    return graph


# ---------------------------------------------------------------------------
# DeepAgentWrapper — preserves the ``ainvoke({messages: [...]})`` contract
# ---------------------------------------------------------------------------


class DeepAgentWrapper:
    """Thin adapter that presents a ``CompiledStateGraph`` via the same
    ``ainvoke({"messages": [...]})`` interface that ``main.py`` expects.

    The wrapper also normalises the output: ``main.py`` reads
    ``result["messages"][-1].content`` — that's what DeepAgents returns
    natively, so no output transformation is needed.  The wrapper exists
    purely to (a) hold the graph instance and (b) give a named type for
    isinstance checks in tests.
    """

    def __init__(self, graph: CompiledStateGraph) -> None:  # type: ignore[type-arg]
        self._graph = graph

    async def ainvoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Invoke the DeepAgents graph and return its output unchanged.

        ``payload`` must have shape ``{"messages": [...]}``.  Messages can be
        ``BaseMessage`` instances or ``{"role": ..., "content": ...}`` dicts —
        DeepAgents accepts both.
        """
        result: dict[str, Any] = await self._graph.ainvoke(payload)
        return result


# ---------------------------------------------------------------------------
# Public factory — matches main.py's ``build_agent(settings)`` call
# ---------------------------------------------------------------------------


def build_agent(settings: Settings) -> DeepAgentWrapper:
    """Build the coder agent used by the /chat route.

    Returns a ``DeepAgentWrapper`` with ``ainvoke({'messages': [...]})`` — the
    same interface ``main.py`` always expected from ``ChatAgent``.

    The underlying graph is a ``create_deep_agent`` with planner (orchestrator)
    + analyzer + implementer + refiner subagents (ADR-0012 shape A).
    """
    graph = build_deep_agent(settings)
    return DeepAgentWrapper(graph=graph)


# ---------------------------------------------------------------------------
# Backward-compat alias — tests that import ``ChatAgent`` or ``SYSTEM_PROMPT``
# directly will still resolve.  Remove after test suite is updated.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = _ORCHESTRATOR_SYSTEM_PROMPT
ChatAgent = DeepAgentWrapper  # type alias for tests that check isinstance
