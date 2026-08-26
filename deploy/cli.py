from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from deploy.client_install import run as run_client_install
from deploy.detect import probe
from deploy.server_install import run as run_server_install
from deploy.tiers import Recommendation, recommend

InputFn = Callable[[str], str]


def confirm(recommendation: Recommendation, input_fn: InputFn = input) -> Recommendation:
    print(f"\nDetected tier: {recommendation.tier}")
    print(recommendation.reasoning)
    print(f"\n  model:      {recommendation.ollama_model}")
    print(f"  image-gen:  {'on' if recommendation.enable_image_gen else 'off'}")
    print(f"  tts:        {recommendation.tts_backend}")
    choice = input_fn("\nProceed with this configuration? [Y/n/customize]: ").strip().lower()
    if choice in ("", "y", "yes"):
        return recommendation
    if choice in ("n", "no"):
        raise SystemExit("Install cancelled.")

    model = input_fn(f"Ollama model [{recommendation.ollama_model}]: ").strip() or recommendation.ollama_model
    image_raw = input_fn(f"Enable image-gen? [{'Y/n' if recommendation.enable_image_gen else 'y/N'}]: ").strip().lower()
    enable_image_gen = image_raw.startswith("y") if image_raw else recommendation.enable_image_gen
    tts_raw = input_fn(f"TTS backend (kokoro/hosted/none) [{recommendation.tts_backend}]: ").strip() or recommendation.tts_backend
    return Recommendation(tier=recommendation.tier, ollama_model=model, enable_image_gen=enable_image_gen, tts_backend=tts_raw, reasoning=recommendation.reasoning)


def _install_server(input_fn: InputFn) -> int:
    profile = probe()
    recommendation = recommend(profile)
    confirmed = confirm(recommendation, input_fn)

    image_gen_repo_url = None
    if confirmed.enable_image_gen:
        image_gen_repo_url = input_fn(
            "Git URL for the (private) ultra-fast-image-gen repo [blank to skip image-gen]: "
        ).strip() or None

    tts_api_key = None
    if confirmed.tts_backend == "hosted":
        tts_api_key = input_fn("OpenAI API key for hosted TTS: ").strip()

    run_server_install(
        profile,
        confirmed,
        siblings_dir=Path.cwd().parent,
        units_dir=Path.home() / ".config" / "systemd" / "user",
        image_gen_repo_url=image_gen_repo_url,
        tts_api_key=tts_api_key,
    )
    print("Server install complete.")
    return 0


def _install_client(input_fn: InputFn) -> int:
    server_url = input_fn("Nightwire server WebSocket URL [ws://localhost:8000]: ").strip() or "ws://localhost:8000"
    run_client_install(server_url, Path.cwd() / "frontend")
    print("Client install complete.")
    return 0


def main(argv: list[str] | None = None, input_fn: InputFn = input) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="nightwire-deploy")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("detect")
    install_parser = sub.add_parser("install")
    install_parser.add_argument("--role", choices=["server", "client"], required=True)

    args = parser.parse_args(argv)

    if args.command == "detect":
        profile = probe()
        recommendation = recommend(profile)
        print(profile.model_dump_json(indent=2))
        print(recommendation.reasoning)
        return 0

    if args.role == "server":
        return _install_server(input_fn)
    return _install_client(input_fn)


if __name__ == "__main__":
    sys.exit(main())
