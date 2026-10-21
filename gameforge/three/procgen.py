"""Low-poly 3D asset generators and animation presets. Every generator is seeded and returns a
:class:`Scene` ready for :func:`gltf.write_glb`. Units are metres, +Y up, the model faces +Z."""

from __future__ import annotations

import math
import random

from .mesh import (Animation, Mesh, Node, Scene, Track, box, cone, cylinder, icosphere, prism_roof, qmul,
                   quat_axis)
from ..gfx import palette as pal

KINDS = ("tree", "pine", "rock", "crystal", "house", "tower", "terrain", "dungeon", "character", "chest", "coin",
         "potion", "sword", "mushroom", "spaceship", "cloud", "fence", "barrel")
ANIMATIONS = ("spin", "bob", "bounce", "pulse", "walk", "idle", "wave", "open")


def _rgb(hue: float, sat: float, val: float) -> tuple[float, float, float]:
    r, g, b, _ = pal.hsv(hue, sat, val)
    return r / 255, g / 255, b / 255


def _shade(rng: random.Random, hue: float, sat: float, val: float, spread: float = 0.06):
    return _rgb(hue + rng.uniform(-0.02, 0.02), sat, val + rng.uniform(-spread, spread))


def build(kind: str, seed: int = 0, hue: float | None = None, layout: list[str] | None = None) -> Scene:
    if kind not in KINDS:
        raise ValueError(f"unknown model kind {kind!r}; choose from {', '.join(KINDS)}")
    rng = random.Random(seed)
    return _BUILDERS[kind](rng, hue, layout)


def _single(name: str, mesh: Mesh) -> Scene:
    return Scene(roots=[Node(name, mesh)])


def _tree(rng, hue, _):
    h = hue if hue is not None else 0.30 + rng.uniform(-0.04, 0.06)
    trunk = cylinder(0.12, 1.0, 6, _rgb(0.07, 0.55, 0.42), r_top=0.08).jitter(0.02, rng)
    leaves = Mesh()
    for k in range(rng.randint(3, 5)):
        r = rng.uniform(0.35, 0.55)
        ball = icosphere(r, 1).jitter(r * 0.12, rng)
        for i in range(len(ball.faces)):
            ball.colors[i] = _shade(rng, h, 0.6, 0.62)
        leaves.add(ball.transformed((rng.uniform(-0.3, 0.3), 1.0 + rng.uniform(0, 0.6), rng.uniform(-0.3, 0.3))))
    return Scene(roots=[Node("tree", trunk.add(leaves))])


def _pine(rng, hue, _):
    h = hue if hue is not None else 0.38
    m = cylinder(0.1, 0.5, 6, _rgb(0.07, 0.55, 0.38))
    for k in range(3):
        tier = cone(0.7 - k * 0.17, 0.75, 8).jitter(0.03, rng)
        tier.colors = [_shade(rng, h, 0.55, 0.5 + k * 0.06) for _ in tier.faces]
        m.add(tier.transformed((0, 0.4 + k * 0.42, 0)))
    return _single("pine", m)


def _rock(rng, hue, _):
    m = icosphere(0.5, 1).jitter(0.12, rng).transformed(s=(1.2, 0.7, 1.0))
    m.colors = [_shade(rng, 0.6 if hue is None else hue, 0.08, 0.6, 0.1) for _ in m.faces]
    return _single("rock", m.transformed((0, 0.25, 0)))


def _crystal(rng, hue, _):
    h = hue if hue is not None else rng.choice([0.5, 0.75, 0.9, 0.33])
    m = Mesh()
    for k in range(rng.randint(3, 6)):
        height = rng.uniform(0.5, 1.3)
        shard = cylinder(0.12, height * 0.75, 6, r_top=0.12).add(cone(0.12, height * 0.25, 6).transformed((0, height * 0.75, 0)))
        shard.colors = [_shade(rng, h, 0.55, 0.9, 0.1) for _ in shard.faces]
        tilt = qmul(quat_axis((0, 0, 1), rng.uniform(-0.5, 0.5)), quat_axis((1, 0, 0), rng.uniform(-0.5, 0.5)))
        m.add(shard.transformed((rng.uniform(-0.2, 0.2), 0, rng.uniform(-0.2, 0.2)), r=tilt))
    base = icosphere(0.35, 0).transformed(s=(1, 0.35, 1)).paint(_rgb(0.6, 0.1, 0.45))
    return _single("crystal", m.add(base))


