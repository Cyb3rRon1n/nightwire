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
            last_turn_had_image=data.get("last_turn_had_image", False),
            narrative_summary=data.get("narrative_summary", ""),
            narrative_summary_line_count=data.get("narrative_summary_line_count", 0),
            npc_memory=data.get("npc_memory", {}),
            pending_rolls=data.get("pending_rolls", {}),
            pending_chrome_offers=data.get("pending_chrome_offers", {}),
            pending_world_events=data.get("pending_world_events", []),
            recent_stakes=data.get("recent_stakes", []),
            phone=data.get("phone", {}),
            suggestions=data.get("suggestions", {}),
            present=data.get("present", []),
            cast_location=data.get("cast_location"),
            drop_in_turn=data.get("drop_in_turn"),
            last_moves=data.get("last_moves", {}),
            type_turns=data.get("type_turns", {}),
            copied_lines=data.get("copied_lines", []),
            voice_lines=data.get("voice_lines", []),
            promises=data.get("promises", []),
            journal=data.get("journal", []),
            last_turn=data.get("last_turn"),
            last_rating=data.get("last_rating"),
            checkin_open=data.get("checkin_open", False),
            checkin_turn=data.get("checkin_turn"),
            tension=data.get("tension", 0),
            breather=data.get("breather", 0),
            quiet_turns=data.get("quiet_turns", 0),
            events_used=data.get("events_used", {}),
            people=data.get("people", {}),
            places=data.get("places", {}),
            clocks=data.get("clocks", {}),
            trail=data.get("trail", []),
            deeds=data.get("deeds", []),
            gossip_turn=data.get("gossip_turn"),
            night=data.get("night", 1),
            stretch=data.get("stretch", 0),
            stretch_start=data.get("stretch_start"),
            clock_district=data.get("clock_district"),
            sleepers=data.get("sleepers", []),
        )
