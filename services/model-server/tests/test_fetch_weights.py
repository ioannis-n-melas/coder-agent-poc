"""Offline tests for scripts/fetch_weights.py.

We do NOT actually hit HuggingFace — that would make the test suite require
network + 17 GiB free disk. Instead we monkeypatch `snapshot_download` and
`hf_hub_download`, then assert the script:
  * defaults to the ADR-0013-aligned community AWQ repo,
  * respects MODEL_HF_REPO / MODEL_TARGET_DIR / HF_TOKEN overrides,
  * fails loudly when the downloaded directory is missing required files
    (so a bad HF build can't produce a silently-broken image),
  * overlays `chat_template` from the upstream Qwen repo when the AWQ repo
    ships a tokenizer_config.json without one (fix for the vLLM
    "no default chat template" error seen on rev 00007 — 2026-04-22).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "fetch_weights.py"

# A stand-in Jinja body; its exact content doesn't matter for these tests,
# only that the overlay propagates it verbatim.
FAKE_UPSTREAM_TEMPLATE = "{% if messages %}{{ messages[0]['content'] }}{% endif %}"


def _load_fetch_weights() -> ModuleType:
    """Import scripts/fetch_weights.py as a module without needing it on sys.path."""
    spec = importlib.util.spec_from_file_location("fetch_weights", SCRIPT_PATH)
    assert spec and spec.loader, f"could not load {SCRIPT_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules["fetch_weights"] = module
    spec.loader.exec_module(module)
    return module


def _write_awq_snapshot(local_dir: Path, *, with_template: bool = False) -> None:
    """Populate local_dir with the minimum fileset the script sanity-checks.

    By default the tokenizer_config.json has NO chat_template, matching the
    real cpatonn AWQ repo behaviour that motivated the fix.
    """
    local_dir.mkdir(parents=True, exist_ok=True)
    (local_dir / "config.json").write_text("{}")
    (local_dir / "tokenizer.json").write_text("{}")
    (local_dir / "model-00001-of-00002.safetensors").write_bytes(b"\x00")
    cfg: dict[str, Any] = {
        "tokenizer_class": "Qwen2Tokenizer",
        "model_max_length": 262144,
    }
    if with_template:
        cfg["chat_template"] = "{{ 'preexisting' }}"
    (local_dir / "tokenizer_config.json").write_text(json.dumps(cfg))


@pytest.fixture
def fake_download(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> dict[str, Any]:
    """Replace HF downloads with fakes that record kwargs.

    `snapshot_download` populates target_dir with the minimum fileset,
    including a tokenizer_config.json WITHOUT a chat_template (matches the
    real cpatonn AWQ repo). `hf_hub_download` serves an upstream
    tokenizer_config.json that DOES carry a chat_template. Together these
    exercise the overlay happy-path in every test that doesn't override.
    """
    captured: dict[str, Any] = {"snapshot": {}, "hub": []}
    upstream_root = tmp_path / "_upstream_cache"
    upstream_root.mkdir(parents=True, exist_ok=True)

    def _fake_snapshot_download(**kwargs: Any) -> str:
        captured["snapshot"] = kwargs
        local_dir = Path(kwargs["local_dir"])
        _write_awq_snapshot(local_dir)
        return str(local_dir)

    def _fake_hf_hub_download(**kwargs: Any) -> str:
        captured["hub"].append(kwargs)
        # Simulate HF's per-file cache by writing to a deterministic path.
        repo_id = kwargs["repo_id"].replace("/", "__")
        out = upstream_root / repo_id / kwargs["filename"]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "tokenizer_class": "Qwen2Tokenizer",
                    "chat_template": FAKE_UPSTREAM_TEMPLATE,
                }
            )
        )
        return str(out)

    module = _load_fetch_weights()
    monkeypatch.setattr(module, "snapshot_download", _fake_snapshot_download)
    monkeypatch.setattr(module, "hf_hub_download", _fake_hf_hub_download)
    return {"captured": captured, "module": module}


def test_defaults_use_adr_aligned_community_awq_repo(
    fake_download: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MODEL_TARGET_DIR", str(tmp_path / "weights"))
    monkeypatch.delenv("MODEL_HF_REPO", raising=False)
    monkeypatch.delenv("TEMPLATE_HF_REPO", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)

    rc = fake_download["module"].main()
    assert rc == 0

    snapshot = fake_download["captured"]["snapshot"]
    assert snapshot["repo_id"] == "cpatonn/Qwen3-Coder-30B-A3B-Instruct-AWQ-4bit"
    assert snapshot["local_dir"] == str(tmp_path / "weights")
    assert snapshot["token"] is None


def test_repo_id_override(
    fake_download: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MODEL_HF_REPO", "someorg/my-awq-fork")
    monkeypatch.setenv("MODEL_TARGET_DIR", str(tmp_path / "weights"))

    rc = fake_download["module"].main()
    assert rc == 0
    assert fake_download["captured"]["snapshot"]["repo_id"] == "someorg/my-awq-fork"


def test_hf_token_passthrough(
    fake_download: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HF_TOKEN", "hf_sekret")
    monkeypatch.setenv("MODEL_TARGET_DIR", str(tmp_path / "weights"))

    rc = fake_download["module"].main()
    assert rc == 0
    # Token must reach BOTH downloaders — snapshot for the AWQ repo and
    # hf_hub_download for the upstream template config.
    assert fake_download["captured"]["snapshot"]["token"] == "hf_sekret"
    assert fake_download["captured"]["hub"][0]["token"] == "hf_sekret"


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
        (local_dir / "tokenizer_config.json").write_text("{}")
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
        # No tokenizer.json or tokenizer_config.json
        return str(local_dir)

    monkeypatch.setattr(module, "snapshot_download", _fake_download_without_tokenizer)
    monkeypatch.setenv("MODEL_TARGET_DIR", str(tmp_path / "weights"))

    rc = module.main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "tokenizer.json" in err


def test_overlay_merges_upstream_chat_template(
    fake_download: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Happy path: AWQ tokenizer_config lacks chat_template → overlay from upstream.

    This is the regression test for the 2026-04-22 vLLM failure:
        'As of transformers v4.44, default chat template is no longer allowed...'
    """
    weight_dir = tmp_path / "weights"
    monkeypatch.setenv("MODEL_TARGET_DIR", str(weight_dir))

    rc = fake_download["module"].main()
    assert rc == 0

    # The overlay must hit the official Qwen repo by default (ADR-0013).
    hub_calls = fake_download["captured"]["hub"]
    assert len(hub_calls) == 1
    assert hub_calls[0]["repo_id"] == "Qwen/Qwen3-Coder-30B-A3B-Instruct"
    assert hub_calls[0]["filename"] == "tokenizer_config.json"

    # The merged tokenizer_config.json in the weight dir now carries the
    # upstream chat_template AND preserves the AWQ repo's original fields.
    merged = json.loads((weight_dir / "tokenizer_config.json").read_text())
    assert merged["chat_template"] == FAKE_UPSTREAM_TEMPLATE
    assert merged["tokenizer_class"] == "Qwen2Tokenizer"
    assert merged["model_max_length"] == 262144


