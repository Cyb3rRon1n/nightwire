from typing import Literal

from engine.session import Session
from narrator.tts_backend import VoiceOption


def assign_voice(
    session: Session,
    speaker: str,
    gender: Literal["male", "female"] | None,
    voices: list[VoiceOption],
) -> str:
    if speaker in session.speaker_voices:
        return session.speaker_voices[speaker]

    candidates = [v for v in voices if v.gender == gender] if gender else []
    if not candidates:
        candidates = voices

    used = set(session.speaker_voices.values())
    unused = [v for v in candidates if v.id not in used]
    chosen = (unused or candidates)[0]

    session.speaker_voices[speaker] = chosen.id
    return chosen.id