def _house(rng, hue, _):
    w, d, h = rng.uniform(1.6, 2.4), rng.uniform(1.6, 2.2), rng.uniform(1.1, 1.5)
    wall = _rgb(0.1, 0.25, 0.92)
    roof_c = _rgb(hue if hue is not None else rng.choice([0.0, 0.03, 0.6, 0.33]), 0.6, 0.6)
    m = box(w, h, d, wall).transformed((0, h / 2, 0))
    m.add(prism_roof(w + 0.3, d + 0.3, h * 0.7, roof_c).transformed((0, h, 0)))
    m.add(box(0.45, 0.8, 0.05, _rgb(0.07, 0.6, 0.4)).transformed((0, 0.4, d / 2 + 0.02)))
    for x in (-w / 3, w / 3):
        m.add(box(0.35, 0.35, 0.05, _rgb(0.55, 0.4, 0.95)).transformed((x, h * 0.6, d / 2 + 0.02)))
    m.add(box(0.3, 0.7, 0.3, _rgb(0.0, 0.3, 0.5)).transformed((w / 4, h + h * 0.55, 0)))
    return _single("house", m)


def _tower(rng, hue, _):
    stone = _rgb(0.6, 0.06, 0.7)
    m = cylinder(0.8, 3.0, 10, stone).jitter(0.03, rng)
    for i in range(10):
        if i % 2 == 0:
            a = 2 * math.pi * i / 10
            m.add(box(0.35, 0.35, 0.35, stone).transformed((0.75 * math.cos(a), 3.15, 0.75 * math.sin(a))))
    m.add(cone(0.95, 1.4, 10, _rgb(hue if hue is not None else 0.0, 0.6, 0.55)).transformed((0, 3.35, 0)))
    m.add(box(0.5, 0.9, 0.1, _rgb(0.07, 0.6, 0.35)).transformed((0, 0.45, 0.78)))
    return _single("tower", m)


def _terrain(rng, hue, _):
    n, size = 24, 12.0
    off = [[rng.random() for _ in range(6)] for _ in range(6)]

    def height(x: float, z: float) -> float:
        h = 0.0
        for k, amp in ((1, 1.6), (2, 0.6), (4, 0.25)):
            h += amp * math.sin(x * k * 0.5 + off[k][0] * 6) * math.cos(z * k * 0.45 + off[k][1] * 6)
        d = math.hypot(x, z) / (size / 2)
        return h * (1 - d * 0.4) + 1.2 * (1 - d * d)

    verts, faces, colors = [], [], []
    step = size / n
    grid = [[(i * step - size / 2, height(i * step - size / 2, j * step - size / 2), j * step - size / 2)
             for i in range(n + 1)] for j in range(n + 1)]
    for j in range(n + 1):
        verts += grid[j]
    for j in range(n):
        for i in range(n):
            a, b, c, d = j * (n + 1) + i, j * (n + 1) + i + 1, (j + 1) * (n + 1) + i, (j + 1) * (n + 1) + i + 1
            for tri in ((a, c, b), (b, c, d)):
                faces.append(tri)
                y = sum(verts[t][1] for t in tri) / 3
                colors.append(_terrain_color(y, rng))
    m = Mesh(verts, faces, colors)
    water = box(size, 0.02, size, _rgb(0.57, 0.6, 0.85)).transformed((0, 0.05, 0))
    return Scene(roots=[Node("terrain", m), Node("water", water)])


def _terrain_color(y: float, rng: random.Random):
    if y < 0.25:
        return _shade(rng, 0.12, 0.4, 0.9, 0.04)
    if y < 1.6:
        return _shade(rng, 0.3, 0.6, 0.62, 0.05)
    if y < 2.4:
        return _shade(rng, 0.08, 0.3, 0.55, 0.05)
    return _shade(rng, 0.6, 0.05, 0.97, 0.02)


DEFAULT_DUNGEON = [
    "##########",
    "#....#...#",
    "#.C..#.T.#",
    "#....D...#",
    "##D###...#",
    "#......###",
    "#.T....C.#",
    "##########",
]


