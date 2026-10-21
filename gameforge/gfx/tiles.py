"""Tilesets: seamless terrain textures (with animated water and lava), Wang 2-corner transitions
between any two terrains, map props, and Godot 4 TileSet resources with terrain peering bits so
the editor's terrain painter autotiles them out of the box."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PIL import Image

from . import palette as pal
from .canvas import Grid, render

T = 16


@dataclass(frozen=True)
class Terrain:
    hue: float
    sat: float
    val: float
    scale: int  # noise cell size; must divide T for seamless tiling
    feature: str = ""
    animated: bool = False
    solid: bool = False


TERRAINS: dict[str, Terrain] = {
    "grass": Terrain(0.30, 0.65, 0.72, 8, "blades"),
    "dirt": Terrain(0.07, 0.55, 0.58, 8, "pebbles"),
    "sand": Terrain(0.11, 0.45, 0.92, 8, "speckle"),
    "water": Terrain(0.57, 0.7, 0.85, 8, "waves", animated=True, solid=True),
    "deep_water": Terrain(0.62, 0.75, 0.6, 8, "waves", animated=True, solid=True),
    "stone": Terrain(0.62, 0.1, 0.62, 8, "cracks"),
    "snow": Terrain(0.58, 0.08, 1.0, 8, "speckle"),
    "lava": Terrain(0.03, 0.9, 1.0, 8, "bubbles", animated=True, solid=True),
    "wood": Terrain(0.08, 0.6, 0.65, 4, "planks"),
    "brick": Terrain(0.02, 0.5, 0.6, 4, "bricks", solid=True),
    "dungeon": Terrain(0.7, 0.2, 0.42, 4, "flagstones"),
    "void": Terrain(0.7, 0.4, 0.12, 8, "", solid=True),
}


def _value_noise(seed: int, cell: int, x: float, y: float) -> float:
    """Periodic (period T) value noise in [0, 1] with smoothstep interpolation."""
    n = T // cell
    gx, gy = x / cell, y / cell
    x0, y0 = int(math.floor(gx)), int(math.floor(gy))
    fx, fy = gx - x0, gy - y0
    sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)

    def h(ix: int, iy: int) -> float:
        return random.Random(hash((seed, ix % n, iy % n)) & 0xFFFFFFFF).random()

    top = h(x0, y0) + (h(x0 + 1, y0) - h(x0, y0)) * sx
    bot = h(x0, y0 + 1) + (h(x0 + 1, y0 + 1) - h(x0, y0 + 1)) * sx
    return top + (bot - top) * sy


def _fbm(seed: int, terrain: Terrain, x: float, y: float) -> float:
    a = _value_noise(seed, terrain.scale, x, y)
    b = _value_noise(seed + 1, max(2, terrain.scale // 2), x, y)
    return a * 0.7 + b * 0.3


_BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def texture(name: str, seed: int = 0, variant: int = 0, frame: int = 0, frames: int = 4) -> Image.Image:
    t = TERRAINS[name]
    colors = pal.ramp(t.hue, t.sat, t.val, 5)
    img = Image.new("RGBA", (T, T))
    px = img.load()
    vs = seed * 131 + variant * 17
    shift = frame * T / frames if t.animated else 0.0
    field = [[_fbm(vs, t, (x + shift) % T, y) for x in range(T)] for y in range(T)]
    mean = sum(map(sum, field)) / (T * T)
    for y in range(T):
        for x in range(T):
            n = field[y][x] - mean + 0.5  # every variant shares one average tone, so mixing them never patches
            n = n + (_BAYER[y % 4][x % 4] / 16 - 0.5) * 0.1  # ordered dither between ramp steps
            idx = max(1, min(3, int(n * 2.6) + 1))  # mid-ramp only: low contrast hides the repeat
            px[x, y] = colors[idx]
    _feature(px, t, colors, random.Random(vs + 7), frame, frames)
    return img


def _feature(px, t: Terrain, colors: list, rng: random.Random, frame: int, frames: int) -> None:
    f = t.feature
    if f == "blades":
        for _ in range(7):
            x, y = rng.randrange(T), rng.randrange(1, T)
            px[x, y] = colors[4]
            px[x, y - 1] = colors[3]
        if rng.random() < 0.35:  # the odd flower
            x, y = rng.randrange(1, T - 1), rng.randrange(1, T - 1)
            px[x, y] = pal.hsv(rng.choice([0.0, 0.15, 0.8, 0.6]), 0.6, 1.0)
    elif f == "pebbles":
        for _ in range(3):
            x, y = rng.randrange(T - 1), rng.randrange(T - 1)
            px[x, y] = colors[3]
            px[x + 1, y + 1] = colors[0]
    elif f == "speckle":
        for _ in range(6):
            px[rng.randrange(T), rng.randrange(T)] = colors[rng.choice([0, 4])]
    elif f == "waves":
        phase = frame / frames * 2 * math.pi
        for k in range(3):
            y0 = (rng.randrange(T) + frame) % T
            x0 = rng.randrange(T)
            for d in range(3 + k % 2):
                px[(x0 + d) % T, (y0 + (1 if d in (0, 3) else 0)) % T] = colors[4]
        if math.sin(phase + rng.random() * 6) > 0.6:
            px[rng.randrange(T), rng.randrange(T)] = (255, 255, 255, 255)
    elif f == "bubbles":
        for _ in range(2):
            x, y = rng.randrange(1, T - 1), rng.randrange(1, T - 1)
            r = (frame + rng.randrange(frames)) % frames
            if r < 2:
                px[x, y] = (255, 240, 160, 255)
                if r == 1:
                    px[x + 1, y] = px[x - 1, y] = px[x, y - 1] = (255, 200, 80, 255)
    elif f == "cracks":
        x, y = rng.randrange(T), rng.randrange(T)
        for _ in range(5):
            px[x % T, y % T] = colors[0]
            x += rng.choice([-1, 0, 1])
            y += 1
    elif f == "planks":
        for y in range(T):
            for x in range(T):
                if y % 4 == 3:
                    px[x, y] = colors[0]
                elif (x + (y // 4) * 7) % T == 0:
                    px[x, y] = colors[1]
    elif f == "bricks":
        for y in range(T):
            for x in range(T):
                if y % 4 == 3 or (x + (4 if (y // 4) % 2 else 0)) % 8 == 7:
                    px[x, y] = pal.ramp(0.08, 0.15, 0.7, 5)[1]
                elif y % 4 == 0:
                    px[x, y] = colors[4]
    elif f == "flagstones":
        for y in range(T):
            for x in range(T):
                if y % 8 == 7 or (x + (4 if (y // 8) % 2 else 0)) % 8 == 7:
                    px[x, y] = colors[0]


# ---------------------------------------------------------------------------- Wang 2-corner

# tile id -> corners (tl, tr, bl, br); 1 = upper terrain. Laid out 4x4 in this order.
WANG_ORDER = [(tl, tr, bl, br) for tl in (0, 1) for tr in (0, 1) for bl in (0, 1) for br in (0, 1)]


def transition_tiles(lower: str, upper: str, seed: int = 0, frame: int = 0) -> list[tuple[tuple, Image.Image]]:
    """16 tiles blending ``upper`` over ``lower`` by corner membership. Edges get a rim (a darker
    lip on the lower side, a highlight on the upper side) so the join reads as depth."""
    lo = texture(lower, seed, 0, frame).load()
    up = texture(upper, seed, 1, frame).load()
    out = []
    t_up = TERRAINS[upper]
    rim_dark = pal.ramp(TERRAINS[lower].hue, TERRAINS[lower].sat, TERRAINS[lower].val, 5)[0]
    rim_light = pal.ramp(t_up.hue, t_up.sat, t_up.val, 5)[4]
    for corners in WANG_ORDER:
        tl, tr, bl, br = corners
        mask = [[False] * T for _ in range(T)]
        for y in range(T):
            for x in range(T):
                u, v = (x + 0.5) / T, (y + 0.5) / T
                m = tl * (1 - u) * (1 - v) + tr * u * (1 - v) + bl * (1 - u) * v + br * u * v
                wobble = (_value_noise(seed + 99, 4, x, y) - 0.5) * 0.35
                mask[y][x] = m + wobble > 0.5
        img = Image.new("RGBA", (T, T))
        px = img.load()
        for y in range(T):
            for x in range(T):
                if mask[y][x]:
                    edge = any(not mask[ny][nx] for nx, ny in ((x, y - 1), (x - 1, y), (x + 1, y), (x, y + 1))
                               if 0 <= nx < T and 0 <= ny < T)
                    px[x, y] = rim_light if edge else up[x, y]
                else:
                    below_upper = y > 0 and mask[y - 1][x]
                    px[x, y] = rim_dark if below_upper else lo[x, y]
        out.append((corners, img))
    return out


def wang_sheet(lower: str, upper: str, seed: int = 0, frame: int = 0, variants: int = 4) -> Image.Image:
    """4 columns: rows 0-3 are the 16 Wang tiles, row 4 holds ``upper`` fill variants and row 5
    ``lower`` fill variants (same corner bits, so Godot's terrain painter scatters them)."""
    sheet = Image.new("RGBA", (4 * T, 6 * T))
    for i, (_, img) in enumerate(transition_tiles(lower, upper, seed, frame)):
        sheet.alpha_composite(img, ((i % 4) * T, (i // 4) * T))
    for v in range(min(4, variants)):
        sheet.alpha_composite(texture(upper, seed, v + 2, frame), (v * T, 4 * T))
        sheet.alpha_composite(texture(lower, seed, v + 2, frame), (v * T, 5 * T))
    return sheet


# ---------------------------------------------------------------------------- props

def prop(kind: str, seed: int = 0, hue: float | None = None) -> Image.Image:
    rng = random.Random(seed)
    if kind == "tree":
        g = Grid(16, 32)
        g.rect(6, 21, 9, 29, "H")
        g.set(5, 29, "H")
        g.set(10, 29, "H")
        for cx, cy, r in ((8, 8, 5.5), (4.5, 13, 4.2), (11.5, 13, 4.2), (8, 15, 5.5), (5, 18, 3.5), (11, 18, 3.5)):
            g.disc(cx + rng.uniform(-0.6, 0.6), cy + rng.uniform(-0.6, 0.6), r, "A")
        for _ in range(4):  # leaf clusters catching light
            g.disc(rng.uniform(4, 10), rng.uniform(5, 13), 1.5, "L")
        leaf = hue if hue is not None else 0.32
        ramps = {"A": pal.ramp(leaf, 0.65, 0.62), "L": pal.ramp(leaf - 0.03, 0.55, 0.85),
                 "H": pal.ramp(0.07, 0.55, 0.5)}
        return render(g, ramps)
    if kind == "pine":
        g = Grid(16, 32)
        g.rect(7, 25, 8, 29, "H")
        for k, (top, half) in enumerate(((2, 3), (8, 5), (14, 6.5))):
            g.poly([(8, top), (8 + half + 0.5, top + 11), (7.5 - half, top + 11)], "A")
        ramps = {"A": pal.ramp(hue if hue is not None else 0.4, 0.6, 0.55), "H": pal.ramp(0.07, 0.55, 0.45)}
        return render(g, ramps)
    if kind == "rock":
        g = Grid(16, 16)
        g.poly([(2, 13), (3, 7), (7, 4), (12, 5), (14, 10), (13, 13)], "A")
        return render(g, {"A": pal.ramp(0.62, 0.1, 0.75)})
    if kind == "bush":
        g = Grid(16, 16)
        for cx, cy, r in ((5, 10, 4), (11, 10, 4), (8, 7, 4.5)):
            g.disc(cx, cy, r, "A")
        for _ in range(3):
            g.set(rng.randrange(4, 12), rng.randrange(5, 11), "B")
        return render(g, {"A": pal.ramp(hue if hue is not None else 0.33, 0.6, 0.65),
                          "B": [(230, 70, 90, 255)] * 4}, flat={"B"})
    if kind == "flowers":
        g = Grid(16, 16)
        for _ in range(5):
            x, y = rng.randrange(2, 14), rng.randrange(4, 14)
            g.set(x, y, "S")
            g.set(x, y - 1, "F")
        return render(g, {"S": pal.ramp(0.33, 0.6, 0.5), "F": [pal.hsv(rng.random(), 0.55, 1.0)] * 4},
                      flat={"F"}, outline=False)
    if kind == "sign":
        g = Grid(16, 16)
        g.rect(7, 9, 8, 14, "H")
        g.rect(2, 3, 13, 9, "W")
        for y in (5, 7):
            g.rect(4, y, 11, y, "H")
        return render(g, {"H": pal.ramp(0.07, 0.55, 0.45), "W": pal.ramp(0.09, 0.45, 0.85)})
    if kind == "torch":
        g = Grid(16, 16)
        g.rect(7, 7, 8, 14, "H")
        g.disc(7.5, 5, 2.6, "F")
        g.disc(7.5, 5.8, 1.3, "Y")
        return render(g, {"H": pal.ramp(0.07, 0.55, 0.45), "F": pal.ramp(0.05, 0.9, 1.0),
                          "Y": [(255, 240, 150, 255)] * 4}, flat={"Y"})
    if kind == "crate":
        g = Grid(16, 16)
        g.rect(2, 3, 13, 14, "W")
        g.rect(2, 3, 13, 3, "H")
        g.rect(2, 14, 13, 14, "H")
        g.line(2, 3, 13, 14, "H")
        return render(g, {"W": pal.ramp(0.08, 0.55, 0.7), "H": pal.ramp(0.07, 0.6, 0.45)})
    raise ValueError(f"unknown prop {kind!r}; choose from {', '.join(PROPS)}")


PROPS = ("tree", "pine", "rock", "bush", "flowers", "sign", "torch", "crate")


# ---------------------------------------------------------------------------- Godot TileSet

def _solid(key: str) -> str:
    h = T // 2
    return f"{key}/physics_layer_0/polygon_0/points = PackedVector2Array(-{h}, -{h}, {h}, -{h}, {h}, {h}, -{h}, {h})"


def godot_tileset(texture_res_path: str, lower: str, upper: str, columns: int = 4) -> str:
    """A Godot 4 TileSet (.tres) for a :func:`wang_sheet`, terrain mode Match Corners, with
    collision on fully solid tiles."""
    lo_c = pal.ramp(TERRAINS[lower].hue, TERRAINS[lower].sat, TERRAINS[lower].val, 5)[2]
    up_c = pal.ramp(TERRAINS[upper].hue, TERRAINS[upper].sat, TERRAINS[upper].val, 5)[2]
    solid = {0: TERRAINS[lower].solid, 1: TERRAINS[upper].solid}
    lines = [
        '[gd_resource type="TileSet" load_steps=3 format=3]',
        "",
        f'[ext_resource type="Texture2D" path="{texture_res_path}" id="1_tex"]',
        "",
        '[sub_resource type="TileSetAtlasSource" id="TileSetAtlasSource_1"]',
        'texture = ExtResource("1_tex")',
        f"texture_region_size = Vector2i({T}, {T})",
    ]
    names = ("top_left_corner", "top_right_corner", "bottom_left_corner", "bottom_right_corner")
    for i, corners in enumerate(WANG_ORDER):
        x, y = i % columns, i // columns
        key = f"{x}:{y}/0"
        center = 1 if sum(corners) >= 2 else 0
        lines += [f"{key} = 0", f"{key}/terrain_set = 0", f"{key}/terrain = {center}"]
        lines += [f"{key}/terrains_peering_bit/{n} = {c}" for n, c in zip(names, corners)]
        if all(solid[c] for c in corners):
            lines.append(_solid(key))
    for row, terrain in ((4, 1), (5, 0)):  # fill variants: same bits as the all-upper / all-lower tile
        for x in range(4):
            key = f"{x}:{row}/0"
            lines += [f"{key} = 0", f"{key}/terrain_set = 0", f"{key}/terrain = {terrain}"]
            lines += [f"{key}/terrains_peering_bit/{n} = {terrain}" for n in names]
            lines.append(f"{key}/probability = 0.35")
            if solid[terrain]:
                lines.append(_solid(key))
    lines += [
        "",
        "[resource]",
        f"tile_size = Vector2i({T}, {T})",
        "physics_layer_0/collision_layer = 1",
        "terrain_set_0/mode = 1",
        f'terrain_set_0/terrain_0/name = "{lower}"',
        f"terrain_set_0/terrain_0/color = Color({lo_c[0] / 255:.3f}, {lo_c[1] / 255:.3f}, {lo_c[2] / 255:.3f}, 1)",
        f'terrain_set_0/terrain_1/name = "{upper}"',
        f"terrain_set_0/terrain_1/color = Color({up_c[0] / 255:.3f}, {up_c[1] / 255:.3f}, {up_c[2] / 255:.3f}, 1)",
        'sources/0 = SubResource("TileSetAtlasSource_1")',
        "",
    ]
    return "\n".join(lines)