def test_overlay_skipped_when_awq_already_ships_template(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """If a future AWQ rebuild restores chat_template, we must not clobber it."""
    module = _load_fetch_weights()

    def _fake_snapshot_with_template(**kwargs: Any) -> str:
        local_dir = Path(kwargs["local_dir"])
        _write_awq_snapshot(local_dir, with_template=True)
        return str(local_dir)

    hub_calls: list[dict[str, Any]] = []

    def _fake_hf_hub_download(**kwargs: Any) -> str:  # pragma: no cover - must not run
        hub_calls.append(kwargs)
        raise AssertionError("upstream overlay must not run when AWQ ships a template")

    monkeypatch.setattr(module, "snapshot_download", _fake_snapshot_with_template)
    monkeypatch.setattr(module, "hf_hub_download", _fake_hf_hub_download)
    weight_dir = tmp_path / "weights"
    monkeypatch.setenv("MODEL_TARGET_DIR", str(weight_dir))

    rc = module.main()
    assert rc == 0
    assert hub_calls == []
    merged = json.loads((weight_dir / "tokenizer_config.json").read_text())
    assert merged["chat_template"] == "{{ 'preexisting' }}"


def test_overlay_respects_template_repo_override(
    fake_download: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MODEL_TARGET_DIR", str(tmp_path / "weights"))
    monkeypatch.setenv("TEMPLATE_HF_REPO", "custom/template-source")

    rc = fake_download["module"].main()
    assert rc == 0
    hub_calls = fake_download["captured"]["hub"]
    assert hub_calls[0]["repo_id"] == "custom/template-source"


def test_overlay_fails_when_upstream_lacks_template(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """If the upstream itself doesn't ship a template, surface a clear error
    — don't silently produce an image that will 500 the first /chat call.
    """
    module = _load_fetch_weights()

    def _fake_snapshot_no_template(**kwargs: Any) -> str:
        local_dir = Path(kwargs["local_dir"])
        _write_awq_snapshot(local_dir, with_template=False)
        return str(local_dir)

    def _fake_hf_hub_download(**kwargs: Any) -> str:
        out = tmp_path / "upstream_tokenizer_config.json"
        out.write_text(json.dumps({"tokenizer_class": "Qwen2Tokenizer"}))
        return str(out)

    monkeypatch.setattr(module, "snapshot_download", _fake_snapshot_no_template)
    monkeypatch.setattr(module, "hf_hub_download", _fake_hf_hub_download)
    monkeypatch.setenv("MODEL_TARGET_DIR", str(tmp_path / "weights"))

    rc = module.main()
    assert rc == 1
    assert "no chat_template" in capsys.readouterr().err