def _dungeon(rng, hue, layout):
    """``#`` wall, ``.`` floor, ``D`` door, ``C`` chest, ``T`` torch pillar."""
    rows = layout or DEFAULT_DUNGEON
    floor_m, wall_m, props = Mesh(), Mesh(), Mesh()
    h = len(rows)
    for z, row in enumerate(rows):
        for x, ch in enumerate(row):
            px, pz = x - len(row) / 2, z - h / 2
            if ch == "#":
                wall_m.add(box(1, 1.6, 1, _shade(rng, 0.62, 0.08, 0.5, 0.05)).transformed((px, 0.8, pz)))
                continue
            floor_m.add(box(0.98, 0.1, 0.98, _shade(rng, 0.7, 0.12, 0.38, 0.05)).transformed((px, -0.05, pz)))
            if ch == "D":
                props.add(box(0.9, 1.2, 0.12, _rgb(0.07, 0.6, 0.4)).transformed((px, 0.6, pz)))
            elif ch == "C":
                props.add(box(0.6, 0.35, 0.4, _rgb(0.08, 0.6, 0.5)).transformed((px, 0.18, pz)))
                props.add(box(0.62, 0.12, 0.42, _rgb(0.13, 0.8, 0.9)).transformed((px, 0.4, pz)))
            elif ch == "T":
                props.add(cylinder(0.08, 1.0, 6, _rgb(0.07, 0.5, 0.35)).transformed((px, 0, pz)))
                props.add(icosphere(0.14, 0, _rgb(0.08, 0.95, 1.0)).transformed((px, 1.1, pz)))
    return Scene(roots=[Node("floor", floor_m), Node("walls", wall_m), Node("props", props)])


def _character(rng, hue, _):
    """Blocky humanoid as a node hierarchy (no skin weights needed): limbs pivot at the joints so
    the walk/idle/wave presets read correctly in any engine."""
    shirt = _rgb(hue if hue is not None else rng.random(), 0.6, 0.7)
    skin = _rgb(0.07, rng.uniform(0.3, 0.55), rng.uniform(0.55, 0.95))
    pants = _rgb(rng.random(), 0.4, 0.4)
    hair = _rgb(rng.random(), 0.5, 0.4)
    head = box(0.5, 0.5, 0.5, skin).transformed((0, 0.25, 0))
    head.add(box(0.54, 0.16, 0.54, hair).transformed((0, 0.52, 0)))
    for ex in (-0.11, 0.11):
        head.add(box(0.07, 0.09, 0.02, (0.08, 0.06, 0.1)).transformed((ex, 0.28, 0.26)))
    torso = box(0.55, 0.65, 0.3, shirt).transformed((0, 0.325, 0))

    def limb(w: float, length: float, color) -> Mesh:
        return box(w, length, w, color).transformed((0, -length / 2, 0))

    arm_l = Node("arm_l", limb(0.18, 0.6, shirt).add(box(0.17, 0.12, 0.17, skin).transformed((0, -0.62, 0))),
                 translation=(-0.37, 0.6, 0))
    arm_r = Node("arm_r", limb(0.18, 0.6, shirt).add(box(0.17, 0.12, 0.17, skin).transformed((0, -0.62, 0))),
                 translation=(0.37, 0.6, 0))
    leg_l = Node("leg_l", limb(0.22, 0.7, pants), translation=(-0.14, 0, 0))
    leg_r = Node("leg_r", limb(0.22, 0.7, pants), translation=(0.14, 0, 0))
    body = Node("body", torso, translation=(0, 0.7, 0),
                children=[Node("head", head, translation=(0, 0.65, 0)), arm_l, arm_r, leg_l, leg_r])
    return Scene(roots=[Node("character", None, children=[body])])


def _chest(rng, hue, _):
    wood = _rgb(0.07, 0.6, 0.5)
    gold = _rgb(0.13, 0.8, 0.95)
    base = box(0.8, 0.45, 0.5, wood).transformed((0, 0.225, 0))
    base.add(box(0.82, 0.06, 0.52, gold).transformed((0, 0.43, 0)))
    lid = box(0.8, 0.22, 0.5, wood).transformed((0, 0.11, 0.25))
    lid.add(box(0.12, 0.14, 0.04, gold).transformed((0, 0.0, 0.51)))
    return Scene(roots=[Node("chest", base, children=[Node("lid", lid, translation=(0, 0.45, -0.25))])])


