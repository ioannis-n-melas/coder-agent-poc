"""Tests for config loading and URL normalization."""

from __future__ import annotations

import pytest

from coder_agent.config import Settings


def test_model_server_base_adds_v1_when_missing() -> None:
    s = Settings(model_server_url="http://host:8080")  # type: ignore[call-arg]
    assert s.model_server_base == "http://host:8080/v1"


def test_model_server_base_preserves_v1_when_present() -> None:
    s = Settings(model_server_url="http://host:8080/v1")  # type: ignore[call-arg]
    assert s.model_server_base == "http://host:8080/v1"


def test_model_server_base_strips_trailing_slash() -> None:
    s = Settings(model_server_url="http://host:8080/")  # type: ignore[call-arg]
    assert s.model_server_base == "http://host:8080/v1"


def test_settings_requires_model_server_url() -> None:
    with pytest.raises(ValueError):
        Settings()  # type: ignore[call-arg]


def test_settings_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_SERVER_URL", "http://env-host:9000")
    monkeypatch.setenv("MODEL_NAME", "qwen-test")
    s = Settings()  # type: ignore[call-arg]
    assert s.model_server_url == "http://env-host:9000"
    assert s.model_name == "qwen-test"
