"""Write the play screen's place art: one 1600px JPG per approved place, into narrator/worlds/place_art/.

    python -m tools.export_place_art

Uses design-data/<slug>/play.png when the owner preferred another shot over the design's establishing shot,
else establishing.png. Needs Pillow (the design extra). The server serves the result at /place-art/.
"""
import tomllib
from pathlib import Path

from PIL import Image

from narrator.place_art import ART_DIR

DESIGNS = Path("narrator/worlds/designs")
DATA = Path("design-data")


def main() -> None:
    ART_DIR.mkdir(exist_ok=True)
    for toml in sorted(DESIGNS.glob("*.toml")):
        d = tomllib.loads(toml.read_text())
        if d.get("status") != "approved" or d.get("kind") == "character":
            continue
        src = next((p for p in (DATA / toml.stem / "play.png", DATA / toml.stem / "establishing.png") if p.exists()), None)
        if src is None:
            print(f"{toml.stem}: no image, skipped")
            continue
        im = Image.open(src).convert("RGB")
        im.thumbnail((1600, 1600))
        im.save(ART_DIR / f"{toml.stem}.jpg", quality=84, optimize=True)
        print(f"{toml.stem}: {src.name}")


if __name__ == "__main__":
    main()
