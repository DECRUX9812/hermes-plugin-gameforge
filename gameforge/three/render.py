"""A tiny software rasterizer for previews: flat-shaded, painter-sorted, supersampled. Good enough
to show a low-poly model, a turntable, or an animation clip without Blender or a GPU — and it can
load any .glb (AI-generated ones included) for a quick look."""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path

from PIL import Image, ImageDraw

from .mesh import Mesh, Node, Scene, Track, cross, dot, norm, qrot, vsub

LIGHT = norm((-0.5, 0.85, 0.6))


def _sample(track: Track, t: float):
    times = track.times
    if t <= times[0]:
        return track.values[0]
    if t >= times[-1]:
        return track.values[-1]
    for i in range(len(times) - 1):
        if times[i] <= t <= times[i + 1]:
            u = (t - times[i]) / (times[i + 1] - times[i] or 1)
            a, b = track.values[i], track.values[i + 1]
            if track.path == "rotation" and sum(x * y for x, y in zip(a, b)) < 0:
                b = tuple(-x for x in b)
            v = tuple(x + (y - x) * u for x, y in zip(a, b))
            if track.path == "rotation":
                n = math.sqrt(sum(x * x for x in v)) or 1
                v = tuple(x / n for x in v)
            return v
    return track.values[-1]


def world_triangles(scene: Scene, anim_name: str | None = None, t: float = 0.0):
    """Yield (a, b, c, color) in world space, applying an animation pose at time ``t``."""
    pose: dict[tuple[str, str], tuple] = {}
    if anim_name:
        anim = next((a for a in scene.animations if a.name == anim_name), None)
        if anim:
            for tr in anim.tracks:
                pose[(tr.node, tr.path)] = _sample(tr, t)

    def visit(node: Node, xf):
        tr = pose.get((node.name, "translation"), node.translation)
        rot = pose.get((node.name, "rotation"), node.rotation)
        sc = pose.get((node.name, "scale"), node.scale)

        def local(v, tr=tr, rot=rot, sc=sc):
            return xf(_add(qrot(rot, (v[0] * sc[0], v[1] * sc[1], v[2] * sc[2])), tr))
        if node.mesh is not None:
            m = node.mesh
            for (ia, ib, ic), col in zip(m.faces, m.colors):
                yield local(m.verts[ia]), local(m.verts[ib]), local(m.verts[ic]), col
        for child in node.children:
            yield from visit(child, local)

    for root in scene.roots:
        yield from visit(root, lambda v: v)


def _add(a, b):
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def render(scene: Scene, size: int = 512, yaw: float = 0.6, pitch: float = 0.45, anim: str | None = None,
           t: float = 0.0, background: tuple = (32, 36, 52), fit: tuple | None = None) -> Image.Image:
    tris = list(world_triangles(scene, anim, t))
    if not tris:
        return Image.new("RGB", (size, size), background)
    lo, hi = fit or _bounds(tris)
    center = tuple((lo[i] + hi[i]) / 2 for i in range(3))
    radius = max(0.001, max(hi[i] - lo[i] for i in range(3)) * 0.62)
    dist = radius * 3.2
    cam = (center[0] + dist * math.sin(yaw) * math.cos(pitch), center[1] + dist * math.sin(pitch),
           center[2] + dist * math.cos(yaw) * math.cos(pitch))
    fwd = norm(vsub(center, cam))
    right = norm(cross(fwd, (0, 1, 0)))
    up = cross(right, fwd)
    ss = 2
    w = size * ss
    focal = w / (2 * math.tan(math.radians(22)))
    img = Image.new("RGB", (w, w), background)
    _floor_gradient(img, background)
    draw = ImageDraw.Draw(img)
    projected = []
    for a, b, c, col in tris:
        n = norm(cross(vsub(b, a), vsub(c, a)))
        centroid = tuple((a[i] + b[i] + c[i]) / 3 for i in range(3))
        to_cam = vsub(cam, centroid)
        if dot(n, to_cam) <= 0:
            continue
        pts, depth = [], 0.0
        for v in (a, b, c):
            rel = vsub(v, cam)
            z = dot(rel, fwd)
            if z <= 1e-4:
                break
            pts.append((w / 2 + focal * dot(rel, right) / z, w / 2 - focal * dot(rel, up) / z))
            depth += z
        else:
            lam = 0.38 + 0.62 * max(0.0, dot(n, LIGHT))
            rim = 0.12 * max(0.0, 1 - abs(dot(n, norm(to_cam)))) ** 2
            shade = tuple(min(255, int((col[k] * lam + rim) * 255)) for k in range(3))
            projected.append((depth, pts, shade))
    projected.sort(key=lambda p: -p[0])
    for _, pts, shade in projected:
        draw.polygon(pts, fill=shade)
    return img.resize((size, size), Image.LANCZOS)


