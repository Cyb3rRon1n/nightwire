"""Shorts studio: written shorts -> grey-box, prompts, takes, review, rough cut.
See docs/superpowers/specs/2026-11-08-shorts-studio-design.md."""

import os
from pathlib import Path

SHORTS_DIR = Path(__file__).resolve().parents[2] / "narrator" / "worlds" / "shorts"


def data_dir() -> Path:
    return Path(os.environ.get("NIGHTWIRE_DESIGN_DIR", "design-data")) / "shorts"
