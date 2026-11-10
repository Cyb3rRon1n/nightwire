"""A film is an ordered list of shorts (scenes): narrator/worlds/films/<slug>.toml.
title, character, logline, mood, scenes = ["short-slug", ...]"""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

FILMS_DIR = Path(__file__).resolve().parents[2] / "narrator" / "worlds" / "films"


def default_dir() -> Path:
    env = os.environ.get("NIGHTWIRE_FILMS_DIR")
    return Path(env) if env else FILMS_DIR


@dataclass
class Film:
    slug: str
    title: str
    character: str
    logline: str
    mood: str
    scenes: list[str]


def load_film(slug: str, films_dir: Path | None = None, shorts_dir: Path | None = None) -> Film:
    """Raises ValueError when the film is missing or names a scene (short) that does not exist."""
    from tools.shorts import SHORTS_DIR
    path = (films_dir or default_dir()) / f"{slug}.toml"
    if not path.exists():
        raise ValueError(f"no film {slug!r} at {path}")
    d = tomllib.loads(path.read_text())
    f = Film(slug, d["title"], d.get("character", ""), d.get("logline", ""), d.get("mood", ""), list(d.get("scenes", [])))
    root = shorts_dir or SHORTS_DIR
    problems = [] if f.scenes else ["scenes is empty"]
    problems += [f"scene {s!r} has no short at {root / s}" for s in f.scenes if not (root / s / "short.toml").exists()]
    if problems:
        raise ValueError(f"film {slug}: " + "; ".join(problems))
    return f
