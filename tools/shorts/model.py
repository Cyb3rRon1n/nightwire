"""A short is one TOML (cast, room, figures on one shared timeline) plus one TOML per shot."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

TIERS = ("capsule", "mannequin", "rigged")
DISFLUENCIES = ("", "block", "repeat", "silence", "self-correct")
MAX_SHOT_S = 30.0


@dataclass
class Line:
    who: str
    t: float
    text: str
    early_s: float = 0.0
    overlap_s: float = 0.0
    disfluency: str = ""
    on_word: str = ""


@dataclass
class Acting:
    who: str
    t: tuple[float, float]
    goal: str
    emotion: str
    trigger: str = ""
    face: str = ""
    gaze: str = ""
    voice: str = ""
    end: str = ""


@dataclass
class Beat:
    t: tuple[float, float]
    text: str


@dataclass
class CameraKey:
    t: float
    at: tuple[float, float, float]
    look: tuple[float, float, float]


@dataclass
class Shot:
    id: str
    start: float
    end: float
    summary: str
    lens: float
    camera: list[CameraKey]
    state: dict[str, str] = field(default_factory=dict)
    beats: list[Beat] = field(default_factory=list)
    acting: list[Acting] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    model: str = ""

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)


@dataclass
class Block:
    name: str
    size: tuple[float, float, float]
    at: tuple[float, float, float]
    rot: float = 0.0


@dataclass
class Figure:
    id: str
    tier: str
    pose: str
    keys: list[tuple[float, float, float, float]]


@dataclass
class Short:
    slug: str
    title: str
    logline: str
    place: str
    style: str
    budget_usd: float
    cast: dict[str, str]
    beats: list[str]
    blocks: list[Block]
    figures: dict[str, Figure]
    shots: list[Shot]


def _shot(d: dict) -> Shot:
    return Shot(
        id=d["id"], start=float(d["start"]), end=float(d["end"]), summary=d["summary"], lens=float(d.get("lens", 35.0)),
        camera=[CameraKey(float(k["t"]), tuple(k["at"]), tuple(k["look"])) for k in d["camera"]],
        state=dict(d.get("state", {})),
        beats=[Beat(tuple(b["t"]), b["text"]) for b in d.get("beats", [])],
        acting=[Acting(**{**a, "t": tuple(a["t"])}) for a in d.get("acting", [])],
        lines=[Line(**ln) for ln in d.get("lines", [])],
        model=d.get("model", ""),
    )


def load_short(folder: Path) -> Short:
    d = tomllib.loads((folder / "short.toml").read_text())
    return Short(
        slug=folder.name, title=d["title"], logline=d.get("logline", ""), place=d["place"], style=d.get("style", ""),
        budget_usd=float(d.get("budget_usd", 25.0)), cast=dict(d["cast"]), beats=list(d.get("beats", [])),
        blocks=[Block(b["name"], tuple(b["size"]), tuple(b["at"]), float(b.get("rot", 0.0)))
                for b in d.get("room", {}).get("blocks", [])],
        figures={cid: Figure(cid, f["tier"], f.get("pose", "stand"), [tuple(map(float, k)) for k in f["keys"]])
                 for cid, f in d.get("figures", {}).items()},
        shots=[_shot(tomllib.loads(p.read_text())) for p in sorted((folder / "shots").glob("*.toml"))],
    )


def validate_short(s: Short, designs: dict) -> list[str]:
    problems = []
    for cid, slug in s.cast.items():
        d = designs.get(slug)
        if d is None:
            problems.append(f"{cid}: no design {slug}")
        elif d.status != "approved":
            problems.append(f"{cid}: {slug} is not approved")
    place = designs.get(s.place)
    if place is None or place.kind != "location":
        problems.append(f"place {s.place} is not a location design")
    for cid, f in s.figures.items():
        if cid not in s.cast:
            problems.append(f"figure: unknown cast id {cid}")
        if f.tier not in TIERS:
            problems.append(f"figure {cid}: tier {f.tier!r} not in {TIERS}")
    for shot in s.shots:
        where = f"shot {shot.id}"
        if shot.duration <= 0 or shot.duration > MAX_SHOT_S:
            problems.append(f"{where}: {shot.duration}s is empty or longer than 30 s")
        if len(shot.camera) < 1:
            problems.append(f"{where}: needs at least one camera key")
        ids = [ln.who for ln in shot.lines] + [a.who for a in shot.acting] + list(shot.state)
        for cid in ids:
            if cid not in s.cast:
                problems.append(f"{where}: unknown cast id {cid}")
        for ln in shot.lines:
            if ln.disfluency not in DISFLUENCIES:
                problems.append(f"{where}: disfluency {ln.disfluency!r} not in {DISFLUENCIES}")
            if not shot.start <= ln.t <= shot.end:
                problems.append(f"{where}: line at {ln.t}s is outside the shot")
    return problems
