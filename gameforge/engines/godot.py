"""Godot 4: find the editor, scaffold a project from GameForge assets (the game project root *is* the
Godot project, so every ``res://assets/...`` path in generated .tres files resolves), import, run
headless and parse errors, bot-playtest at faster-than-real-time, and export with presets."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from .. import project as proj
from . import web

TEMPLATE = Path(__file__).parent / "templates" / "godot_topdown"
NAMES = ("godot4", "godot", "Godot", "godot-mono", "godot4-mono")
KNOWN = ("~/.local/bin", "/usr/local/bin", "/opt/godot", "/Applications/Godot.app/Contents/MacOS",
         "/var/lib/flatpak/exports/bin", "~/.local/share/flatpak/exports/bin", "/snap/bin",
         "~/.steam/steam/steamapps/common/Godot Engine", r"C:\Program Files\Godot", r"C:\Godot")
FLATPAK_ID = "org.godotengine.Godot"

PRESETS = {
    "web": ("Web", "Web", "dist/godot-web/index.html"),
    "linux": ("Linux", "Linux", "dist/godot-linux/game.x86_64"),
    "windows": ("Windows Desktop", "Windows Desktop", "dist/godot-windows/game.exe"),
    "macos": ("macOS", "macOS", "dist/godot-macos/game.zip"),
    "android": ("Android", "Android", "dist/godot-android/game.apk"),
}


def locate(explicit: str | None = None) -> str | None:
    if explicit:
        p = os.path.expanduser(explicit)
        return p if os.path.exists(p) else shutil.which(p)
    for name in NAMES:
        hit = shutil.which(name)
        if hit:
            return hit
    for d in KNOWN:
        for name in (*NAMES, FLATPAK_ID, "Godot.exe"):
            p = os.path.join(os.path.expanduser(d), name)
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p
    return None


def version(binary: str) -> str:
    out = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=30)
    return out.stdout.strip().splitlines()[-1] if out.stdout.strip() else "unknown"


def _split_version(ver: str) -> tuple[str, str]:
    """'4.7.1.stable.official.a13da4feb' -> ('4.7.1', 'stable')."""
    parts = ver.split(".")
    i = next((k for k, p in enumerate(parts) if not p.isdigit()), len(parts))
    return ".".join(parts[:i]), (parts[i] if i < len(parts) else "stable")


def templates_dir(ver: str) -> Path | None:
    """Where export templates for ``ver`` must live (Godot names the folder <number>.<status>)."""
    number, status = _split_version(ver)
    for base in ("~/.local/share/godot/export_templates", "~/Library/Application Support/Godot/export_templates",
                 "%APPDATA%/Godot/export_templates"):
        d = Path(os.path.expandvars(os.path.expanduser(base))) / f"{number}.{status}"
        if d.is_dir() and any(d.iterdir()):
            return d
    return None


def scaffold(project: Path, title: str, theme: str, seed: int, hero: str) -> dict:
    """Godot project at the game root, reusing (or first generating) the web build's assets and level."""
    web_res = web.scaffold(project, title=title, theme=theme, seed=seed, hero=hero)
    cfg = json.loads(Path(web_res["config"]).read_text(encoding="utf-8"))
    th = web.THEMES[theme]

    def res(kind: str, name: str, suffix: str) -> str:
        entry = proj.find(project, kind, name)
        if entry is None:
            raise RuntimeError(f"ledger has no {kind} '{name}'")
        rel = next(f for f in entry["files"] if f.endswith(suffix))
        return "res://" + rel.replace(os.sep, "/")

    tiles_name = f"{th['lower']}_{th['upper']}"
    cfg["godot"] = {
        "tileset": res("tileset", tiles_name, ".tres"),
        "player_frames": res("sprite", "player", "_frames.tres"), "enemy_frames": res("sprite", "enemy", "_frames.tres"),
        "coin": res("sprite", "items", "_coin.png"), "chest": res("sprite", "items", "_chest.png"),
        "tree": res("sprite", "props", f"_{th['tree']}_0.png"), "rock": res("sprite", "props", "_rock_1.png"),
        "flowers": res("sprite", "props", "_flowers_2.png"),
        "sfx": {k: ["res://" + f for f in proj.find(project, "sfx", k)["files"] if f.endswith(".wav")]
                for k in cfg["assets"]["sfx"]},
        "music": res("music", "theme", ".wav"),
    }
    (project / "level.json").write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    (project / "project.godot").write_text(_project_godot(title), encoding="utf-8")
    shutil.copy2(TEMPLATE / "main.gd", project / "main.gd")
    shutil.copy2(TEMPLATE / "main.tscn", project / "main.tscn")
    addon = project / "addons" / "gameforge"
    addon.mkdir(parents=True, exist_ok=True)
    for f in (TEMPLATE / "addons" / "gameforge").iterdir():
        shutil.copy2(f, addon / f.name)
    for skip in ("web", "playtests", "dist"):  # keep Godot from importing build output and reports
        (project / skip).mkdir(exist_ok=True)
        (project / skip / ".gdignore").touch()
    (project / "export_presets.cfg").write_text(export_presets(), encoding="utf-8")
    proj.set_meta(project, "engines", {**proj.load(project).get("engines", {}), "godot": "project.godot"})
    return {"project_godot": project / "project.godot", "main": project / "main.gd", "level": project / "level.json",
            "presets": list(PRESETS)}


