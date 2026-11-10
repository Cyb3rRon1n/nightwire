"""Look book data (docs/look-book.md): film-grammar defaults, risk warnings for AI video, and why-line hints."""

from tools.shorts.model import SIZES, Shot, Short

CLOSE = ("MCU", "CU", "ECU")  # a face fills the frame: lip-sync and identity drift show most here
STATIC = ("", "static", "locked-off", "locked off", "none")
MAX_CAST = 2
MAX_LINES = 1

SIZE_FEEL = {
    "EWS": "the place is enormous and the person is tiny: awe, loneliness",
    "WS": "the whole body in its surroundings: a person belonging to a place",
    "MWS": "knees up: still part of the room, readable posture",
    "MS": "waist up: calm, conversational, the plain look at someone",
    "MCU": "chest up: close enough to read a mood",
    "CU": "face fills the frame: intimacy or pressure",
    "ECU": "one detail, an eye or a hand: tension",
}
MOVE_FEEL = {
    "static": "locked-off: the world is steady and we simply watch",
    "slow push-in": "drifting closer: attention narrows, feeling builds",
    "slow pan": "turning to reveal: the place unfolds",
}
FRAME_FEEL = (("behind", "seen from behind: we share their view"), ("profile", "in profile: thoughtful, a little apart"),
              ("silhouette", "a silhouette: shape and mood without a face"), ("reflect", "a reflection: a quiet second image"))
assert set(SIZE_FEEL) == set(SIZES)


def _is_static(shot: Shot) -> bool:
    return shot.move.strip().lower() in STATIC


def warnings(short: Short, shot: Shot) -> list[str]:
    out = []
    if shot.lines and shot.size in CLOSE:
        out.append(f"risk: talking face at {shot.size} (AI video drifts on close lip-sync; try WS/MS, a back or a profile)")
    if len(shot.lines) > MAX_LINES:
        out.append(f"risk: {len(shot.lines)} lines in one shot (keep to {MAX_LINES}; split across shots)")
    if len(shot.frame) > MAX_CAST:
        out.append(f"risk: {len(shot.frame)} people in frame (AI video handles {MAX_CAST} at most; keep extras tiny or away)")
    if not _is_static(shot) and shot.action.strip():
        out.append(f"risk: camera move ({shot.move}) plus character action (do one: lock the camera, or let the figure be still)")
    total = sum(len(s.lines) for s in short.shots)
    if short.shots and total > len(short.shots):
        out.append(f"risk: dialogue-heavy short ({total} lines in {len(short.shots)} shots); films work best with little talk")
    return out


def why_hint(shot: Shot) -> str:
    """A suggested why-line from size, move and framing; the owner or author edits it."""
    parts = [SIZE_FEEL.get(shot.size, "")]
    if (m := MOVE_FEEL.get(shot.move.strip().lower())):
        parts.append(m)
    text = " ".join(shot.frame.values()).lower()
    parts += [feel for key, feel in FRAME_FEEL if key in text]
    return "; ".join(p for p in parts if p)
