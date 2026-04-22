"""Offline tests for entrypoint.sh — no GPU / vLLM required.

These tests rewrite the last line of entrypoint.sh on-the-fly to echo the
final argv instead of exec'ing vLLM, then invoke the script under bash with
various env-var combinations. This pins down the most failure-prone thing in
the image: the CLI flags passed to vLLM.

If these tests pass, the container is guaranteed to invoke vLLM with the
flags ml-engineer intends, even if the published vLLM image's ENTRYPOINT
changes upstream.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parent.parent
ENTRYPOINT = SERVICE_ROOT / "entrypoint.sh"


def _run_entrypoint_in_dryrun(env: dict[str, str]) -> list[str]:
    """Execute entrypoint.sh with the `exec` line replaced by an echo.

    Returns the argv (as a list) that would have been passed to
    ``python3 -m vllm.entrypoints.openai.api_server``.
    """
    assert ENTRYPOINT.exists(), f"missing {ENTRYPOINT}"
    script = ENTRYPOINT.read_text()

    # Substitute the final `exec python3 …` call with a shell expansion that
    # prints the argv on a single line prefixed with a sentinel we can grep
    # for. Everything else in the script (variable defaults, echo banner) is
    # preserved so we test the real behaviour.
    modified = script.replace(
        'exec python3 -m vllm.entrypoints.openai.api_server "${ARGS[@]}"',
        'printf "ARGV>>>%s<<<\\n" "${ARGS[*]}"',
    )
    assert modified != script, "entrypoint.sh shape changed; update test substitution"

    proc = subprocess.run(
        ["bash", "-c", modified],
        env={**env, "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    )
    for line in proc.stdout.splitlines():
        if line.startswith("ARGV>>>") and line.endswith("<<<"):
            argv_str = line[len("ARGV>>>") : -len("<<<")]
            return argv_str.split()
    raise AssertionError(f"no ARGV line in output; stdout was:\n{proc.stdout}")


def test_defaults_are_applied_when_no_env_vars_set() -> None:
    argv = _run_entrypoint_in_dryrun(env={})
    # Model directory defaults to the baked-in path.
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "/models/qwen3-coder-30b-a3b-instruct-awq"
    # Served model name — what the agent addresses.
    assert "--served-model-name" in argv
    assert argv[argv.index("--served-model-name") + 1] == "Qwen/Qwen3-Coder-30B-A3B-Instruct"
    # Quantization defaults to awq_marlin (fast path on L4/SM89).
    assert "--quantization" in argv
    assert argv[argv.index("--quantization") + 1] == "awq_marlin"
    # Context window defaults to the ADR-0013 proposal of 32768.
    assert "--max-model-len" in argv
    assert argv[argv.index("--max-model-len") + 1] == "32768"
    # GPU memory utilization default.
    assert "--gpu-memory-utilization" in argv
    assert argv[argv.index("--gpu-memory-utilization") + 1] == "0.90"
    # Required for Qwen's custom tokenizer assets.
    assert "--trust-remote-code" in argv
    # Port default for local docker-compose.
    assert "--port" in argv
    assert argv[argv.index("--port") + 1] == "8080"
    # Bind on 0.0.0.0 so Cloud Run's health probes reach us.
    assert "--host" in argv
    assert argv[argv.index("--host") + 1] == "0.0.0.0"


def test_port_env_var_is_honoured() -> None:
    """Cloud Run injects PORT; the server MUST bind to it."""
    argv = _run_entrypoint_in_dryrun(env={"PORT": "9090"})
    assert argv[argv.index("--port") + 1] == "9090"


def test_max_model_len_override() -> None:
    """If KV-cache headroom proves insufficient at 32K, we drop to 16K."""
    argv = _run_entrypoint_in_dryrun(env={"MAX_MODEL_LEN": "16384"})
    assert argv[argv.index("--max-model-len") + 1] == "16384"


def test_served_model_name_override() -> None:
    """The agent-visible model id is a configurable runtime input."""
    argv = _run_entrypoint_in_dryrun(env={"SERVED_MODEL_NAME": "custom/model-id"})
    assert argv[argv.index("--served-model-name") + 1] == "custom/model-id"


def test_quantization_override_to_plain_awq() -> None:
    """Rollback path: if awq_marlin has a regression we can force plain awq."""
    argv = _run_entrypoint_in_dryrun(env={"QUANTIZATION": "awq"})
    assert argv[argv.index("--quantization") + 1] == "awq"


def test_enforce_eager_flag_added_only_when_requested() -> None:
    argv_off = _run_entrypoint_in_dryrun(env={})
    assert "--enforce-eager" not in argv_off

    argv_on = _run_entrypoint_in_dryrun(env={"ENFORCE_EAGER": "true"})
    assert "--enforce-eager" in argv_on


def test_tool_choice_flags_present_by_default() -> None:
    """DeepAgents (ADR-0012) requires --enable-auto-tool-choice + parser."""
    argv = _run_entrypoint_in_dryrun(env={})
    assert "--enable-auto-tool-choice" in argv
    assert "--tool-call-parser" in argv
    assert argv[argv.index("--tool-call-parser") + 1] == "hermes"


def test_tool_choice_can_be_disabled() -> None:
    """Escape hatch if a future model needs the vLLM default (no tool choice)."""
    argv = _run_entrypoint_in_dryrun(env={"ENABLE_TOOL_CHOICE": "false"})
    assert "--enable-auto-tool-choice" not in argv
    assert "--tool-call-parser" not in argv


def test_tool_call_parser_override() -> None:
    """Swap the parser for a future model (e.g. llama3_json)."""
    argv = _run_entrypoint_in_dryrun(env={"TOOL_CALL_PARSER": "llama3_json"})
    assert argv[argv.index("--tool-call-parser") + 1] == "llama3_json"


def test_script_uses_strict_mode() -> None:
    """Regressions on `set -euo pipefail` have bitten ops-y shell scripts
    before. Lock it in so a careless edit doesn't silently swallow errors."""
    content = ENTRYPOINT.read_text()
    lines = content.splitlines()
    # Must appear as its own line (not in a comment block) and before the
    # first var assignment / ARGS setup.
    strict_line_idx = next(
        (i for i, line in enumerate(lines) if line.strip() == "set -euo pipefail"),
        None,
    )
    assert strict_line_idx is not None, (
        "entrypoint.sh is missing `set -euo pipefail`"
    )
    # Must come before any `exec` or `ARGS=` line to be load-bearing.
    first_exec = next(
        (i for i, line in enumerate(lines) if line.lstrip().startswith(("exec ", "ARGS="))),
        len(lines),
    )
    assert strict_line_idx < first_exec, (
        "`set -euo pipefail` must precede the exec / argv setup"
    )


@pytest.mark.parametrize("required_flag", ["--host", "--port", "--model", "--quantization"])
def test_required_flags_always_present(required_flag: str) -> None:
    argv = _run_entrypoint_in_dryrun(env={})
    assert required_flag in argv, f"entrypoint.sh dropped {required_flag}"
