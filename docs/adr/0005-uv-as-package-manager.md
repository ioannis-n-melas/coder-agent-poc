# 0005 — uv for Python packaging

- **Status**: Accepted
- **Date**: 2026-04-19
- **Authors**: @ioannis-n-melas

## Context

We need a Python packaging tool that gives us a reproducible lockfile, fast installs, and works in both local dev and CI/Docker builds.

## Options considered

- **pip + requirements.txt** — familiar but no lockfile, slow, what market-snapshot uses.
- **pip-tools** — lockfile via `pip-compile` but still slow installs.
- **Poetry** — lockfile + good DX but slow resolver, Poetry-specific `pyproject.toml` dialect.
- **uv** (Astral) — Rust-based, 10–100× faster, reads standard `pyproject.toml`, drop-in `pip install` replacement, lockfile via `uv.lock`.

## Decision

**uv.** Standard across the project. `uv sync` in CI and Docker. Lockfile committed.

## Consequences

- **Good**: cold CI installs in seconds, not minutes.
- **Good**: standard `pyproject.toml` — portable if we switch tools.
- **Bad**: diverges from market-snapshot's pip setup. Contributors switching between repos need to remember which one uses which.
- **Trigger to revisit**: uv deprecation or a repeated incompatibility we can't work around.

## References

- [uv docs](https://docs.astral.sh/uv/)
