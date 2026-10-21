"""glTF 2.0 binary (.glb) writer: flat-shaded meshes with vertex colours, a node hierarchy and
keyframe animations. Opens in Godot, Unity (glTFast), Unreal (Interchange), Blender, three.js."""

from __future__ import annotations

import json
import struct
from pathlib import Path

from .mesh import Scene, cross, norm, vsub

FLOAT, USHORT, UINT = 5126, 5123, 5125
ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 34962, 34963


class _Bin:
    def __init__(self) -> None:
        self.data = bytearray()
        self.views: list[dict] = []
        self.accessors: list[dict] = []

    def add(self, raw: bytes, target: int | None, comp: int, count: int, kind: str,
            minmax: tuple[list, list] | None = None) -> int:
        while len(self.data) % 4:
            self.data += b"\x00"
        view = {"buffer": 0, "byteOffset": len(self.data), "byteLength": len(raw)}
        if target:
            view["target"] = target
        self.data += raw
        self.views.append(view)
        acc = {"bufferView": len(self.views) - 1, "componentType": comp, "count": count, "type": kind}
        if minmax:
            acc["min"], acc["max"] = minmax
        self.accessors.append(acc)
        return len(self.accessors) - 1


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def write_glb(scene: Scene, path: str | Path, generator: str = "hermes-gameforge") -> Path:
    b = _Bin()
    meshes: list[dict] = []
    gl_nodes: list[dict] = []
    index_of: dict[int, int] = {}
    all_nodes = scene.nodes()
    for i, node in enumerate(all_nodes):
        index_of[id(node)] = i

    for node in all_nodes:
        entry: dict = {"name": node.name}
        if node.translation != (0.0, 0.0, 0.0):
            entry["translation"] = list(node.translation)
        if node.rotation != (0.0, 0.0, 0.0, 1.0):
            entry["rotation"] = list(node.rotation)
        if node.scale != (1.0, 1.0, 1.0):
            entry["scale"] = list(node.scale)
        if node.children:
            entry["children"] = [index_of[id(c)] for c in node.children]
        if node.mesh is not None and node.mesh.faces:
            entry["mesh"] = len(meshes)
            meshes.append(_mesh(b, node.name, node.mesh))
        gl_nodes.append(entry)

    animations = []
    for anim in scene.animations:
        samplers, channels = [], []
        for tr in anim.tracks:
            target = next((index_of[id(n)] for n in all_nodes if n.name == tr.node), None)
            if target is None:
                continue
            t_raw = struct.pack(f"<{len(tr.times)}f", *tr.times)
            t_acc = b.add(t_raw, None, FLOAT, len(tr.times), "SCALAR", ([min(tr.times)], [max(tr.times)]))
            flat = [c for v in tr.values for c in v]
            kind = "VEC4" if tr.path == "rotation" else "VEC3"
            v_acc = b.add(struct.pack(f"<{len(flat)}f", *flat), None, FLOAT, len(tr.values), kind)
            samplers.append({"input": t_acc, "output": v_acc, "interpolation": tr.interpolation})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": target, "path": tr.path}})
        if channels:
            animations.append({"name": anim.name, "samplers": samplers, "channels": channels})

    roots = [index_of[id(r)] for r in scene.roots]
    gltf = {
        "asset": {"version": "2.0", "generator": generator},
        "scene": 0, "scenes": [{"nodes": roots}], "nodes": gl_nodes, "meshes": meshes,
        "materials": [{"name": "vertex_color", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1],
                                                                         "metallicFactor": 0.0, "roughnessFactor": 0.85}}],
        "buffers": [{"byteLength": len(b.data)}], "bufferViews": b.views, "accessors": b.accessors,
    }
    if animations:
        gltf["animations"] = animations
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    binary = bytes(b.data) + b"\x00" * (-len(b.data) % 4)
    total = 12 + 8 + len(js) + 8 + len(binary)
    out = struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(js), 0x4E4F534A) + js
    out += struct.pack("<II", len(binary), 0x004E4942) + binary
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out)
    return path


def _mesh(b: _Bin, name: str, mesh) -> dict:
    pos, nrm, col = [], [], []
    for (ia, ib, ic), color in zip(mesh.faces, mesh.colors):
        a, bb, c = mesh.verts[ia], mesh.verts[ib], mesh.verts[ic]
        n = norm(cross(vsub(bb, a), vsub(c, a)))
        lin = tuple(_srgb_to_linear(x) for x in color)
        for v in (a, bb, c):
            pos.extend(v)
            nrm.extend(n)
            col.extend((*lin, 1.0))
    count = len(pos) // 3
    xs, ys, zs = pos[0::3], pos[1::3], pos[2::3]
    p_acc = b.add(struct.pack(f"<{len(pos)}f", *pos), ARRAY_BUFFER, FLOAT, count, "VEC3",
                  ([min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]))
    n_acc = b.add(struct.pack(f"<{len(nrm)}f", *nrm), ARRAY_BUFFER, FLOAT, count, "VEC3")
    c_acc = b.add(struct.pack(f"<{len(col)}f", *col), ARRAY_BUFFER, FLOAT, count, "VEC4")
    comp, fmt = (USHORT, "H") if count < 65536 else (UINT, "I")
    idx = list(range(count))
    raw = struct.pack(f"<{count}{fmt}", *idx)
    i_acc = b.add(raw, ELEMENT_ARRAY_BUFFER, comp, count, "SCALAR")
    return {"name": name, "primitives": [{"attributes": {"POSITION": p_acc, "NORMAL": n_acc, "COLOR_0": c_acc},
                                          "indices": i_acc, "material": 0}]}


def read_glb_json(path: str | Path) -> dict:
    """The JSON chunk of a .glb (for inspection and tests)."""
    data = Path(path).read_bytes()
    magic, version, _ = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67 or version != 2:
        raise ValueError("not a glTF 2.0 binary")
    length, kind = struct.unpack_from("<II", data, 12)
    if kind != 0x4E4F534A:
        raise ValueError("first chunk is not JSON")
    return json.loads(data[20:20 + length])