def _floor_gradient(img: Image.Image, bg: tuple) -> None:
    draw = ImageDraw.Draw(img)
    h = img.height
    for y in range(0, h, 4):
        k = y / h
        c = tuple(int(bg[i] * (1.15 - 0.35 * k)) for i in range(3))
        draw.rectangle([0, y, img.width, y + 4], fill=c)


def _bounds(tris):
    xs = [v[0] for t in tris for v in t[:3]]
    ys = [v[1] for t in tris for v in t[:3]]
    zs = [v[2] for t in tris for v in t[:3]]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def turntable(scene: Scene, path: str | Path, frames: int = 24, size: int = 320, anim: str | None = None,
              duration: float = 1.0) -> Path:
    """Animated GIF orbiting the model (and playing ``anim`` if given)."""
    fit = _bounds(list(world_triangles(scene)))
    imgs = [render(scene, size, yaw=2 * math.pi * i / frames, anim=anim, t=duration * (i % frames) / frames, fit=fit)
            for i in range(frames)]
    path = Path(path)
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=int(2400 / frames), loop=0)
    return path


def contact_sheet(scene: Scene, path: str | Path, size: int = 256) -> Path:
    """Front, three-quarter, side and top views side by side."""
    views = [(0.0, 0.2), (0.75, 0.45), (math.pi / 2, 0.2), (0.3, 1.35)]
    fit = _bounds(list(world_triangles(scene)))
    sheet = Image.new("RGB", (size * 4, size))
    for i, (yaw, pitch) in enumerate(views):
        sheet.paste(render(scene, size, yaw, pitch, fit=fit), (i * size, 0))
    path = Path(path)
    sheet.save(path)
    return path


# ---------------------------------------------------------------------------- .glb loading

def load_glb(path: str | Path) -> Scene:
    """Geometry + base colours of any glTF binary (textures are approximated by the material's
    base colour factor or COLOR_0)."""
    data = Path(path).read_bytes()
    jlen, _ = struct.unpack_from("<II", data, 12)
    gltf = json.loads(data[20:20 + jlen])
    off = 20 + jlen
    blen, _ = struct.unpack_from("<II", data, off)
    binary = data[off + 8:off + 8 + blen]

    def accessor(i: int) -> list:
        acc = gltf["accessors"][i]
        view = gltf["bufferViews"][acc["bufferView"]]
        ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[acc["type"]]
        fmt, size = {5126: ("f", 4), 5123: ("H", 2), 5125: ("I", 4), 5121: ("B", 1)}[acc["componentType"]]
        stride = view.get("byteStride", size * ncomp)
        base = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        out = []
        for k in range(acc["count"]):
            vals = struct.unpack_from(f"<{ncomp}{fmt}", binary, base + k * stride)
            out.append(vals if ncomp > 1 else vals[0])
        return out

    def mesh_of(mi: int) -> Mesh:
        mesh = Mesh()
        for prim in gltf["meshes"][mi]["primitives"]:
            pos = accessor(prim["attributes"]["POSITION"])
            idx = accessor(prim["indices"]) if "indices" in prim else list(range(len(pos)))
            mat = gltf.get("materials", [{}])[prim.get("material", 0)] if gltf.get("materials") else {}
            base = tuple(mat.get("pbrMetallicRoughness", {}).get("baseColorFactor", [0.8, 0.8, 0.8, 1])[:3])
            vcol = accessor(prim["attributes"]["COLOR_0"]) if "COLOR_0" in prim["attributes"] else None
            start = len(mesh.verts)
            mesh.verts += [tuple(p) for p in pos]
            for k in range(0, len(idx) - 2, 3):
                a, b, c = idx[k], idx[k + 1], idx[k + 2]
                mesh.faces.append((start + a, start + b, start + c))
                if vcol:
                    col = tuple(min(1.0, max(0.0, vcol[a][j] if isinstance(vcol[a][j], float) else vcol[a][j] / 65535))
                                ** (1 / 2.2) for j in range(3))
                else:
                    col = tuple(min(1.0, c_ ** (1 / 2.2)) for c_ in base)
                mesh.colors.append(col)
        return mesh

    def node_of(ni: int) -> Node:
        nd = gltf["nodes"][ni]
        node = Node(nd.get("name", f"node{ni}"), mesh_of(nd["mesh"]) if "mesh" in nd else None,
                    tuple(nd.get("translation", (0, 0, 0))), tuple(nd.get("rotation", (0, 0, 0, 1))),
                    tuple(nd.get("scale", (1, 1, 1))))
        node.children = [node_of(c) for c in nd.get("children", [])]
        return node

    scene_idx = gltf.get("scene", 0)
    roots = gltf.get("scenes", [{"nodes": list(range(len(gltf.get("nodes", []))))}])[scene_idx]["nodes"]
    return Scene(roots=[node_of(r) for r in roots])