def _coin(rng, hue, _):
    m = cylinder(0.4, 0.08, 16, _rgb(hue if hue is not None else 0.13, 0.8, 0.95))
    m.add(cylinder(0.28, 0.1, 16, _rgb(0.12, 0.85, 0.75)).transformed((0, -0.01, 0)))
    return _single("coin", m.transformed((0, 0.5, 0), r=quat_axis((1, 0, 0), math.pi / 2)))


def _potion(rng, hue, _):
    liquid = icosphere(0.3, 1, _rgb(hue if hue is not None else 0.95, 0.75, 0.9)).transformed((0, 0.3, 0))
    liquid.add(cylinder(0.1, 0.22, 8, _rgb(0.55, 0.15, 0.95)).transformed((0, 0.52, 0)))
    liquid.add(cylinder(0.12, 0.1, 8, _rgb(0.07, 0.55, 0.45)).transformed((0, 0.72, 0)))
    return _single("potion", liquid)


def _sword(rng, hue, _):
    blade = box(0.12, 1.0, 0.03, _rgb(0.6, 0.08, 0.92)).transformed((0, 0.75, 0))
    blade.add(cone(0.06, 0.15, 4, _rgb(0.6, 0.08, 0.92)).transformed((0, 1.25, 0)))
    blade.add(box(0.45, 0.07, 0.08, _rgb(0.13, 0.8, 0.9)).transformed((0, 0.22, 0)))
    blade.add(cylinder(0.04, 0.22, 6, _rgb(0.07, 0.6, 0.4)))
    blade.add(icosphere(0.06, 0, _rgb(hue if hue is not None else 0.0, 0.8, 0.8)).transformed((0, -0.02, 0)))
    return _single("sword", blade)


def _mushroom(rng, hue, _):
    stem = cylinder(0.12, 0.35, 8, _rgb(0.1, 0.15, 0.95), r_top=0.1)
    cap = icosphere(0.35, 1).transformed((0, 0.35, 0), s=(1, 0.6, 1))
    cap.colors = [_rgb(hue if hue is not None else 0.0, 0.75, 0.85) if rng.random() > 0.15 else (1, 1, 1)
                  for _ in cap.faces]
    return _single("mushroom", stem.add(cap))


def _spaceship(rng, hue, _):
    h = hue if hue is not None else rng.random()
    hull = cone(0.35, 1.6, 6, _rgb(0.6, 0.08, 0.85)).transformed(r=quat_axis((1, 0, 0), math.pi / 2))
    hull.add(icosphere(0.2, 1, _rgb(0.55, 0.6, 0.95)).transformed((0, 0.18, 0.55)))
    for side in (-1, 1):
        wing = box(0.9, 0.06, 0.5, _rgb(h, 0.65, 0.7)).transformed((side * 0.55, 0, 0.2))
        hull.add(wing)
        hull.add(cylinder(0.08, 0.3, 6, _rgb(0.05, 0.9, 1.0)).transformed((side * 0.25, 0, -0.1),
                                                                         r=quat_axis((1, 0, 0), -math.pi / 2)))
    return _single("spaceship", hull.transformed((0, 0.6, 0)))


def _cloud(rng, hue, _):
    m = Mesh()
    for _ in range(5):
        r = rng.uniform(0.3, 0.55)
        m.add(icosphere(r, 1, (0.97, 0.98, 1.0)).jitter(0.03, rng).transformed((rng.uniform(-0.7, 0.7), rng.uniform(0, 0.25),
                                                                                 rng.uniform(-0.25, 0.25))))
    return _single("cloud", m.transformed((0, 2, 0)))


def _fence(rng, hue, _):
    wood = _rgb(0.08, 0.5, 0.6)
    m = Mesh()
    for x in (-0.9, 0, 0.9):
        m.add(box(0.12, 0.8, 0.12, wood).transformed((x, 0.4, 0)))
    for y in (0.3, 0.6):
        m.add(box(2.0, 0.1, 0.06, wood).transformed((0, y, 0.07)))
    return _single("fence", m)


