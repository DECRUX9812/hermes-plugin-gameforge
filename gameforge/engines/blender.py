"""Blender, headless: format conversion, LODs, turntable renders, procedural keyframe animation and
arbitrary bpy scripts — all through ``blender -b --python``. Complements the catalog's Blender MCP
plugin (live editing of an open scene); this path needs no add-on and runs unattended."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

KNOWN = ("~/.local/bin", "/usr/local/bin", "/opt/blender", "/snap/bin", "/var/lib/flatpak/exports/bin",
         "~/.local/share/flatpak/exports/bin", "/Applications/Blender.app/Contents/MacOS",
         r"C:\Program Files\Blender Foundation\Blender 4.5", r"C:\Program Files\Blender Foundation\Blender 5.0",
         r"C:\Program Files\Blender Foundation\Blender 5.1", "~/.steam/steam/steamapps/common/Blender")
NAMES = ("blender", "Blender", "org.blender.Blender", "blender.exe")

# One script, dispatched by "op". Runs inside Blender's Python; receives JSON after "--".
_SCRIPT = r'''
import bpy, json, math, os, sys
args = json.loads(sys.argv[sys.argv.index("--") + 1])

def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)

def load(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"): bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx": bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj": bpy.ops.wm.obj_import(filepath=path)
    elif ext == ".stl": bpy.ops.wm.stl_import(filepath=path)
    elif ext == ".ply": bpy.ops.wm.ply_import(filepath=path)
    elif ext == ".blend": bpy.ops.wm.open_mainfile(filepath=path)
    else: raise SystemExit("unsupported input " + ext)

def save(path):
    ext = os.path.splitext(path)[1].lower()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if ext in (".glb", ".gltf"): bpy.ops.export_scene.gltf(filepath=path, export_format="GLB" if ext == ".glb" else "GLTF_SEPARATE")
    elif ext == ".fbx": bpy.ops.export_scene.fbx(filepath=path, path_mode="COPY", embed_textures=True)
    elif ext == ".obj": bpy.ops.wm.obj_export(filepath=path)
    elif ext == ".stl": bpy.ops.wm.stl_export(filepath=path)
    elif ext == ".blend": bpy.ops.wm.save_as_mainfile(filepath=path)
    else: raise SystemExit("unsupported output " + ext)

def meshes():
    return [o for o in bpy.context.scene.objects if o.type == "MESH"]

def bounds():
    import mathutils
    pts = [o.matrix_world @ mathutils.Vector(c) for o in meshes() for c in o.bound_box]
    lo = mathutils.Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = mathutils.Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi

op = args["op"]
result = {"op": op}
if op == "convert":
    clear(); load(args["input"]); save(args["output"]); result["output"] = args["output"]
elif op == "lod":
    clear(); load(args["input"]); outs = []
    base = os.path.splitext(args["output"])[0]
    for i, ratio in enumerate(args.get("ratios", [1.0, 0.5, 0.25])):
        if i:  # every level decimates the original, not the previous level
            clear(); load(args["input"])
            for o in meshes():
                m = o.modifiers.new("lod", "DECIMATE"); m.ratio = ratio
                bpy.context.view_layer.objects.active = o
                bpy.ops.object.modifier_apply(modifier=m.name)
        path = f"{base}_lod{i}.glb"; save(path)
        outs.append({"path": path, "ratio": ratio, "triangles": sum(len(o.data.polygons) for o in meshes())})
    result["lods"] = outs
elif op == "turntable":
    clear(); load(args["input"])
    lo, hi = bounds(); center = (lo + hi) / 2; size = max((hi - lo).x, (hi - lo).y, (hi - lo).z)
    scene = bpy.context.scene
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else ("BLENDER_EEVEE" if "BLENDER_EEVEE" in engines else "CYCLES")
    scene.render.resolution_x = scene.render.resolution_y = args.get("size", 512)
    scene.render.film_transparent = True
    pivot = bpy.data.objects.new("pivot", None); scene.collection.objects.link(pivot); pivot.location = center
    cam_data = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cam_data); scene.collection.objects.link(cam)
    cam.parent = pivot; cam.location = (0, -size * 2.4, size * 0.9); cam.rotation_euler = (math.radians(70), 0, 0)
    scene.camera = cam
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(50), 0, math.radians(30)); sun.data.energy = 3
    frames = args.get("frames", 24); scene.frame_start, scene.frame_end = 1, frames
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"  # constant spin, any Blender version
    pivot.rotation_euler = (0, 0, 0); pivot.keyframe_insert("rotation_euler", frame=1)
    pivot.rotation_euler = (0, 0, math.radians(360 * (frames - 1) / frames)); pivot.keyframe_insert("rotation_euler", frame=frames)
    os.makedirs(args["output"], exist_ok=True)
    scene.render.filepath = os.path.join(args["output"], "frame_")
    scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(animation=True)
    result["frames_dir"] = args["output"]; result["engine"] = scene.render.engine
elif op == "animate":
    clear(); load(args["input"]); fps = 24; frames = int(args.get("duration", 1.0) * fps)
    scene = bpy.context.scene; scene.frame_start, scene.frame_end = 1, frames + 1
    root = bpy.data.objects.new("root", None); scene.collection.objects.link(root)
    for o in list(scene.objects):
        if o.parent is None and o is not root: o.parent = root
    preset = args.get("preset", "spin")
    for f in range(frames + 1):
        t = f / frames
        if preset == "spin": root.rotation_euler = (0, 0, 2 * math.pi * t); root.keyframe_insert("rotation_euler", frame=f + 1)
        elif preset == "bob": root.location = (0, 0, 0.15 * math.sin(2 * math.pi * t)); root.keyframe_insert("location", frame=f + 1)
        elif preset == "pulse":
            s = 1 + 0.08 * math.sin(2 * math.pi * t); root.scale = (s, s, s); root.keyframe_insert("scale", frame=f + 1)
    save(args["output"]); result["output"] = args["output"]
elif op == "info":
    clear(); load(args["input"])
    result["objects"] = [{"name": o.name, "type": o.type, "triangles": sum(len(p.vertices) - 2 for p in o.data.polygons) if o.type == "MESH" else 0}
                         for o in bpy.context.scene.objects]
    result["actions"] = [a.name for a in bpy.data.actions]
    lo, hi = bounds() if meshes() else ((0, 0, 0), (0, 0, 0))
    result["size"] = [round(hi[i] - lo[i], 4) for i in range(3)]
print("GAMEFORGE_RESULT " + json.dumps(result))
'''

OPS = ("convert", "lod", "turntable", "animate", "info", "script")


def locate(explicit: str | None = None) -> str | None:
    if explicit:
        p = os.path.expanduser(explicit)
        return p if os.path.exists(p) else shutil.which(p)
    for name in NAMES:
        hit = shutil.which(name)
        if hit:
            return hit
    for d in KNOWN:
        for name in NAMES:
            p = os.path.join(os.path.expanduser(d), name)
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p
    return None


def run(binary: str, op: str, args: dict, timeout: int = 1800) -> dict:
    """Run one operation (or, with op='script', the agent's own bpy file) in background Blender."""
    if op not in OPS:
        raise ValueError(f"unknown Blender op {op!r}; choose from {', '.join(OPS)}")
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="gameforge-blender-") as tmp:
        if op == "script":
            script = Path(os.path.expanduser(args["script"]))
            payload = json.dumps(args.get("args", {}))
        else:
            script = Path(tmp) / "gameforge_op.py"
            script.write_text(_SCRIPT, encoding="utf-8")
            payload = json.dumps({"op": op, **args})
        proc = subprocess.run([binary, "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(script),
                               "--", payload], capture_output=True, text=True, timeout=timeout)
    out = proc.stdout + proc.stderr
    result = next((json.loads(line.split(" ", 1)[1]) for line in out.splitlines() if line.startswith("GAMEFORGE_RESULT ")), None)
    errors = [ln for ln in out.splitlines() if "Error" in ln or "Traceback" in ln][:20]
    return {"ok": proc.returncode == 0, "result": result, "errors": errors,
            "wall_seconds": round(time.monotonic() - start, 1), "log_tail": out[-1500:]}
