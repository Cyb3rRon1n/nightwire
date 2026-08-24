import json
from dataclasses import asdict
from pathlib import Path

from engine.character import CharacterSheet
from engine.session import Session


class SessionStoreUnwritable(Exception):
    pass


class JSONFileSessionStore:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self._check_writable()

    def _check_writable(self) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            probe = self.directory / ".write_probe"
            probe.write_text("")
            probe.unlink()
        except OSError as e:
            raise SessionStoreUnwritable(
                f"Session store directory {self.directory} is not writable: {e}"
            ) from e

    def _path_for(self, session_id: str) -> Path:
        if not session_id or "/" in session_id or session_id in (".", ".."):
            raise ValueError(f"invalid session_id: {session_id!r}")
        return self.directory / f"{session_id}.json"

    def save(self, session: Session) -> None:
        self._path_for(session.session_id).write_text(json.dumps(asdict(session), indent=2))

    def load(self, session_id: str) -> Session | None:
        path = self._path_for(session_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        characters = {
            player_id: CharacterSheet(**character_data)
            for player_id, character_data in data["characters"].items()
        }
        return Session(
            session_id=data["session_id"],
            characters=characters,
            turn_order=data["turn_order"],
            current_turn_index=data["current_turn_index"],
            in_combat=data["in_combat"],
            pre_combat_turn_order=data["pre_combat_turn_order"],
            log=data["log"],
            location=data["location"],
            scene_mood=data["scene_mood"],
            active_objectives=data["active_objectives"],
            speaker_voices=data.get("speaker_voices", {}),
            pending_initiative=data.get("pending_initiative", {}),
        )