def _barrel(rng, hue, _):
    m = cylinder(0.32, 0.4, 10, _rgb(0.07, 0.6, 0.5), r_top=0.37)
    m.add(cylinder(0.37, 0.4, 10, _rgb(0.07, 0.6, 0.5), r_top=0.32).transformed((0, 0.4, 0)))
    for y in (0.12, 0.66):
        m.add(cylinder(0.37, 0.05, 10, _rgb(0.6, 0.1, 0.45)).transformed((0, y, 0)))
    return _single("barrel", m)


_BUILDERS = {"tree": _tree, "pine": _pine, "rock": _rock, "crystal": _crystal, "house": _house, "tower": _tower,
             "terrain": _terrain, "dungeon": _dungeon, "character": _character, "chest": _chest, "coin": _coin,
             "potion": _potion, "sword": _sword, "mushroom": _mushroom, "spaceship": _spaceship, "cloud": _cloud,
             "fence": _fence, "barrel": _barrel}


# ---------------------------------------------------------------------------- animation presets

def _rot_track(node: str, axis, angles: list[float], times: list[float]) -> Track:
    return Track(node, "rotation", times, [quat_axis(axis, a) for a in angles])


def animate(scene: Scene, preset: str, duration: float = 1.0) -> Animation:
    """Add an animation clip to ``scene``. Whole-model presets target the root node; character
    presets need the node names :func:`_character` creates (``open`` needs ``lid``)."""
    root = scene.roots[0].name
    names = {n.name for n in scene.nodes()}
    steps = 24
    times = [duration * i / steps for i in range(steps + 1)]
    anim = Animation(preset)
    if preset == "spin":
        anim.tracks.append(_rot_track(root, (0, 1, 0), [2 * math.pi * t / duration for t in times], times))
    elif preset == "bob":
        anim.tracks.append(Track(root, "translation", times,
                                 [(0, 0.15 * math.sin(2 * math.pi * t / duration), 0) for t in times]))
    elif preset == "bounce":
        anim.tracks.append(Track(root, "translation", times,
                                 [(0, 0.5 * abs(math.sin(math.pi * t / duration)), 0) for t in times]))
        anim.tracks.append(Track(root, "scale", times,
                                 [(1 + 0.12 * math.cos(2 * math.pi * t / duration) ** 8, 1 - 0.12 * math.cos(2 * math.pi * t / duration) ** 8,
                                   1 + 0.12 * math.cos(2 * math.pi * t / duration) ** 8) for t in times]))
    elif preset == "pulse":
        anim.tracks.append(Track(root, "scale", times,
                                 [tuple([1 + 0.08 * math.sin(2 * math.pi * t / duration)] * 3) for t in times]))
    elif preset in ("walk", "idle", "wave"):
        if not {"arm_l", "arm_r", "leg_l", "leg_r", "body"} <= names:
            raise ValueError(f"'{preset}' needs a character rig (model kind 'character')")
        swing = {"walk": 0.6, "idle": 0.05, "wave": 0.0}[preset]
        ph = [2 * math.pi * t / duration for t in times]
        anim.tracks += [_rot_track("leg_l", (1, 0, 0), [swing * math.sin(p) for p in ph], times),
                        _rot_track("leg_r", (1, 0, 0), [-swing * math.sin(p) for p in ph], times),
                        _rot_track("arm_l", (1, 0, 0), [-swing * math.sin(p) for p in ph], times)]
        if preset == "wave":
            anim.tracks.append(Track("arm_r", "rotation", times,
                                     [qmul(quat_axis((0, 0, 1), 2.6), quat_axis((1, 0, 0), 0.4 * math.sin(2 * p)))
                                      for p in ph]))
        else:
            anim.tracks.append(_rot_track("arm_r", (1, 0, 0), [swing * math.sin(p) for p in ph], times))
        bob = 0.05 if preset == "walk" else 0.02
        anim.tracks.append(Track("body", "translation", times,
                                 [(0, 0.7 + bob * abs(math.sin(p)), 0) for p in ph]))
    elif preset == "open":
        if "lid" not in names:
            raise ValueError("'open' needs a model with a 'lid' node (model kind 'chest')")
        anim.tracks.append(_rot_track("lid", (1, 0, 0), [-1.9 * min(1.0, 1.4 * t / duration) ** 2 for t in times],
                                      times))
    else:
        raise ValueError(f"unknown animation {preset!r}; choose from {', '.join(ANIMATIONS)}")
    scene.animations.append(anim)
    return anim
