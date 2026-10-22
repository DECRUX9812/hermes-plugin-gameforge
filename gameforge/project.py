"""The game project on disk: where assets go, and ``gameforge.json`` — the asset ledger that
records every generated file with the exact recipe (tool, preset, seed, params) that made it, so
any asset can be regenerated, varied or credited later."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

LEDGER = "gameforge.json"
ASSET_DIRS = {"sfx": "assets/sfx", "music": "assets/music", "voice": "assets/voice", "sprite": "assets/sprites",
              "tileset": "assets/tiles", "model": "assets/models", "playtest": "playtests", "export": "dist"}


def resolve_project(path: str | None, default: str | None = None) -> Path:
    """Relative paths resolve against the agent's working directory (``TERMINAL_CWD`` when the
    host sets it), not the Hermes process cwd."""
    raw = path or default or "game"
    p = Path(os.path.expanduser(raw))
    if not p.is_absolute():
        p = Path(os.environ.get("TERMINAL_CWD") or os.getcwd()) / p
    p.mkdir(parents=True, exist_ok=True)
    return p.resolve()


def asset_dir(project: Path, kind: str) -> Path:
    d = project / ASSET_DIRS[kind]
    d.mkdir(parents=True, exist_ok=True)
    return d


def safe_name(name: str, fallback: str = "asset") -> str:
    clean = re.sub(r"[^A-Za-z0-9_-]+", "_", name or "").strip("_")[:48]
    return clean or fallback


def load(project: Path) -> dict:
    f = project / LEDGER
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {"name": project.name, "created": _now(), "assets": []}


def _rel(project: Path, path: Path) -> str:
    """Project-relative path with forward slashes, on every platform."""
    return path.resolve().relative_to(project).as_posix()


def record(project: Path, kind: str, files: list[Path], recipe: dict, name: str) -> dict:
    """Append (or replace by name+kind) a ledger entry. Paths are stored project-relative,
always with ``/`` separators so the ledger is byte-identical on Windows and POSIX (Godot
``res://`` and the Unity/Unreal importers read these back verbatim)."""
    data = load(project)
    entry = {"name": name, "kind": kind, "files": [_rel(project, f) for f in files],
             "recipe": recipe, "created": _now(), "license": recipe.get("license", "CC0-1.0 (procedurally generated)")}
    data["assets"] = [a for a in data["assets"] if not (a["name"] == name and a["kind"] == kind)] + [entry]
    (project / LEDGER).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return entry


def find(project: Path, kind: str, name: str | None = None) -> dict | None:
    for a in reversed(load(project)["assets"]):
        if a["kind"] == kind and (name is None or a["name"] == name):
            return a
    return None


def summary(project: Path) -> dict:
    data = load(project)
    counts: dict[str, int] = {}
    for a in data["assets"]:
        counts[a["kind"]] = counts.get(a["kind"], 0) + 1
    return {"project": str(project), "assets": counts, "total": len(data["assets"]),
            "engines": data.get("engines", {}), "latest": [a["name"] + f" ({a['kind']})" for a in data["assets"][-8:]]}


def set_meta(project: Path, key: str, value) -> None:
    data = load(project)
    data[key] = value
    (project / LEDGER).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")
