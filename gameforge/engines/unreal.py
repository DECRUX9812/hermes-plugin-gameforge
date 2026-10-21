"""Unreal Engine: bring GameForge assets into a .uproject through the editor's Python API. Live editor
control (actors, blueprints, PIE) is the job of the `unreal-mcp` optional skill; this module covers
the unattended path: a generated import script, run by UnrealEditor-Cmd when it can be found."""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
from pathlib import Path

from .. import project as proj

GLOBS = ("~/UnrealEngine/Engine/Binaries/Linux/UnrealEditor-Cmd", "/opt/UnrealEngine/Engine/Binaries/Linux/UnrealEditor-Cmd",
         "/Users/Shared/Epic Games/UE_*/Engine/Binaries/Mac/UnrealEditor-Cmd",
         r"C:\Program Files\Epic Games\UE_*\Engine\Binaries\Win64\UnrealEditor-Cmd.exe")

IMPORTABLE = {".glb", ".gltf", ".fbx", ".obj", ".png", ".wav", ".tga", ".jpg"}

_IMPORT = r'''
import json, unreal
cfg = json.loads(r"""{payload}""")
tasks = []
for item in cfg["files"]:
    t = unreal.AssetImportTask()
    t.filename = item["src"]
    t.destination_path = item["dest"]
    t.automated = True
    t.replace_existing = True
    t.save = True
    tasks.append(t)
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
for t in tasks:
    unreal.log("GAMEFORGE_IMPORTED " + t.filename + " -> " + ", ".join(t.imported_object_paths))
for path in unreal.EditorAssetLibrary.list_assets(cfg["root"], recursive=True):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    if isinstance(asset, unreal.Texture2D):  # pixel art: nearest filtering, no mips
        asset.set_editor_property("filter", unreal.TextureFilter.TF_NEAREST)
        asset.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        asset.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_PIXELS2D)
        unreal.EditorAssetLibrary.save_loaded_asset(asset)
'''


def locate(explicit: str | None = None) -> str | None:
    if explicit:
        p = os.path.expanduser(explicit)
        return p if os.path.exists(p) else None
    hit = shutil.which("UnrealEditor-Cmd")
    if hit:
        return hit
    found = sorted(p for g in GLOBS for p in glob.glob(os.path.expanduser(g)))
    return found[-1] if found else None


def import_script(project: Path, root: str = "/Game/GameForge") -> Path:
    """Write ``unreal_import.py`` covering every importable file in the GameForge ledger."""
    ledger = proj.load(project)          # empty ledger for a fresh project instead of FileNotFoundError
    files = []
    for asset in ledger["assets"]:
        for rel in asset["files"]:
            src = project / rel
            if src.suffix.lower() in IMPORTABLE and not src.name.endswith(("_preview.png", "_views.png", "_sheet_preview.png")):
                files.append({"src": str(src.resolve()), "dest": f"{root}/{asset['kind'].capitalize()}"})
    script = project / "unreal_import.py"
    project.mkdir(parents=True, exist_ok=True)     # a fresh path has no directory to write into yet
    script.write_text(_IMPORT.replace("{payload}", json.dumps({"files": files, "root": root})), encoding="utf-8")
    return script


def run_import(binary: str, uproject: Path, script: Path, timeout: int = 3600) -> dict:
    proc = subprocess.run([binary, str(uproject), "-run=pythonscript", f"-script={script}", "-unattended", "-nop4",
                           "-nosplash", "-stdout"], capture_output=True, text=True, timeout=timeout)
    out = proc.stdout + proc.stderr
    return {"ok": proc.returncode == 0, "imported": [ln.split("GAMEFORGE_IMPORTED ", 1)[1] for ln in out.splitlines()
                                                    if "GAMEFORGE_IMPORTED " in ln][:200],
            "errors": [ln for ln in out.splitlines() if "Error:" in ln][:30]}