def _project_godot(title: str) -> str:
    return f"""; Generated by Hermes GameForge
config_version=5

[application]

config/name="{title}"
run/main_scene="res://main.tscn"
config/features=PackedStringArray("4.3", "GL Compatibility")

[display]

window/size/viewport_width=320
window/size/viewport_height=240
window/size/window_width_override=960
window/size/window_height_override=720
window/stretch/mode="viewport"

[rendering]

textures/canvas_textures/default_texture_filter=0
renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
"""


def export_presets() -> str:
    blocks = []
    for i, (name, platform, path) in enumerate(PRESETS.values()):
        blocks.append(f"""[preset.{i}]

name="{name}"
platform="{platform}"
runnable=true
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter="level.json"
exclude_filter="web/*, playtests/*, dist/*"
export_path="{path}"
encryption_include_filters=""
encryption_exclude_filters=""
encrypt_pck=false
encrypt_directory=false

[preset.{i}.options]

custom_template/debug=""
custom_template/release=""
""" + ("progressive_web_app/enabled=true\nhtml/canvas_resize_policy=2\n"
       # Single-threaded web export: a threaded build needs SharedArrayBuffer, which means
       # COOP/COEP headers most static hosts (and plain file://) do not send, so the game
       # would refuse to start. Single-threaded runs anywhere.
       "threads/export_type=0\n" if platform == "Web" else ""))
    return "\n".join(blocks)


_EXIT_NOISE = ("still in use at exit", "leaked at exit", "Pages in use exist at exit")
_ERR = re.compile(r"^(SCRIPT ERROR|ERROR|USER ERROR|WARNING|USER WARNING|Parse Error)[: ]", re.M)


def parse_log(text: str) -> list[dict]:
    """Godot prints an error line followed by indented ``at:`` lines; keep them together."""
    out: list[dict] = []
    for line in text.splitlines():
        m = _ERR.match(line.strip())
        if m:
            noise = any(n in line for n in _EXIT_NOISE)  # quit-time bookkeeping, not a game bug
            out.append({"level": "warning" if "WARNING" in m.group(1) or noise else "error", "text": line.strip()})
        elif out and line.strip().startswith(("at:", "GDScript backtrace", "[")) and len(out[-1]["text"]) < 600:
            out[-1]["text"] += " | " + line.strip()
    return out


def _run(cmd: list[str], timeout: int, cwd: Path | None = None) -> tuple[int, str]:
    env = {**os.environ, "DBUS_SESSION_BUS_ADDRESS": "disabled:"}
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env)
    return proc.returncode, proc.stdout + proc.stderr


def import_assets(binary: str, project: Path, timeout: int = 300) -> dict:
    code, log = _run([binary, "--headless", "--path", str(project), "--import"], timeout)
    return {"code": code, "issues": [i for i in parse_log(log) if "Import" in i["text"] or i["level"] == "error"][:30]}


