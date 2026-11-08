"""Static /shorts/ page: floor plan, previews, grey-box and takes per shot; verdicts go to the
existing design-picks images API, so no new server is needed."""

import json
import shutil
from pathlib import Path

from tools.shorts.takes import take_image_id

HTML = Path(__file__).with_name("page.html")


def collect(work_root: Path, titles: dict[str, tuple[str, float]], notes: dict[str, dict] | None = None) -> list[dict]:
    """notes: optional {slug: {"logline", "cast", "shots": {shot_id: {"time", "summary", "beats"}}}} shown to the reviewer."""
    notes = notes or {}
    out = []
    for w in sorted(p for p in work_root.iterdir() if (p / "scene.json").exists()):
        slug = w.name
        costs = json.loads((w / "costs.json").read_text()) if (w / "costs.json").exists() else []
        title, budget = titles.get(slug, (slug, 25.0))
        shots = []
        for sd in sorted((w / "shots").iterdir()) if (w / "shots").exists() else []:
            rel = f"{slug}/shots/{sd.name}"
            takes = []
            for t in sorted((sd / "takes").glob("t*.mp4")):
                meta = json.loads(t.with_suffix(".json").read_text()) if t.with_suffix(".json").exists() else {}
                takes.append({"id": t.stem, "image_id": take_image_id(slug, sd.name, t.stem), "src": f"{rel}/takes/{t.name}",
                              "model": meta.get("model", ""), "cost": meta.get("cost", 0)})
            shots.append({"id": sd.name, **notes.get(slug, {}).get("shots", {}).get(sd.name, {}), "greybox": f"{rel}/greybox.mp4" if (sd / "greybox.mp4").exists() else "",
                          "previews": [f"{rel}/preview/{p.name}" for p in sorted((sd / "preview").glob("*.png"))]
                          if (sd / "preview").exists() else [], "takes": takes})
        info = notes.get(slug, {})
        out.append({"slug": slug, "title": title, "logline": info.get("logline", ""), "cast": info.get("cast", {}), "budget": budget, "spent": round(sum(c["cost"] for c in costs), 2),
                    "floorplan": f"{slug}/floorplan.png" if (w / "floorplan.png").exists() else "",
                    "draft": f"{slug}/draft.mp4" if (w / "draft.mp4").exists() else "", "shots": shots})
    return out


def build(work_root: Path, site: Path, titles: dict[str, tuple[str, float]], notes: dict[str, dict] | None = None) -> Path:
    entries = collect(work_root, titles, notes)
    site.mkdir(parents=True, exist_ok=True)
    for e in entries:
        for rel in [e["floorplan"], e["draft"]] + [x for s in e["shots"] for x in [s["greybox"], *s["previews"], *(t["src"] for t in s["takes"])]]:
            if rel:
                dst = site / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(work_root / rel, dst)
    (site / "shorts.json").write_text(json.dumps(entries, indent=1))
    shutil.copyfile(HTML, site / "index.html")
    return site
