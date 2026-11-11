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
MODES = ("i2v", "reference")


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
class Scene:
    time: str
    weather: str
    set: str
    light: list[str]
    not_visible: list[str]


def scene_text(short) -> str:
    """The scene bible exactly as every shot sends it."""
    s = short.scene
    if s is None:
        return ""
    return " ".join([f"Time: {s.time}.", f"Weather: {s.weather}.", f"Set: {s.set}.",
                     f"Light: {'; '.join(s.light)}." if s.light else "",
                     f"Not visible: {', '.join(s.not_visible)}." if s.not_visible else ""]).strip()


def scene_look(short) -> str:
    """The scene bible without its "Not visible" sentence: what a plate prompt may describe."""
    s = short.scene
    if s is None:
        return ""
    return " ".join([f"Time: {s.time}.", f"Weather: {s.weather}.", f"Set: {s.set}.",
                     f"Light: {'; '.join(s.light)}." if s.light else ""]).strip()


def scene_mood(short) -> str:
    """Time, weather and light sources only (no "Set:"): for plates whose own tags say what the room shows."""
    s = short.scene
    if s is None:
        return ""
    return " ".join([f"Time: {s.time}.", f"Weather: {s.weather}.",
                     f"Light: {'; '.join(s.light)}." if s.light else ""]).strip()


@dataclass
class Board:
    """One figure on one draft board: [[board]] in a shot TOML. pose/camera name cells of the grey-box library."""
    which: str                  # "start" or "end" keyframe
    figure: str                 # cast id
    pose: str
    camera: str
    feet: tuple[float, float]   # 0..1 of the frame; y > 1 = below it (close shots: the floor is out of frame)
    height: float | None        # figure height, 0..1 of the frame; None = from the plate's camera (plate_camera.py)
    hidden_below: float | None = None  # frame y (0..1) below which the plate's foreground (counter, rail) hides the figure
    keep_props: bool = False    # also draw the library cell's own props (stool, rail); off: the plate has the real ones


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
    plate: str = ""                                          # name of the location plate this shot is framed on
    mode: str = "i2v"                                        # "i2v" (image to video) or "reference"
    motion: str = ""                                         # what moves in the shot, in plain words
    end_frame: bool = False                                  # render toward a fixed last frame
    wardrobe_change: list[str] = field(default_factory=list) # cast ids whose wardrobe changes on purpose in this shot
    blocking_change: bool = False                            # the blocking (who sits or stands where) changes in this shot
    boards: list[Board] = field(default_factory=list)        # draft-board figures per keyframe
    why: str = ""                                            # one line: the cinematographic reason for this shot
    vertical: float = 0.5                                    # x centre (0..1) of the 9:16 crop window

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
    scene: Scene | None = None
    wardrobe: dict[str, str] = field(default_factory=dict)
    blocking: dict[str, str] = field(default_factory=dict)
    avoid: list[str] = field(default_factory=list)  # extra keyframe negatives for this short


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
        plate=d.get("plate", ""), mode=d.get("mode", "i2v"), motion=d.get("motion", ""),
        end_frame=d.get("end_frame", False), wardrobe_change=list(d.get("wardrobe_change", [])),
        blocking_change=d.get("blocking_change", False),
        boards=[Board(b["which"], b["figure"], b["pose"], b["camera"], tuple(map(float, b["feet"])),
                             float(b["height"]) if "height" in b else None,
                             float(b["hidden_below"]) if "hidden_below" in b else None, bool(b.get("keep_props", False)))
                for b in d.get("board", [])],
        why=d.get("why", ""), vertical=float(d.get("vertical", [0.5])[0]),
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
        scene=Scene(**{"light": [], "not_visible": [], **d["scene"]}) if "scene" in d else None,
        wardrobe=dict(d.get("wardrobe", {})), blocking=dict(d.get("blocking", {})),
        avoid=list(d.get("avoid", [])),
    )


def _board_problems(s: "Short", shot: Shot, where: str) -> list[str]:
    from tools.greybox_library import presets
    out = []
    for b in shot.boards:
        tag = f"{where}: board {b.which} {b.figure}"
        if b.which not in ("start", "end"):
            out.append(f"{tag}: which must be start or end")
        if b.figure not in s.cast:
            out.append(f"{tag}: figure is not a cast id")
        if b.pose not in presets.POSES:
            out.append(f"{tag}: pose {b.pose!r} is not in the grey-box library")
        if b.camera not in presets.CAMERAS:
            out.append(f"{tag}: camera {b.camera!r} is not in the grey-box library")
        if len(b.feet) != 2 or not (0 <= b.feet[0] <= 1 and 0 <= b.feet[1] <= 2):
            out.append(f"{tag}: feet must be [x, y], x 0..1, y 0..2 (above 1 = below the frame, for close shots)")
        if b.height is not None and not 0 < b.height <= 1:
            out.append(f"{tag}: height must be above 0 and at most 1")
    return out


def wardrobe_state(short, designs: dict, cid: str) -> str | None:
    """The design wardrobe state a short's [wardrobe] value names, or None when it is free text."""
    d = designs.get(short.cast.get(cid, ""))
    v = short.wardrobe.get(cid, "")
    return v if v in (getattr(d, "wardrobe", None) or {}) else None


def wardrobe_text(short, designs: dict, cid: str) -> str:
    """What the prompt says the character wears: the state's text, else the free text as written."""
    st = wardrobe_state(short, designs, cid)
    return designs[short.cast[cid]].wardrobe[st].text if st else short.wardrobe[cid]


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
    for cid, v in s.wardrobe.items():
        if cid not in s.cast:
            problems.append(f"wardrobe: unknown cast id {cid}")
        elif (have := sorted(getattr(designs.get(s.cast[cid]), "wardrobe", None) or {})) and v not in have:
            problems.append(f"wardrobe {cid}: {v!r} is not a wardrobe state of {s.cast[cid]} (states: {', '.join(have)}); free text is only for designs without states")
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
               + list(shot.at_start) + list(shot.at_end) + list(shot.props) + list(shot.prop_change) + shot.wardrobe_change)
        for cid in ids:
            if cid not in s.cast:
                problems.append(f"{where}: unknown cast id {cid}")
        if not isinstance(shot.cross_ok, bool):
            problems.append(f"{where}: cross_ok must be true or false")
        if shot.size and shot.size not in SIZES:
            problems.append(f"{where}: size {shot.size!r} not in {SIZES}")
        if shot.mode not in MODES:
            problems.append(f"{where}: mode {shot.mode!r} not in {MODES}")
        if not isinstance(shot.end_frame, bool) or not isinstance(shot.blocking_change, bool):
            problems.append(f"{where}: end_frame and blocking_change must be true or false")
        if not 0 <= shot.vertical <= 1:
            problems.append(f"{where}: vertical must be between 0 and 1")
        problems += _board_problems(s, shot, where)
        for ln in shot.lines:
            if ln.disfluency not in DISFLUENCIES:
                problems.append(f"{where}: disfluency {ln.disfluency!r} not in {DISFLUENCIES}")
            if not shot.start <= ln.t <= shot.end:
                problems.append(f"{where}: line at {ln.t}s is outside the shot")
    return problems
