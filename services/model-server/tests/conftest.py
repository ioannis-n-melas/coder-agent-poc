"""Shared pytest fixtures for model-server contract tests.

There are two test tiers here:

1. **Offline / CPU-only** — validate the launch script (entrypoint.sh) produces
   the argv we expect for any given set of env vars, and that fetch_weights.py
   parses its inputs correctly. These run anywhere (including CI without a GPU)
   and catch the most common "I broke the launch command" regressions.

2. **Live GPU** — marked with @pytest.mark.gpu. They point an httpx client at
   an actual running vLLM server (local docker or a Cloud Run URL) and assert
   the OpenAI contract: /v1/models lists our served name, /v1/chat/completions
   streams a response, /health returns 200 once the model is ready.

   These require ``MODEL_SERVER_URL`` in the environment to opt-in. Without
   it they are skipped. We never fail CI on a missing GPU — devops-engineer
   wires that into the deploy pipeline.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import httpx
import pytest


def _gpu_base_url() -> str | None:
    """Return the base URL for live GPU tests, or None to skip."""
    return os.environ.get("MODEL_SERVER_URL") or None


@pytest.fixture
def live_server_url() -> str:
    """Base URL of a running vLLM server.

    Tests using this fixture are skipped when MODEL_SERVER_URL is unset,
    making them safe to run on a laptop without a GPU. Set MODEL_SERVER_URL
    to a reachable endpoint (e.g. http://localhost:8080 or a deployed Cloud
    Run URL) to enable the live tier.
    """
    url = _gpu_base_url()
    if url is None:
        pytest.skip("MODEL_SERVER_URL not set; live GPU tests disabled")
    return url.rstrip("/")


@pytest.fixture
def live_client(live_server_url: str) -> Iterator[httpx.Client]:
    """httpx client pre-pointed at the live vLLM server."""
    # Timeouts are deliberately generous: cold starts on Cloud Run GPU can run
    # to ~60 s (ADR-0011), and a chat completion has to fit inside that envelope
    # in the worst case.
    with httpx.Client(base_url=live_server_url, timeout=90.0) as client:
        yield client


@pytest.fixture
def served_model_name() -> str:
    """Name the agent uses to address the model.

    Must match the value passed via --served-model-name in entrypoint.sh.
    If a future change renames the served model, this fixture is the single
    place to update it for the test suite.
    """
    return os.environ.get("SERVED_MODEL_NAME", "Qwen/Qwen3-Coder-30B-A3B-Instruct")