def run(binary: str, project: Path, seconds: float = 5.0, scene: str | None = None, timeout: int = 180) -> dict:
    """Run the game headless for ``seconds`` of game time and collect errors and warnings."""
    if not (project / ".godot").exists():
        import_assets(binary, project)
    frames = max(1, int(seconds * 60))
    cmd = [binary, "--headless", "--fixed-fps", "60", "--path", str(project), "--quit-after", str(frames)]
    if scene:
        cmd.append(scene)
    start = time.monotonic()
    code, log = _run(cmd, timeout)
    issues = parse_log(log)
    return {"exit_code": code, "wall_seconds": round(time.monotonic() - start, 2), "game_seconds": seconds,
            "errors": [i for i in issues if i["level"] == "error"][:40],
            "warnings": [i for i in issues if i["level"] == "warning"][:20],
            "ok": code == 0 and not any(i["level"] == "error" for i in issues), "log_tail": log[-1500:]}


def playtest(binary: str, project: Path, out_dir: Path, seconds: float = 120.0, seed: int = 1, timeout: int = 600,
             screenshots: bool = False) -> dict:
    """Bot-play the game at fixed 60 FPS without real-time sync: minutes of play in seconds. With
    ``screenshots`` it renders for real (on $DISPLAY, or a virtual one through xvfb-run) and saves frames."""
    if not (project / "addons" / "gameforge" / "playtest_runner.tscn").exists():
        addon = project / "addons" / "gameforge"
        addon.mkdir(parents=True, exist_ok=True)
        for f in (TEMPLATE / "addons" / "gameforge").iterdir():
            shutil.copy2(f, addon / f.name)
    if not (project / ".godot").exists():
        import_assets(binary, project)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "godot_bot.json"
    start = time.monotonic()
    cmd = [binary, "--headless", "--fixed-fps", "60", "--path", str(project),
           "res://addons/gameforge/playtest_runner.tscn", "--", f"--duration={seconds}", f"--out={report_path}",
           f"--seed={seed}"]
    if screenshots:
        shots = out_dir / "shots"
        shots.mkdir(exist_ok=True)
        cmd = [c for c in cmd if c != "--headless"] + [f"--shots={shots}", f"--shot-every={max(2.0, seconds / 12)}"]
        cmd[1:1] = ["--rendering-driver", "opengl3", "--audio-driver", "Dummy"]
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            xvfb = shutil.which("xvfb-run")
            if not xvfb:
                raise RuntimeError("screenshots need a display; install xvfb (xvfb-run) or run with DISPLAY set")
            cmd = [xvfb, "-a", "-s", "-screen 0 1280x960x24", *cmd]
    code, log = _run(cmd, timeout)
    issues = parse_log(log)
    if not report_path.exists():
        return {"verdict": "BROKEN", "error": "the bot did not finish (crash or script error before the end)",
                "exit_code": code, "errors": [i for i in issues if i["level"] == "error"][:30], "log_tail": log[-2000:]}
    bot = json.loads(report_path.read_text(encoding="utf-8"))
    events = bot.get("events", [])
    counts: dict[str, int] = {}
    for e in events:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    errors = [i for i in issues if i["level"] == "error"]
    found = []
    for e in errors:
        found.append({"severity": "critical", "title": "Engine/script error", "detail": e["text"][:300]})
    for s in bot.get("stuck", []):
        found.append({"severity": "major", "title": "Player got stuck",
                      "detail": f"no movement for 4s at ({s['x']:.0f}, {s['y']:.0f}) holding {s['holding']}", "t": s["t"]})
    game_times = [0.0] + [e["t"] for e in events if e["type"] not in ("start", "attack")] + [bot["duration_s"]]
    for a, b in zip(game_times, game_times[1:]):
        if b - a >= 20:
            found.append({"severity": "design", "title": "Nothing happens", "detail": f"{a:.0f}s–{b:.0f}s with no game event", "t": a})
    fm = bot.get("frame_ms", {})
    if fm.get("p95", 0) > 16.7:
        found.append({"severity": "major", "title": "Slow frames", "detail": f"p95 process time {fm['p95']:.1f} ms (> 16.7 ms budget)"})
    verdict = ("BROKEN" if any(f["severity"] == "critical" for f in found) else
               "ROUGH" if any(f["severity"] == "major" for f in found) else "PLAYABLE" if found else "SOLID")
    report = {"verdict": verdict, "engine": bot.get("engine"), "game_seconds": bot["duration_s"],
              "wall_seconds": round(time.monotonic() - start, 1), "events": counts, "restarts": bot.get("restarts"),
              "coverage_cells": bot.get("coverage_cells"), "frame_ms": fm, "issues": found,
              "warnings": [i["text"][:200] for i in issues if i["level"] == "warning"][:10]}
    if bot.get("shots"):
        report["screenshots"] = [str(out_dir / "shots" / s["file"]) for s in bot["shots"]]
    (out_dir / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def export(binary: str, project: Path, target: str, debug: bool = False, timeout: int = 900) -> dict:
    if target not in PRESETS:
        raise ValueError(f"unknown Godot export target {target!r}; choose from {', '.join(PRESETS)}")
    ver = version(binary)
    if templates_dir(ver) is None:
        return {"ok": False, "error": f"Godot export templates for {ver} are not installed",
                "fix": "In the editor: Editor > Manage Export Templates > Download and Install. Headless: "
                       "forge_export target=godot_templates downloads the official .tpz for this version "
                       "(about 1 GB) and installs it."}
    if not (project / "export_presets.cfg").exists():
        (project / "export_presets.cfg").write_text(export_presets(), encoding="utf-8")
    # Always re-import: a project scaffolded (or re-scaffolded) after the .godot cache was
    # built has unimported assets, and the export silently ships an empty game without this.
    imported = import_assets(binary, project)
    import_errors = [i for i in imported.get("issues", []) if i["level"] == "error"]
    if imported.get("code") not in (0, None) and import_errors:
        return {"ok": False, "error": "asset import failed before export", "details": imported}
    name, _, rel = PRESETS[target]
    out = project / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    code, log = _run([binary, "--headless", "--path", str(project), "--export-debug" if debug else "--export-release",
                      name, str(out)], timeout)
    issues = parse_log(log)
    return {"ok": code == 0 and out.exists(), "output": out, "exit_code": code,
            "errors": [i for i in issues if i["level"] == "error"][:20], "log_tail": log[-1200:]}


def install_templates(binary: str, timeout: int = 3600) -> dict:
    """Download the official export templates for this exact Godot build from GitHub releases.

    The ``.tpz`` is a zip with one ``templates/`` directory inside; only that leading folder is
    stripped, so the layout Godot expects (``<number>.<status>/linux_release.x86_64`` …) is kept.
    """
    import urllib.error
    import urllib.request
    import zipfile

    number, status = _split_version(version(binary))
    tag = f"{number}-{status}"
    url = f"https://github.com/godotengine/godot-builds/releases/download/{tag}/Godot_v{tag}_export_templates.tpz"
    dest_root = Path(os.path.expanduser("~/.local/share/godot/export_templates")) / f"{number}.{status}"
    dest_root.mkdir(parents=True, exist_ok=True)
    tpz = dest_root.parent / f"{tag}.tpz"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp, open(tpz, "wb") as fh:
            shutil.copyfileobj(resp, fh)
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"no export templates published for {version(binary)} ({exc.code} from {url})",
                "fix": "Open the project in the Godot editor and use Editor > Manage Export Templates > Download, "
                       "or install a release build whose .tpz exists on github.com/godotengine/godot-builds."}
    with zipfile.ZipFile(tpz) as z:
        count = _extract_tpz(z, dest_root)
    tpz.unlink()
    return {"installed": dest_root, "version": tag, "source": url, "ok": True, "files": count}


def _extract_tpz(z, dest_root: Path) -> int:
    """Unpack an export-template zip into ``dest_root``, stripping only a leading ``templates/``."""
    import zipfile

    names = z.namelist()
    prefix = "templates/" if any(n.startswith("templates/") for n in names) else ""
    count = 0
    for member in names:
        if member.endswith("/"):
            continue
        rel = member[len(prefix):] if prefix and member.startswith(prefix) else member
        if not rel or rel.startswith("..") or member.startswith("__MACOSX"):
            continue
        target = dest_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        with z.open(member) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
        count += 1
    return count
