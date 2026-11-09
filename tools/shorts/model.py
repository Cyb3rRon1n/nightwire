"""A short is one TOML (cast, room, figures on one shared timeline) plus one TOML per shot."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

TIERS = ("capsule", "mannequin", "rigged")
DISFLUENCIES = ("", "block", "repeat", "silence", "self-correct")
MAX_SHOT_S = 30.0
# Shot sizes, closest first. ECU extreme close-up, CU close-up, MCU medium close-up (chest up), MS medium (waist up),
# MWS medium wide (knees up), WS wide (whole body), EWS extreme wide (the place dominates).
SIZES = ("ECU", "CU", "MCU", "MS", "MWS", "WS", "EWS")


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
    size: str = ""
    angle: str = ""
    move: str = ""
    action: str = ""
    frame: dict[str, str] = field(default_factory=dict)      # who is in frame and where, at the cut
    at_start: dict[str, str] = field(default_factory=dict)   # pose / gaze / hands when the shot opens
    at_end: dict[str, str] = field(default_factory=dict)     # ... and when it cuts
    props: dict[str, str] = field(default_factory=dict)      # what each character holds, and in which hand
    prop_change: list[str] = field(default_factory=list)     # cast ids whose props change on purpose in this shot
    cross_ok: bool = False                                   # a deliberate crossing of the screen-direction line

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
    line_rule: str = ""
    model: str = ""
    locks: dict[str, str] = field(default_factory=dict)
    retry_cap: int = 2


def _shot(d: dict) -> Shot:
    return Shot(
        id=d["id"], start=float(d["start"]), end=float(d["end"]), summary=d["summary"], lens=float(d.get("lens", 35.0)),
        camera=[CameraKey(float(k["t"]), tuple(k["at"]), tuple(k["look"])) for k in d["camera"]],
        state=dict(d.get("state", {})),
        beats=[Beat(tuple(b["t"]), b["text"]) for b in d.get("beats", [])],
        acting=[Acting(**{**a, "t": tuple(a["t"])}) for a in d.get("acting", [])],
        lines=[Line(**ln) for ln in d.get("lines", [])],
        model=d.get("model", ""),
        size=d.get("size", ""), angle=d.get("angle", ""), move=d.get("move", ""), action=d.get("action", ""),
        frame=dict(d.get("frame", {})), at_start=dict(d.get("at_start", {})), at_end=dict(d.get("at_end", {})),
        props=dict(d.get("props", {})), prop_change=list(d.get("prop_change", [])), cross_ok=d.get("cross_ok", False),  # raw: validate_short rejects non-bools ("false" would be truthy)
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
        line_rule=d.get("line_rule", ""), model=d.get("model", ""), locks=dict(d.get("locks", {})),
        retry_cap=int(d.get("retry_cap", 2)),
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
        for k in shot.camera:
            if not 0 <= k.t <= shot.duration:
                problems.append(f"{where}: camera key at {k.t}s is outside 0..{shot.duration}s (camera times are relative to the shot start)")
        ids = ([ln.who for ln in shot.lines] + [a.who for a in shot.acting] + list(shot.state) + list(shot.frame)
               + list(shot.at_start) + list(shot.at_end) + list(shot.props) + list(shot.prop_change))
        for cid in ids:
            if cid not in s.cast:
                problems.append(f"{where}: unknown cast id {cid}")
        if not isinstance(shot.cross_ok, bool):
            problems.append(f"{where}: cross_ok must be true or false")
        if shot.size and shot.size not in SIZES:
            problems.append(f"{where}: size {shot.size!r} not in {SIZES}")
        for ln in shot.lines:
            if ln.disfluency not in DISFLUENCIES:
                problems.append(f"{where}: disfluency {ln.disfluency!r} not in {DISFLUENCIES}")
            if not shot.start <= ln.t <= shot.end:
                problems.append(f"{where}: line at {ln.t}s is outside the shot")
    return problems
