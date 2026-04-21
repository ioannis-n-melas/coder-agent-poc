"""Offline tests for scripts/fetch_weights.py.

We do NOT actually hit HuggingFace — that would make the test suite require
network + 17 GiB free disk. Instead we monkeypatch `snapshot_download`, then
assert the script:
  * defaults to the ADR-0013-aligned community AWQ repo,
  * respects MODEL_HF_REPO / MODEL_TARGET_DIR / HF_TOKEN overrides,
  * fails loudly when the downloaded directory is missing required files
    (so a bad HF build can't produce a silently-broken image).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "fetch_weights.py"


def _load_fetch_weights() -> ModuleType:
    """Import scripts/fetch_weights.py as a module without needing it on sys.path."""
    spec = importlib.util.spec_from_file_location("fetch_weights", SCRIPT_PATH)
    assert spec and spec.loader, f"could not load {SCRIPT_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules["fetch_weights"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fake_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """Replace huggingface_hub.snapshot_download with a fake that records kwargs
    and populates target_dir with the minimum set of files the script checks for.
    """
    captured: dict[str, Any] = {}

    def _fake_snapshot_download(**kwargs: Any) -> str:
        captured.update(kwargs)
        local_dir = Path(kwargs["local_dir"])
        local_dir.mkdir(parents=True, exist_ok=True)
        (local_dir / "config.json").write_text("{}")
        (local_dir / "tokenizer.json").write_text("{}")
        (local_dir / "model-00001-of-00002.safetensors").write_bytes(b"\x00")
        return str(local_dir)

    module = _load_fetch_weights()
    monkeypatch.setattr(module, "snapshot_download", _fake_snapshot_download)
    return {"captured": captured, "module": module}


def test_defaults_use_adr_aligned_community_awq_repo(
    fake_download: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MODEL_TARGET_DIR", str(tmp_path / "weights"))
    monkeypatch.delenv("MODEL_HF_REPO", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)

    rc = fake_download["module"].main()
    assert rc == 0

    captured = fake_download["captured"]
    assert captured["repo_id"] == "cpatonn/Qwen3-Coder-30B-A3B-Instruct-AWQ-4bit"
    assert captured["local_dir"] == str(tmp_path / "weights")
    assert captured["token"] is None


def test_repo_id_override(
    fake_download: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MODEL_HF_REPO", "someorg/my-awq-fork")
    monkeypatch.setenv("MODEL_TARGET_DIR", str(tmp_path / "weights"))

    rc = fake_download["module"].main()
    assert rc == 0
    assert fake_download["captured"]["repo_id"] == "someorg/my-awq-fork"


def test_hf_token_passthrough(
    fake_download: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HF_TOKEN", "hf_sekret")
    monkeypatch.setenv("MODEL_TARGET_DIR", str(tmp_path / "weights"))

    rc = fake_download["module"].main()
    assert rc == 0
    assert fake_download["captured"]["token"] == "hf_sekret"


def test_missing_safetensors_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_fetch_weights()

    def _fake_download_without_weights(**kwargs: Any) -> str:
        local_dir = Path(kwargs["local_dir"])
        local_dir.mkdir(parents=True, exist_ok=True)
        (local_dir / "config.json").write_text("{}")
        (local_dir / "tokenizer.json").write_text("{}")
        # Deliberately no .safetensors
        return str(local_dir)

    monkeypatch.setattr(module, "snapshot_download", _fake_download_without_weights)
    monkeypatch.setenv("MODEL_TARGET_DIR", str(tmp_path / "weights"))

    rc = module.main()
    assert rc == 1
    assert "no *.safetensors files" in capsys.readouterr().err


def test_missing_tokenizer_or_config_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_fetch_weights()

    def _fake_download_without_tokenizer(**kwargs: Any) -> str:
        local_dir = Path(kwargs["local_dir"])
        local_dir.mkdir(parents=True, exist_ok=True)
        (local_dir / "config.json").write_text("{}")
        (local_dir / "model-00001-of-00001.safetensors").write_bytes(b"\x00")
        # No tokenizer.json
        return str(local_dir)

    monkeypatch.setattr(module, "snapshot_download", _fake_download_without_tokenizer)
    monkeypatch.setenv("MODEL_TARGET_DIR", str(tmp_path / "weights"))

    rc = module.main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "tokenizer.json" in err
