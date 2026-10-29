"""Write Nightwire presets into ComfyUI's Workflows sidebar (editor format, labelled nodes).

    python -m tools.comfy_presets --out <comfyui>/user/default/workflows
"""
import argparse
import json
import urllib.request
from pathlib import Path

from tools.imagegen import build

EXAMPLES = {
    "scene": "rainy neon alley, izakaya, paper lanterns, wet street, steam",
    "portrait": "1girl, mature female, slender, beautiful face, idol, black hair, long hair, leather jacket, choker, smirk",
    "character": "1girl, mature female, slender, narrow waist, long legs, beautiful face, idol, black hair, leather bodysuit, "
                 "character sheet, turnaround, multiple views, front view, from side, from behind, full body",
    "plain": "rooftop bar, neon signs, city skyline, rain",
}
SIZES = {"scene": ("base", "1080p", "4k", "ultrawide", "phone"), "portrait": ("portrait",),
         "character": ("base", "4k"), "plain": ("base", "1080p", "4k", "ultrawide", "phone")}
TITLES = {"6": "Positive prompt (edit me)", "7": "Negative prompt", "3": "Sampler (seed here)", "5": "Image size",
          "41": "Final wallpaper size", "9": "Save image"}


def to_editor(api: dict, info: dict) -> dict:
    ids = {k: i + 1 for i, k in enumerate(sorted(api, key=int))}
    nodes, links, link_id = [], [], 0
    outs = {}
    for k in sorted(api, key=int):
        node, spec = api[k], info[api[k]["class_type"]]
        order = spec.get("input_order", {})
        names = order.get("required", list(spec["input"].get("required", {}))) + order.get("optional", [])
        allspec = {**spec["input"].get("required", {}), **spec["input"].get("optional", {})}
        inputs, widgets = [], []
        for name in names:
            v = node["inputs"].get(name)
            typ = allspec[name][0]
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                link_id += 1
                src, slot = v
                links.append([link_id, ids[src], slot, ids[k], len(inputs), info[api[src]["class_type"]]["output"][slot]])
                outs.setdefault((src, slot), []).append(link_id)
                inputs.append({"name": name, "type": typ if isinstance(typ, str) else "COMBO", "link": link_id})
            elif v is not None:
                widgets.append(v)
                if name in ("seed", "noise_seed"):
                    widgets.append("fixed")
        nodes.append({"id": ids[k], "type": node["class_type"], "pos": [0, 0], "size": [400, 200], "flags": {},
                      "order": ids[k], "mode": 0, "inputs": inputs, "outputs": [],
                      "properties": {"Node name for S&R": node["class_type"]}, "widgets_values": widgets,
                      "title": TITLES.get(k, node["class_type"])})
    for n, k in zip(nodes, sorted(api, key=int)):
        spec = info[api[k]["class_type"]]
        n["outputs"] = [{"name": nm, "type": t, "links": outs.get((k, i), []), "slot_index": i}
                        for i, (nm, t) in enumerate(zip(spec.get("output_name", spec["output"]), spec["output"]))]
    # simple left-to-right layout by dependency depth
    depth = {}
    def d(k):
        if k not in depth:
            srcs = [v[0] for v in api[k]["inputs"].values() if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str)]
            depth[k] = 1 + max((d(s) for s in srcs), default=-1)
        return depth[k]
    rows = {}
    for n, k in zip(nodes, sorted(api, key=int)):
        col = d(k); r = rows.get(col, 0); rows[col] = r + 1
        n["pos"] = [col * 460, r * 260]
        if k in ("6", "7"):
            n["size"] = [440, 220]
    return {"last_node_id": len(nodes), "last_link_id": link_id, "nodes": nodes, "links": links, "groups": [],
            "config": {}, "extra": {}, "version": 0.4}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--comfyui-url", default="http://192.168.10.19:8188")
    a = p.parse_args()
    info = json.loads(urllib.request.urlopen(a.comfyui_url.rstrip("/") + "/object_info", timeout=60).read())
    a.out.mkdir(parents=True, exist_ok=True)
    for kind, sizes in SIZES.items():
        for size in sizes:
            api = build(EXAMPLES[kind], kind, False, "", size, 424242)
            (a.out / f"Nightwire - {kind.title()} - {size}.json").write_text(json.dumps(to_editor(api, info), indent=1))
            print(kind, size)


if __name__ == "__main__":
    main()
