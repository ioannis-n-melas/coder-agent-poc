"""ADR-0001 compliance: coder-agent must never import runtime-specific modules.

The agent⇄model contract is OpenAI-compatible HTTP. If `coder_agent.agent`
(or anything it transitively imports) pulls in `vllm`, `llama_cpp`, or a
similar backend-specific module, swapping the runtime becomes a code change
instead of a URL change — a direct ADR-0001 violation.

This test imports the agent module and inspects `sys.modules` to ensure
nothing runtime-specific got loaded.
"""

from __future__ import annotations

import importlib
import sys


_FORBIDDEN_PREFIXES: tuple[str, ...] = ("vllm", "llama_cpp", "llamacpp")


def test_coder_agent_does_not_import_runtime_specific_modules() -> None:
    for mod in list(sys.modules):
        if mod.startswith("coder_agent"):
            del sys.modules[mod]

    importlib.import_module("coder_agent.agent")

    offending = sorted(
        name
        for name in sys.modules
        if any(name == p or name.startswith(f"{p}.") for p in _FORBIDDEN_PREFIXES)
    )
    assert not offending, (
        "ADR-0001 violation: coder_agent.agent transitively imports runtime-specific "
        f"modules: {offending}. The agent must only talk to the model via "
        "OpenAI-compatible HTTP — no direct import of the serving runtime."
    )
