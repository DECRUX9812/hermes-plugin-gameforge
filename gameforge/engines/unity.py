"""Unity: find an editor (Unity Hub installs), scaffold ``unity/`` from GameForge assets and the
shared level, run batch-mode setup and builds, and surface compiler/build errors from the log."""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from .. import project as proj
from . import web

TEMPLATE = Path(__file__).parent / "templates" / "unity_topdown"
HUB_GLOBS = ("~/Unity/Hub/Editor/*/Editor/Unity", "/opt/unity/Editor/Unity", "~/Applications/Unity/Hub/Editor/*/Unity.app/Contents/MacOS/Unity",
             "/Applications/Unity/Hub/Editor/*/Unity.app/Contents/MacOS/Unity",
             r"C:\Program Files\Unity\Hub\Editor\*\Editor\Unity.exe", r"C:\Program Files\Unity*\Editor\Unity.exe")
TARGETS = {"webgl": "WebGL", "android": "Android", "windows": "Windows", "linux": "Linux", "macos": "MacOS"}


def locate(explicit: str | None = None) -> str | None:
    if explicit:
        p = os.path.expanduser(explicit)
        return p if os.path.exists(p) else None
    hit = shutil.which("Unity") or shutil.which("unity-editor")
    if hit:
        return hit
    found = sorted(p for g in HUB_GLOBS for p in glob.glob(os.path.expanduser(g)))
    return found[-1] if found else None  # newest version sorts last


def scaffold(project: Path, title: str, theme: str, seed: int, hero: str) -> dict:
    web_res = web.scaffold(project, title=title, theme=theme, seed=seed, hero=hero)
    cfg = json.loads(Path(web_res["config"]).read_text())
    root = project / "unity"
    res = root / "Assets" / "Resources" / "GameForge"
    res.mkdir(parents=True, exist_ok=True)
    for sub in ("Editor", "Scripts"):
        dst = root / "Assets" / sub
        dst.mkdir(parents=True, exist_ok=True)
        for f in (TEMPLATE / "Assets" / sub).iterdir():
            shutil.copy2(f, dst / f.name)
    web_dir = Path(web_res["web_dir"])

    def put(rel: str) -> str:
        """Copy a web asset into Resources; return its Resources.Load path (no extension)."""
        src = web_dir / rel
        shutil.copy2(src, res / src.name)
        return "GameForge/" + src.stem

    def sheet(png_key: str, json_key: str) -> dict:
        atlas = json.loads((web_dir / cfg["assets"][json_key]).read_text())
        names = list(atlas["frames"])
        rects = [atlas["frames"][n]["frame"] for n in names]
        anims = [{"name": t["name"], "frames": [names.index(f) for f in t["frames"]]} for t in atlas["meta"]["frameTags"]]
        return {"texture": put(cfg["assets"][png_key]), "rects": [{k: r[k] for k in "xywh"} for r in rects], "anims": anims}

    tiles_static = next(f for f in proj.find(project, "tileset", f"{cfg['tiles']['lower']}_{cfg['tiles']['upper']}")["files"]
                        if f.endswith(".png") and not f.endswith("_anim.png"))
    shutil.copy2(project / tiles_static, res / Path(tiles_static).name)
    level = {
        "title": title, "map": cfg["map"], "player": cfg["player"], "enemy": cfg["enemy"],
        "player_sheet": sheet("player", "player_json"), "enemy_sheet": sheet("enemy", "enemy_json"),
        "tiles": "GameForge/" + Path(tiles_static).stem,
        **{k: put(cfg["assets"][k]) for k in ("coin", "chest", "tree", "rock", "flowers", "music")},
        "sfx": [{"name": k, "clips": [put(f) for f in v]} for k, v in cfg["assets"]["sfx"].items()],
        "music_volume": cfg.get("music_volume", 0.35),
    }
    (res / "level.json").write_text(json.dumps(level, indent=1), encoding="utf-8")
    proj.set_meta(project, "engines", {**proj.load(project).get("engines", {}), "unity": "unity/"})
    return {"unity_project": root, "level": res / "level.json",
            "next": "forge_engine engine=unity action=setup (batch-mode scene creation), then action=build target=webgl"}


_ERR = re.compile(r"(error CS\d+|Exception|Build Failed|Scripts have compiler errors|Aborting batchmode)", re.I)


def batch(binary: str, unity_project: Path, method: str, timeout: int = 3600) -> dict:
    log = unity_project / "Logs" / f"gameforge_{method.split('.')[-1]}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    proc = subprocess.run([binary, "-batchmode", "-quit", "-nographics", "-projectPath", str(unity_project),
                           "-executeMethod", method, "-logFile", str(log)], capture_output=True, text=True, timeout=timeout)
    text = log.read_text(errors="replace") if log.exists() else proc.stdout + proc.stderr
    errors = [ln.strip() for ln in text.splitlines() if _ERR.search(ln)][:40]
    return {"ok": proc.returncode == 0 and not any("error CS" in e for e in errors), "exit_code": proc.returncode,
            "errors": errors, "log": log, "wall_seconds": round(time.monotonic() - start, 1),
            "done": "GAMEFORGE_SETUP_DONE" in text or "GAMEFORGE_BUILD Succeeded" in text}


def setup(binary: str, project: Path) -> dict:
    return batch(binary, project / "unity", "GameForge.EditorTools.Setup.CreateScene")


def build(binary: str, project: Path, target: str) -> dict:
    if target not in TARGETS:
        raise ValueError(f"unknown Unity target {target!r}; choose from {', '.join(TARGETS)}")
    return batch(binary, project / "unity", f"GameForge.EditorTools.Builds.{TARGETS[target]}")
