"""Download AWQ int4 weights for Qwen3-Coder-30B-A3B-Instruct at image-build time.

This script runs inside the weight-downloader Dockerfile stage. It is NOT part
of the runtime container — the downloaded files are copied across via
`COPY --from=...`.

The weights are baked into the image (rather than pulled at container start)
because:
  * Cloud Run GPU cold starts are already 20-60 s (ADR-0011). Adding an
    internet download step at startup would introduce an unbounded extra
    failure mode (HF 5xx, rate limits, outbound throttling).
  * The AWQ weights are ~17 GiB — large, but still well under Cloud Run's
    container-image size budget. Image-pull bandwidth from Artifact Registry
    stays within the same GCP region as the Cloud Run service and is
    typically faster + more reliable than HF egress.
  * Rebuilding the image when we change model versions is an acceptable cost;
    we change models rarely and track each change via an ADR (CLAUDE.md §2).

Chat-template overlay (added 2026-04-22):
  The community AWQ repo (cpatonn/...) strips `chat_template` from
  `tokenizer_config.json` during quantization. Without a chat template,
  vLLM (via transformers >=4.44) refuses to format messages and `/chat`
  returns 500 with:
      "As of transformers v4.44, default chat template is no longer allowed,
       so you must provide a chat template if the tokenizer does not define
       one."
  Fix: after the AWQ snapshot download, pull `tokenizer_config.json` from
  the official upstream (Qwen/Qwen3-Coder-30B-A3B-Instruct by default), copy
  its `chat_template` field into the AWQ `tokenizer_config.json`, and write
  it back. Keeps the template coupled to the weight dir — one overlay, one
  source of truth at runtime.

Env vars honoured at build time (passed via Docker --build-arg):
  MODEL_HF_REPO  — HF repo id of the AWQ build. Default is a community repo
                   because no official Qwen/*-AWQ build exists for this model
                   (ADR-0013 only specifies "AWQ int4 variant from HF").
  MODEL_TARGET_DIR — local directory the weights are written to; this path
                    is what /entrypoint.sh references at runtime.
  TEMPLATE_HF_REPO — HF repo id to source the chat_template from when the
                     AWQ repo is missing it. Default is the official Qwen
                     repo (ADR-0013).
  HF_TOKEN       — optional, only needed for gated repos (not required for
                   the current default). If used, passed via Docker secret,
                   never baked into an image layer.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download


def _ensure_chat_template(
    target_dir: Path,
    template_repo_id: str,
    token: str | None,
) -> int:
    """Ensure `target_dir/tokenizer_config.json` has a non-empty `chat_template`.

    If the AWQ repo's tokenizer_config already carries one, do nothing.
    Otherwise fetch it from `template_repo_id` and merge it in-place.

    Returns 0 on success, 1 on any failure the runtime image shouldn't be
    allowed to inherit.
    """
    tokenizer_config_path = target_dir / "tokenizer_config.json"
    if not tokenizer_config_path.exists():
        print(
            f"[fetch_weights] ERROR: {tokenizer_config_path} missing after download",
            file=sys.stderr,
        )
        return 1

    with tokenizer_config_path.open("r", encoding="utf-8") as fh:
        awq_cfg = json.load(fh)

    if awq_cfg.get("chat_template"):
        print("[fetch_weights] AWQ repo already ships chat_template — no overlay needed.")
        return 0

    print(
        f"[fetch_weights] AWQ repo missing chat_template; overlaying from {template_repo_id}"
    )
    upstream_path = Path(
        hf_hub_download(
            repo_id=template_repo_id,
            filename="tokenizer_config.json",
            token=token,
        )
    )
    with upstream_path.open("r", encoding="utf-8") as fh:
        upstream_cfg = json.load(fh)

    template = upstream_cfg.get("chat_template")
    if not template:
        print(
            f"[fetch_weights] ERROR: upstream {template_repo_id} has no chat_template",
            file=sys.stderr,
        )
        return 1

    awq_cfg["chat_template"] = template
    with tokenizer_config_path.open("w", encoding="utf-8") as fh:
        json.dump(awq_cfg, fh, ensure_ascii=False, indent=2)

    print(
        f"[fetch_weights] wrote chat_template ({len(template)} chars) into "
        f"{tokenizer_config_path}"
    )
    return 0


def main() -> int:
    repo_id = os.environ.get(
        "MODEL_HF_REPO",
        "cpatonn/Qwen3-Coder-30B-A3B-Instruct-AWQ-4bit",
    )
    target_dir = Path(
        os.environ.get("MODEL_TARGET_DIR", "/models/qwen3-coder-30b-a3b-instruct-awq")
    )
    template_repo_id = os.environ.get(
        "TEMPLATE_HF_REPO",
        "Qwen/Qwen3-Coder-30B-A3B-Instruct",
    )
    token = os.environ.get("HF_TOKEN") or None

    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"[fetch_weights] repo_id       = {repo_id}")
    print(f"[fetch_weights] target        = {target_dir}")
    print(f"[fetch_weights] template_repo = {template_repo_id}")
    print(f"[fetch_weights] hf_token      = {'<set>' if token else '<unset>'}")
    print(f"[fetch_weights] hf_transfer   = {os.environ.get('HF_HUB_ENABLE_HF_TRANSFER', '<unset>')}")

    # Only pull the weight + tokenizer files we actually need at runtime.
    # Skip README / images / any extra junk the uploader may have added, so
    # the baked image stays as lean as possible.
    allow_patterns = [
        "*.safetensors",
        "*.json",
        "*.txt",
        "tokenizer*",
        "*.model",
    ]

    path = snapshot_download(
        repo_id=repo_id,
        local_dir=str(target_dir),
        allow_patterns=allow_patterns,
        token=token,
        # Ignore symlinks — Cloud Run runs on overlayfs; real files are safer.
        local_dir_use_symlinks=False,
    )
    print(f"[fetch_weights] downloaded to: {path}")

    # Sanity-check: tokenizer + at least one safetensors shard must be present,
    # otherwise the vLLM server will fail in a much less readable way at
    # runtime.
    required = ["config.json", "tokenizer.json", "tokenizer_config.json"]
    missing = [name for name in required if not (target_dir / name).exists()]
    if missing:
        print(
            f"[fetch_weights] ERROR: required files not found in download: {missing}",
            file=sys.stderr,
        )
        return 1

    if not list(target_dir.glob("*.safetensors")):
        print(
            "[fetch_weights] ERROR: no *.safetensors files found in download",
            file=sys.stderr,
        )
        return 1

    rc = _ensure_chat_template(target_dir, template_repo_id, token)
    if rc != 0:
        return rc

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
