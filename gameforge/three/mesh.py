"""Minimal mesh + scene graph for low-poly assets: per-face colours, flat shading, quaternion
node transforms and keyframe animations — exactly what glTF 2.0 can carry."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

Vec3 = tuple[float, float, float]
Quat = tuple[float, float, float, float]  # x, y, z, w (glTF order)
RGB = tuple[float, float, float]


@dataclass
class Mesh:
    verts: list[Vec3] = field(default_factory=list)
    faces: list[tuple[int, int, int]] = field(default_factory=list)
    colors: list[RGB] = field(default_factory=list)  # one per face

    def add(self, other: "Mesh") -> "Mesh":
        base = len(self.verts)
        self.verts += other.verts
        self.faces += [(a + base, b + base, c + base) for a, b, c in other.faces]
        self.colors += other.colors
        return self

    def transformed(self, t: Vec3 = (0, 0, 0), s: Vec3 | float = 1.0, r: Quat = (0, 0, 0, 1)) -> "Mesh":
        sv = (s, s, s) if isinstance(s, (int, float)) else s
        verts = [vadd(qrot(r, (v[0] * sv[0], v[1] * sv[1], v[2] * sv[2])), t) for v in self.verts]
        return Mesh(verts, list(self.faces), list(self.colors))

    def paint(self, color: RGB) -> "Mesh":
        self.colors = [color] * len(self.faces)
        return self

    def jitter(self, amount: float, rng: random.Random) -> "Mesh":
        """Displace shared vertices consistently (welded by position) so facets stay closed."""
        moved: dict[tuple, Vec3] = {}
        out = []
        for v in self.verts:
            key = tuple(round(c, 4) for c in v)
            if key not in moved:
                moved[key] = (v[0] + rng.uniform(-amount, amount), v[1] + rng.uniform(-amount, amount),
                              v[2] + rng.uniform(-amount, amount))
            out.append(moved[key])
        self.verts = out
        return self

    def bounds(self) -> tuple[Vec3, Vec3]:
        xs, ys, zs = zip(*self.verts)
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


@dataclass
class Node:
    name: str
    mesh: Mesh | None = None
    translation: Vec3 = (0.0, 0.0, 0.0)
    rotation: Quat = (0.0, 0.0, 0.0, 1.0)
    scale: Vec3 = (1.0, 1.0, 1.0)
    children: list["Node"] = field(default_factory=list)

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


@dataclass
class Track:
    node: str
    path: str  # translation | rotation | scale
    times: list[float]
    values: list[tuple]
    interpolation: str = "LINEAR"


@dataclass
class Animation:
    name: str
    tracks: list[Track] = field(default_factory=list)


@dataclass
class Scene:
    roots: list[Node] = field(default_factory=list)
    animations: list[Animation] = field(default_factory=list)

    def nodes(self) -> list[Node]:
        return [n for r in self.roots for n in r.walk()]


# ---------------------------------------------------------------------------- vector math

def vadd(a: Vec3, b: Vec3) -> Vec3:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def vsub(a: Vec3, b: Vec3) -> Vec3:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def cross(a: Vec3, b: Vec3) -> Vec3:
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]


def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def norm(a: Vec3) -> Vec3:
    length = math.sqrt(dot(a, a)) or 1.0
    return a[0] / length, a[1] / length, a[2] / length


def quat_axis(axis: Vec3, angle: float) -> Quat:
    ax = norm(axis)
    s = math.sin(angle / 2)
    return ax[0] * s, ax[1] * s, ax[2] * s, math.cos(angle / 2)


def qmul(a: Quat, b: Quat) -> Quat:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def qrot(q: Quat, v: Vec3) -> Vec3:
    x, y, z, w = q
    u = (x, y, z)
    uv = cross(u, v)
    uuv = cross(u, uv)
    return (v[0] + 2 * (w * uv[0] + uuv[0]), v[1] + 2 * (w * uv[1] + uuv[1]), v[2] + 2 * (w * uv[2] + uuv[2]))


# ---------------------------------------------------------------------------- primitives

def box(sx: float = 1, sy: float = 1, sz: float = 1, color: RGB = (0.8, 0.8, 0.8)) -> Mesh:
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    v = [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
         (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]
    quads = [(4, 5, 6, 7), (1, 0, 3, 2), (0, 4, 7, 3), (5, 1, 2, 6), (7, 6, 2, 3), (0, 1, 5, 4)]
    faces = [t for a, b, c, d in quads for t in ((a, b, c), (a, c, d))]
    return Mesh(v, faces, [color] * len(faces))


def cylinder(r: float = 0.5, h: float = 1, seg: int = 8, color: RGB = (0.8, 0.8, 0.8), r_top: float | None = None) -> Mesh:
    rt = r if r_top is None else r_top
    v: list[Vec3] = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        v.append((r * math.cos(a), 0, r * math.sin(a)))
        v.append((rt * math.cos(a), h, rt * math.sin(a)))
    bottom, top = len(v), len(v) + 1
    v += [(0, 0, 0), (0, h, 0)]
    faces = []
    for i in range(seg):
        a0, a1 = 2 * i, 2 * i + 1
        b0, b1 = 2 * ((i + 1) % seg), 2 * ((i + 1) % seg) + 1
        faces += [(a0, a1, b1), (a0, b1, b0), (bottom, a0, b0)]
        if rt > 1e-6:
            faces.append((top, b1, a1))
    return Mesh(v, faces, [color] * len(faces))


def cone(r: float = 0.5, h: float = 1, seg: int = 8, color: RGB = (0.8, 0.8, 0.8)) -> Mesh:
    return cylinder(r, h, seg, color, r_top=0.0)


def icosphere(r: float = 0.5, subdiv: int = 1, color: RGB = (0.8, 0.8, 0.8)) -> Mesh:
    t = (1 + math.sqrt(5)) / 2
    v = [norm(p) for p in [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t),
                           (0, 1, -t), (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]]
    faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
             (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11),
             (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    for _ in range(subdiv):
        cache: dict[tuple[int, int], int] = {}

        def mid(a: int, b: int) -> int:
            key = (min(a, b), max(a, b))
            if key not in cache:
                v.append(norm(tuple((v[a][k] + v[b][k]) / 2 for k in range(3))))
                cache[key] = len(v) - 1
            return cache[key]
        faces = [f for a, b, c in faces for f in ((a, mid(a, b), mid(c, a)), (b, mid(b, c), mid(a, b)),
                                                   (c, mid(c, a), mid(b, c)), (mid(a, b), mid(b, c), mid(c, a)))]
    return Mesh([(p[0] * r, p[1] * r, p[2] * r) for p in v], faces, [color] * len(faces))


def prism_roof(w: float, d: float, h: float, color: RGB) -> Mesh:
    hw, hd = w / 2, d / 2
    v = [(-hw, 0, -hd), (hw, 0, -hd), (hw, 0, hd), (-hw, 0, hd), (0, h, -hd), (0, h, hd)]
    faces = [(0, 4, 1), (3, 2, 5), (0, 3, 5), (0, 5, 4), (1, 4, 5), (1, 5, 2), (0, 1, 2), (0, 2, 3)]
    return Mesh(v, faces, [color] * len(faces))
