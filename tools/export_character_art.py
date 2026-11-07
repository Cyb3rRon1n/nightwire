"""Write the play screen's NPC portraits: one 256px JPG per approved character, into narrator/worlds/character_art/.

    python -m tools.export_character_art

Made from design-data/<slug>/portrait.png. Needs Pillow (the design extra). The server serves them at
/character-art/, and frontend/src/lib/nightwire/npcPalettes.ts (tools/export_npc_palettes.py) maps names to slugs.
"""
import tomllib
from pathlib import Path

from PIL import Image

ART_DIR = Path(__file__).resolve().parents[1] / "narrator" / "worlds" / "character_art"


def main() -> None:
    ART_DIR.mkdir(exist_ok=True)
    for toml in sorted(Path("narrator/worlds/designs").glob("*.toml")):
        d = tomllib.loads(toml.read_text())
        src = Path("design-data") / toml.stem / "portrait.png"
        if d.get("kind") != "character" or d.get("status") != "approved" or not src.exists():
            continue
        Image.open(src).convert("RGB").resize((256, 256), Image.LANCZOS).save(ART_DIR / f"{toml.stem}.jpg", quality=85, optimize=True)
        print(toml.stem)


if __name__ == "__main__":
    main()
