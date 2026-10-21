"""Sprite sheets in the formats engines read: a packed PNG, TexturePacker/Phaser JSON-hash with
Aseprite-style frame tags, a Godot 4 SpriteFrames resource, and an animated GIF preview."""

from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image


def pack_grid(frames: list[Image.Image], columns: int | None = None, padding: int = 0) -> tuple[Image.Image, list[tuple[int, int, int, int]]]:
    """Uniform cells (the largest frame), left-to-right, top-to-bottom."""
    if not frames:
        raise ValueError("no frames to pack")
    fw = max(f.width for f in frames)
    fh = max(f.height for f in frames)
    cols = columns or math.ceil(math.sqrt(len(frames)))
    rows = math.ceil(len(frames) / cols)
    sheet = Image.new("RGBA", (cols * (fw + padding), rows * (fh + padding)), (0, 0, 0, 0))
    rects = []
    for i, f in enumerate(frames):
        x, y = (i % cols) * (fw + padding), (i // cols) * (fh + padding)
        sheet.alpha_composite(f, (x + (fw - f.width) // 2, y + fh - f.height))
        rects.append((x, y, fw, fh))
    return sheet, rects


def pack_shelf(images: dict[str, Image.Image], max_width: int = 512, padding: int = 1) -> tuple[Image.Image, dict[str, tuple[int, int, int, int]]]:
    """Mixed sizes: tallest-first shelf packing (good enough for icon/prop atlases)."""
    order = sorted(images, key=lambda k: (-images[k].height, -images[k].width))
    x = y = shelf_h = 0
    placed: dict[str, tuple[int, int, int, int]] = {}
    for key in order:
        im = images[key]
        if x + im.width > max_width:
            x, y, shelf_h = 0, y + shelf_h + padding, 0
        placed[key] = (x, y, im.width, im.height)
        x += im.width + padding
        shelf_h = max(shelf_h, im.height)
    width = max(r[0] + r[2] for r in placed.values())
    height = max(r[1] + r[3] for r in placed.values())
    sheet = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for key, (px, py, _, _) in placed.items():
        sheet.alpha_composite(images[key], (px, py))
    return sheet, placed


def texturepacker_json(image_name: str, sheet: Image.Image, names: list[str],
                       rects: list[tuple[int, int, int, int]], anims: dict[str, list[int]] | None = None,
                       fps: int = 8) -> dict:
    """JSON-hash atlas (Phaser 3, PixiJS, Defold, most loaders) + ``meta.frameTags`` (Aseprite)."""
    frames = {}
    for name, (x, y, w, h) in zip(names, rects):
        frames[name] = {"frame": {"x": x, "y": y, "w": w, "h": h}, "rotated": False, "trimmed": False,
                        "spriteSourceSize": {"x": 0, "y": 0, "w": w, "h": h}, "sourceSize": {"w": w, "h": h},
                        "duration": int(1000 / fps)}
    tags = [{"name": k, "from": v[0], "to": v[-1], "direction": "forward", "frames": [names[i] for i in v]}
            for k, v in (anims or {}).items()]
    return {"frames": frames, "meta": {"app": "hermes-gameforge", "version": "1.0", "image": image_name,
                                       "format": "RGBA8888", "size": {"w": sheet.width, "h": sheet.height},
                                       "scale": "1", "frameTags": tags}}


def godot_spriteframes(texture_res_path: str, rects: list[tuple[int, int, int, int]],
                       anims: dict[str, list[int]], fps: float = 8.0, loop: bool = True) -> str:
    """Godot 4 SpriteFrames (.tres) built from AtlasTexture regions of one sheet."""
    used = sorted({i for frames in anims.values() for i in frames})
    lines = [f'[gd_resource type="SpriteFrames" load_steps={len(used) + 2} format=3]', "",
             f'[ext_resource type="Texture2D" path="{texture_res_path}" id="1_sheet"]', ""]
    for i in used:
        x, y, w, h = rects[i]
        lines += [f'[sub_resource type="AtlasTexture" id="AtlasTexture_{i}"]', 'atlas = ExtResource("1_sheet")',
                  f"region = Rect2({x}, {y}, {w}, {h})", ""]
    entries = []
    for name, frames in anims.items():
        frame_list = ", ".join('{"duration": 1.0, "texture": SubResource("AtlasTexture_%d")}' % i for i in frames)
        entries.append('{"frames": [%s], "loop": %s, "name": &"%s", "speed": %.1f}'
                       % (frame_list, "true" if loop else "false", name, fps))
    lines += ["[resource]", "animations = [" + ", ".join(entries) + "]", ""]
    return "\n".join(lines)


def gif_preview(frames: list[Image.Image], path: str | Path, scale: int = 4, fps: int = 8,
                background: tuple[int, int, int] = (40, 44, 60)) -> Path:
    path = Path(path)
    out = []
    for f in frames:
        bg = Image.new("RGBA", f.size, background + (255,))
        bg.alpha_composite(f)
        out.append(bg.convert("RGB").resize((f.width * scale, f.height * scale), Image.NEAREST))
    out[0].save(path, save_all=True, append_images=out[1:], duration=int(1000 / fps), loop=0, disposal=2)
    return path


def write_json(path: str | Path, data: dict) -> Path:
    path = Path(path)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path
