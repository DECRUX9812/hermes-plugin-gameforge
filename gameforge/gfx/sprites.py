"""Procedural pixel-art sprites: 16x16 RPG characters with 4-direction walk cycles, mask-grown
monsters with idle animations, and scalable item icons. All seeded and palette-driven."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from PIL import Image

from . import palette as pal
from .canvas import EMPTY, Grid, render

# ---------------------------------------------------------------------------- characters

_DOWN_TOP = [
    "................",
    "................",
    ".....SSSSSS.....",
    "....SSSSSSSS....",
    "....SSSSSSSS....",
    "....SESSSSES....",
    "....SESSSSES....",
    ".....SSSSSS.....",
    "....ABBBBBBA....",
    "...AABBBBBBAA...",
    "...K.BBBBBB.K...",
    ".....GGGGGG.....",
]
_DOWN_LEGS = [
    [".....PPPPPP.....", ".....PP..PP.....", ".....FF..FF.....", "................"],
    [".....PPPPPP.....", ".....PP..FF.....", ".....FF.........", "................"],
    [".....PPPPPP.....", ".....PP..PP.....", ".....FF..FF.....", "................"],
    [".....PPPPPP.....", ".....FF..PP.....", ".........FF.....", "................"],
]
_SIDE_TOP = [
    "................",
    "................",
    ".....SSSSSS.....",
    "....SSSSSSSS....",
    "....SSSSSSSSS...",
    "....SSSSSSES....",
    "....SSSSSSESS...",
    ".....SSSSSS.....",
]
_SIDE_BODY = [  # rows 8-11 per frame: arm swings with the stride
    ["......BBBB......", "......BABB......", "......BABB......", "......GKGG......"],
    ["......BBBB......", "......BBAB......", "......BBBAK.....", "......GGGG......"],
    ["......BBBB......", "......BABB......", "......BABB......", "......GKGG......"],
    ["......BBBB......", "......ABBB......", ".....KABBB......", "......GGGG......"],
]
_SIDE_LEGS = [
    ["......PPPP......", "......PPPP......", "......FFFFF.....", "................"],
    [".....PPPPPP.....", ".....PP..PP.....", "....FF....FF....", "................"],
    ["......PPPP......", "......PPPP......", "......FFFFF.....", "................"],
    [".....PPPPPP.....", ".....PP..PP.....", "....FF....FF....", "................"],
]

# headwear overlays per facing, rows from y=1
HAIR = {
    "short": {
        "down": [".....HHHHHH.....", "....HHHHHHHH....", "...HHHHHHHHHH...", "...HH.HHHH.HH...", "...H........H..."],
        "up": [".....HHHHHH.....", "....HHHHHHHH....", "...HHHHHHHHHH...", "...HHHHHHHHHH...", "...HHHHHHHHHH...",
               "....HHHHHHHH...."],
        "right": [".....HHHHHH.....", "....HHHHHHHHH...", "...HHHHHHHHHH...", "...HHHHHH.H.....", "...HHHH.........",
                  "...HHH..........", "....H..........."],
    },
    "long": {
        "down": [".....HHHHHH.....", "....HHHHHHHH....", "...HHHHHHHHHH...", "...HH.HHHH.HH...", "...H........H...",
                 "...H........H...", "...HH......HH...", "...HH......HH...", "....H......H...."],
        "up": [".....HHHHHH.....", "....HHHHHHHH....", "...HHHHHHHHHH...", "...HHHHHHHHHH...", "...HHHHHHHHHH...",
               "...HHHHHHHHHH...", "...HHHHHHHHHH...", "....HHHHHHHH....", "....HHHHHHHH...."],
        "right": [".....HHHHHH.....", "....HHHHHHHHH...", "...HHHHHHHHHH...", "...HHHHHH.H.....", "...HHHH.........",
                  "...HHHH.........", "...HHHH.........", "...HHH..........", "....HH.........."],
    },
    "spiky": {
        "down": ["....H.HHHH.H....", "...HHHHHHHHHH...", "...HHHHHHHHHH...", "...HH.HHHH.HH...", "...H........H..."],
        "up": ["....H.HHHH.H....", "...HHHHHHHHHH...", "...HHHHHHHHHH...", "...HHHHHHHHHH...", "...HHHHHHHHHH...",
               "....HHHHHHHH...."],
        "right": ["....H.HHHH.H....", "...HHHHHHHHHH...", "..HHHHHHHHHHH...", "..HHHHHHH.H.....", "...HHHH.........",
                  "..HHH...........", "...H............"],
    },
    "bald": {"down": [], "up": [], "right": []},
    "hood": {
        "down": [".....CCCCCC.....", "....CCCCCCCC....", "...CCCCCCCCCC...", "...CC......CC...", "...C........C...",
                 "...C........C...", "...CC......CC...", "...CC......CC..."],
        "up": [".....CCCCCC.....", "....CCCCCCCC....", "...CCCCCCCCCC...", "...CCCCCCCCCC...", "...CCCCCCCCCC...",
               "...CCCCCCCCCC...", "...CCCCCCCCCC...", "...CCCCCCCCCC..."],
        "right": [".....CCCCCC.....", "....CCCCCCCCC...", "...CCCCCCCCCC...", "...CCCCCC.......", "...CCCCC........",
                  "...CCCCC........", "...CCCCC........", "....CCCC........"],
    },
    "helmet": {
        "down": [".....MMMMMM.....", "....MMMMMMMM....", "...MMMMMMMMMM...", "...MMMMMMMMMM...", "...M........M...",
                 "...M........M..."],
        "up": [".....MMMMMM.....", "....MMMMMMMM....", "...MMMMMMMMMM...", "...MMMMMMMMMM...", "...MMMMMMMMMM...",
               "...MMMMMMMMMM..."],
        "right": [".....MMMMMM.....", "....MMMMMMMMM...", "...MMMMMMMMMM...", "...MMMMMMMMMM...", "...MMMMM........",
                  "...MMMMM........"],
    },
}
OUTFITS = ("tunic", "robe", "armor")

ARCHETYPES = {
    "hero": {"hair": "spiky", "outfit": "tunic", "hair_hue": "indigo", "body_hue": "blue", "legs_hue": "brown"},
    "knight": {"hair": "helmet", "outfit": "armor", "hair_hue": "blue", "body_hue": "blue", "legs_hue": "indigo"},
    "mage": {"hair": "hood", "outfit": "robe", "hair_hue": "purple", "body_hue": "purple", "legs_hue": "indigo"},
    "rogue": {"hair": "hood", "outfit": "tunic", "hair_hue": "green", "body_hue": "teal", "legs_hue": "brown"},
    "villager": {"hair": "short", "outfit": "tunic", "hair_hue": "brown", "body_hue": "lime", "legs_hue": "brown"},
    "princess": {"hair": "long", "outfit": "robe", "hair_hue": "gold", "body_hue": "pink", "legs_hue": "pink"},
    "healer": {"hair": "long", "outfit": "robe", "hair_hue": "red", "body_hue": "cyan", "legs_hue": "teal"},
}

SKIN_TONES = [(0.07, 0.30, 1.0), (0.07, 0.42, 0.92), (0.06, 0.55, 0.75), (0.06, 0.6, 0.55), (0.05, 0.55, 0.42)]
FACINGS = ("down", "left", "right", "up")


@dataclass
class CharacterSpec:
    hair: str = "short"
    outfit: str = "tunic"
    skin: int = 1
    hair_hue: str | float = "brown"
    body_hue: str | float = "blue"
    legs_hue: str | float = "brown"
    seed: int = 0
    extra: dict = field(default_factory=dict)


def character_spec(archetype: str | None, seed: int, overrides: dict | None = None) -> CharacterSpec:
    rng = random.Random(seed)
    base = dict(ARCHETYPES.get(archetype or "", {}))
    if not base:
        base = {"hair": rng.choice(["short", "long", "spiky", "hood", "bald"]), "outfit": rng.choice(OUTFITS),
                "hair_hue": rng.random(), "body_hue": rng.random(), "legs_hue": rng.random()}
    base["skin"] = rng.randrange(len(SKIN_TONES))
    base.update({k: v for k, v in (overrides or {}).items() if v is not None})
    return CharacterSpec(seed=seed, **{k: base[k] for k in ("hair", "outfit", "skin", "hair_hue", "body_hue",
                                                             "legs_hue")})


def _character_ramps(spec: CharacterSpec) -> dict[str, list]:
    h, s, v = SKIN_TONES[spec.skin % len(SKIN_TONES)]
    hair_h = pal.hue_of(spec.hair_hue, 0.07)
    body_h = pal.hue_of(spec.body_hue, 0.6)
    legs_h = pal.hue_of(spec.legs_hue, 0.07)
    body = pal.ramp(body_h, 0.7, 0.85)
    return {
        "S": pal.ramp(h, s, v), "E": [(30, 20, 40, 255)] * 4, "B": body, "A": body,
        "K": pal.ramp(h, s, v), "G": pal.ramp(0.08, 0.6, 0.45), "P": pal.ramp(legs_h, 0.5, 0.55),
        "F": pal.ramp(0.05, 0.5, 0.35), "H": pal.ramp(hair_h, 0.6, 0.75 if hair_h else 0.6),
        "C": pal.ramp(hair_h, 0.55, 0.65), "M": pal.ramp(0.6, 0.12, 0.9),
    }


def character_frame(spec: CharacterSpec, facing: str, frame: int, bob: int = 0) -> Image.Image:
    side = facing in ("left", "right")
    view = "right" if side else facing
    if side:
        rows = _SIDE_TOP + _SIDE_BODY[frame] + _SIDE_LEGS[frame]
    else:
        rows = _DOWN_TOP + _DOWN_LEGS[frame]
    g = Grid.from_rows(rows)
    if view == "up":
        g.remap({"E": "S"})
    if spec.outfit == "robe":
        g.remap({"P": "B", "G": "B"})
    elif spec.outfit == "armor":
        g.remap({"B": "M", "A": "M"})
    g.overlay(HAIR[spec.hair][view], dy=1)
    if bob:  # idle breath: the head sinks one pixel into the collar
        g.cells = [[EMPTY] * 16] + g.cells[:7] + g.cells[8:]
    if facing == "left":
        g = g.mirrored()
    return render(g, _character_ramps(spec), flat={"E"})


def character_sheet(spec: CharacterSpec) -> tuple[list[Image.Image], dict[str, list[int]]]:
    """Frames + animation table: idle_<facing> (2 frames) and walk_<facing> (4 frames)."""
    frames: list[Image.Image] = []
    anims: dict[str, list[int]] = {}
    for facing in FACINGS:
        start = len(frames)
        frames += [character_frame(spec, facing, 0), character_frame(spec, facing, 0, bob=1)]
        anims[f"idle_{facing}"] = [start, start + 1]
        start = len(frames)
        frames += [character_frame(spec, facing, f) for f in range(4)]
        anims[f"walk_{facing}"] = list(range(start, start + 4))
    return frames, anims


# ---------------------------------------------------------------------------- monsters

# 1 = body or empty, 2 = body or skin-edge, 3 = always body; mirrored horizontally
MONSTER_MASKS = {
    "slime": ["......", "......", "......", "......", "...333", "..1333", ".13333", ".13333", "123333", "233333",
              "233333", ".22222"],
    "bat": ["......", "1.....", "11....", "121..3", "1221.3", ".12133", "..1233", "...123", "....12", "......"],
    "beast": ["......", "..1...", ".11.33", ".12333", "..2333", "..3333", ".13333", "113333", "123333", ".12.33",
              ".12..3", ".11..2"],
    "ghost": ["......", "...133", "..1333", ".13333", ".13333", ".23333", ".23333", ".23333", ".23333", ".21313",
              ".1..1."],
    "golem": ["......", "..1333", "..2333", ".11333", "122333", "123333", "123333", ".13333", "..2333", ".12.33",
              ".12.23", "122.22"],
    "spaceship": ["......", ".....1", "....11", "....12", "...112", "..1112", ".11122", ".11122", ".11122", ".11112",
                  "...111", "......"],
}
MONSTER_EYES = {"slime": 7, "bat": 4, "beast": 4, "ghost": 4, "golem": 4, "spaceship": 6}


def monster_frames(kind: str, seed: int, hue: str | float | None = None, size: int = 16) -> list[Image.Image]:
    """Two-frame idle: a squash/hover. ``size`` 16 or 32 (the mask is grown by 2x)."""
    if kind not in MONSTER_MASKS:
        raise ValueError(f"unknown monster kind {kind!r}; choose from {', '.join(MONSTER_MASKS)}")
    rng = random.Random(seed)
    mask = MONSTER_MASKS[kind]
    half_w, h = len(mask[0]), len(mask)
    g = Grid(16, 16)
    oy = (16 - h) // 2 + 1
    for y, row in enumerate(mask):
        for x, ch in enumerate(row):
            if ch == "3" or (ch == "1" and rng.random() < 0.55) or (ch == "2" and rng.random() < 0.8):
                sym = "B" if ch != "2" or rng.random() < 0.6 else "D"
                g.set(2 + x, oy + y, sym)
                g.set(13 - x, oy + y, sym)
    # belly/accents: lighter region in the lower middle
    for y in range(oy + h // 2, oy + h):
        for x in range(6, 10):
            if g.get(x, y) == "B" and rng.random() < 0.7:
                g.set(x, y, "L")
    ey = oy + MONSTER_EYES[kind]
    for ex in (6, 9) if kind != "spaceship" else (7, 8):
        g.set(ex, ey, "W")
        g.set(ex, ey + 1, "E")
    if rng.random() < 0.5 and kind in ("beast", "golem", "slime"):
        for x in range(6, 10):
            if g.get(x, ey + 3) in ("B", "L"):
                g.set(x, ey + 3, "E")  # a mouth
    body_h = pal.hue_of(hue, rng.random())
    ramps = {"B": pal.ramp(body_h, 0.7, 0.85), "D": pal.ramp(body_h + 0.04, 0.75, 0.6),
             "L": pal.ramp(body_h - 0.05, 0.4, 1.0), "W": [(250, 250, 240, 255)] * 4, "E": [(25, 15, 35, 255)] * 4}
    frames = [render(g, ramps, flat={"W", "E"})]
    squash = Grid(16, 16)
    if kind in ("bat", "ghost", "spaceship"):
        squash = g.shifted(0, -1)
    else:  # sink the top half by one pixel, keep feet planted
        for y in range(16):
            for x in range(16):
                src_y = y - 1 if y < oy + h // 2 else y
                squash.cells[y][x] = g.get(x, src_y) if y > 0 else EMPTY
    frames.append(render(squash, ramps, flat={"W", "E"}))
    if size != 16:
        frames = [f.resize((size, size), Image.NEAREST) for f in frames]
    return frames


# ---------------------------------------------------------------------------- items

ITEM_KINDS = ("sword", "potion", "gem", "coin", "key", "heart", "shield", "bomb", "mushroom", "chest", "scroll",
              "bow", "star", "apple")


def item(kind: str, size: int = 16, hue: str | float | None = None) -> Image.Image:
    """Scalable icon drawn from primitives, then auto-shaded and outlined."""
    if kind not in ITEM_KINDS:
        raise ValueError(f"unknown item {kind!r}; choose from {', '.join(ITEM_KINDS)}")
    s = size / 16
    g = Grid(size, size)
    default_hue = {"sword": 0.6, "potion": 0.95, "gem": 0.5, "coin": 0.13, "key": 0.13, "heart": 0.98,
                   "shield": 0.6, "bomb": 0.7, "mushroom": 0.0, "chest": 0.08, "scroll": 0.11, "bow": 0.07,
                   "star": 0.14, "apple": 0.99}[kind]
    hue_v = pal.hue_of(hue, default_hue)
    glints: list[tuple[float, float]] = []
    if kind == "sword":
        g.poly([(12.5 * s, 1.5 * s), (14.5 * s, 1.5 * s), (14.5 * s, 3.5 * s), (6.5 * s, 11.5 * s),
                (4.5 * s, 9.5 * s)], "A")
        g.line(int(3 * s), int(8 * s), int(8 * s), int(13 * s), "G")
        g.line(int(3 * s), int(9 * s), int(7 * s), int(13 * s), "G")
        g.line(int(2 * s), int(14 * s), int(5 * s), int(11 * s), "H")
        g.line(int(1 * s), int(14 * s), int(4 * s), int(11 * s), "H")
        glints = [(12.5, 2.5)]
    elif kind == "potion":
        g.disc(8 * s, 10.5 * s, 4.6 * s, "A")
        g.rect(int(6.5 * s), int(3 * s), int(9.5 * s) - 1, int(6.5 * s), "W")
        g.rect(int(6 * s), int(1.5 * s), int(10 * s) - 1, int(3 * s), "H")
        for y in range(int(6.5 * s), int(9 * s)):
            for x in range(size):
                if g.get(x, y) == "A":
                    g.set(x, y, "W")
        glints = [(5.5, 9.5), (6.5, 8.5)]
    elif kind == "gem":
        g.poly([(4 * s, 5 * s), (6 * s, 2.5 * s), (10 * s, 2.5 * s), (12 * s, 5 * s), (8 * s, 13.5 * s)], "A")
        g.poly([(4 * s, 5 * s), (12 * s, 5 * s), (8 * s, 13.5 * s)], "D")
        glints = [(6.5, 3.5), (5.5, 5.5)]
    elif kind == "coin":
        g.disc(8 * s, 8 * s, 6 * s, "A")
        g.disc(8 * s, 8 * s, 4 * s, "D")
        g.rect(int(7.5 * s), int(5.5 * s), int(8.5 * s) - 1, int(10.5 * s), "A")
        glints = [(5.5, 5.5)]
    elif kind == "key":
        g.disc(5 * s, 5 * s, 3.5 * s, "A")
        g.disc(5 * s, 5 * s, 1.5 * s, ".")
        g.poly([(6.5 * s, 7.5 * s), (8 * s, 6 * s), (14 * s, 12 * s), (12.5 * s, 13.5 * s)], "A")
        g.rect(int(10 * s), int(12 * s), int(11 * s), int(14 * s), "A")
        g.rect(int(12 * s), int(13.5 * s), int(12.5 * s), int(15 * s) - 1, "A")
        glints = [(3.5, 3.5)]
    elif kind == "heart":
        g.disc(5.5 * s, 6 * s, 3.4 * s, "A")
        g.disc(10.5 * s, 6 * s, 3.4 * s, "A")
        g.poly([(2.3 * s, 7 * s), (13.7 * s, 7 * s), (8 * s, 14 * s)], "A")
        glints = [(4.5, 4.5)]
    elif kind == "shield":
        g.poly([(3 * s, 2.5 * s), (13 * s, 2.5 * s), (13 * s, 8 * s), (8 * s, 14.5 * s), (3 * s, 8 * s)], "M")
        g.poly([(4.5 * s, 4 * s), (11.5 * s, 4 * s), (11.5 * s, 8 * s), (8 * s, 12.8 * s), (4.5 * s, 8 * s)], "A")
        g.rect(int(7.5 * s), int(4 * s), int(8.5 * s) - 1, int(12 * s), "G")
        g.rect(int(4.5 * s), int(6.5 * s), int(11.5 * s) - 1, int(7.5 * s) - 1, "G")
    elif kind == "bomb":
        g.disc(7.5 * s, 9.5 * s, 5.5 * s, "A")
        g.rect(int(9 * s), int(3.5 * s), int(11 * s) - 1, int(5 * s), "M")
        g.line(int(10.5 * s), int(3 * s), int(13 * s), int(1 * s), "H")
        g.set(int(13 * s), int(1 * s) - 1, "Y")
        glints = [(5.5, 7.5)]
        hue_v = pal.hue_of(hue, 0.68)
    elif kind == "mushroom":
        g.disc(8 * s, 8 * s, 6.5 * s, "A")
        g.rect(0, int(8 * s), size, size, ".")
        g.rect(int(5.5 * s), int(8 * s), int(10.5 * s) - 1, int(14 * s), "W")
        for cx, cy in ((5.5, 5), (10, 4), (8, 6.5)):
            g.disc(cx * s, cy * s, 1.1 * s, "W")
    elif kind == "chest":
        g.rect(int(2 * s), int(6 * s), int(14 * s) - 1, int(14 * s), "H")
        g.rect(int(2 * s), int(3.5 * s), int(14 * s) - 1, int(6 * s), "D")
        g.rect(int(2 * s), int(7 * s), int(14 * s) - 1, int(7.8 * s), "G")
        g.rect(int(7 * s), int(6 * s), int(9 * s) - 1, int(9 * s), "G")
        hue_v = pal.hue_of(hue, 0.13)
    elif kind == "scroll":
        g.rect(int(4 * s), int(3 * s), int(12 * s) - 1, int(13 * s), "W")
        g.disc(4 * s, 3.5 * s, 1.6 * s, "H")
        g.disc(12 * s, 12.5 * s, 1.6 * s, "H")
        for y in (5.5, 7.5, 9.5):
            g.rect(int(5.5 * s), int(y * s), int(10.5 * s) - 1, int(y * s), "D")
    elif kind == "bow":
        for k in range(15):
            t = k / 14
            g.set(int((3 + 7 * (1 - (2 * t - 1) ** 2)) * s), int((1.5 + 13 * t) * s), "H")
            g.set(int((3 + 7 * (1 - (2 * t - 1) ** 2)) * s) + 1, int((1.5 + 13 * t) * s), "H")
        g.line(int(3 * s), int(1.5 * s), int(3 * s), int(14.5 * s), "W")
    elif kind == "star":
        pts = []
        for k in range(10):
            r = (6.5 if k % 2 == 0 else 2.8) * s
            a = -math.pi / 2 + k * math.pi / 5
            pts.append((8 * s + r * math.cos(a), 8.5 * s + r * math.sin(a)))
        g.poly(pts, "A")
        glints = [(6.5, 6.5)]
    elif kind == "apple":
        g.disc(8 * s, 9.5 * s, 5.5 * s, "A")
        g.rect(int(7.5 * s), int(2 * s), int(8.5 * s) - 1, int(4.5 * s), "H")
        g.poly([(8.5 * s, 3.5 * s), (12 * s, 1.5 * s), (11 * s, 4 * s)], "L")
        glints = [(5.5, 7.5)]
    for gx, gy in glints:
        g.set(int(gx * s), int(gy * s), "W" if g.get(int(gx * s), int(gy * s)) != EMPTY else EMPTY)
    ramps = {"A": pal.ramp(hue_v, 0.75, 0.9), "D": pal.ramp(hue_v + 0.02, 0.8, 0.7), "M": pal.ramp(0.6, 0.12, 0.85),
             "G": pal.ramp(0.12, 0.8, 0.95), "H": pal.ramp(0.07, 0.6, 0.55), "W": pal.ramp(0.12, 0.08, 1.0),
             "Y": [(255, 220, 90, 255)] * 4, "L": pal.ramp(0.3, 0.7, 0.75)}
    return render(g, ramps, flat={"Y"})
