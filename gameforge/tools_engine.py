"""Engine, playtest and export tool handlers."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .secrets import get_secret
from . import project as proj
from .engines import blender, godot, unity, unreal, web
from .export import web_export
from .playtest import cdp
from .playtest.web_runner import WebPlaytester
from .runtime import config, fail, handler, llm, ok


def _project(args: dict) -> Path:
    return proj.resolve_project(args.get("project"), config("default_project"))


def _bin(engine: str) -> str | None:
    explicit = config(f"{engine}_path")
    return {"godot": godot.locate, "unity": unity.locate, "blender": blender.locate,
            "unreal": unreal.locate}[engine](explicit)


def status() -> dict:
    """What this machine can do right now."""
    out: dict = {}
    g = _bin("godot")
    out["godot"] = {"path": g, "version": godot.version(g) if g else None,
                    "export_templates": bool(g and godot.templates_dir(godot.version(g)))}
    for e in ("unity", "blender", "unreal"):
        out[e] = {"path": _bin(e)}
    out["browser"] = {"path": cdp.find_browser(config("browser_path"))}
    out["web"] = {"path": "built in"}
    from .audio import voice
    from .three import ai3d
    out["providers"] = {**ai3d.available(), "elevenlabs": bool(get_secret("ELEVENLABS_API_KEY")),
                        "edge_tts": voice.edge_available()}
    return out


def _missing(engine: str) -> str:
    return fail(f"{engine} not found. Install it or set plugins.entries.gameforge.settings.{engine}_path "
                "(GameForge plugin settings). forge_engine action=status shows what was detected.")


@handler
def forge_engine(args: dict) -> str:
    engine, action = args.get("engine", "web"), args.get("action", "status")
    if action == "status":
        return ok(engines=status())
    p = _project(args)
    title = args.get("title") or "Hermes Quest"
    theme, seed, hero = args.get("theme", "forest"), int(args.get("seed", 7)), args.get("hero", "hero")
    if engine == "web":
        if action != "scaffold":
            return fail("engine 'web' supports action 'scaffold' (play/test it with forge_playtest, ship with forge_export)")
        genre = args.get("genre") or "topdown"
        res = web.scaffold(p, title, theme, seed, hero, args.get("subtitle", ""), bool(args.get("regenerate")),
                           genre=genre)
        return ok(**res)
    if engine == "godot":
        b = _bin("godot")
        if action == "scaffold":
            res = godot.scaffold(p, title, theme, seed, hero)
            if b:
                res["import"] = godot.import_assets(b, p)
                res["smoke_run"] = {k: v for k, v in godot.run(b, p, 3).items() if k != "log_tail"}
            else:
                res["note"] = "Godot not found: project written but not imported or test-run"
            return ok(**res)
        if not b:
            return _missing("godot")
        if action == "import":
            return ok(**godot.import_assets(b, p))
        if action == "run":
            return ok(**godot.run(b, p, float(args.get("seconds", 5)), args.get("scene")))
        return fail("godot actions: scaffold, import, run (export via forge_export target=godot:<platform>)")
    if engine == "unity":
        if action == "scaffold":
            return ok(**unity.scaffold(p, title, theme, seed, hero))
        b = _bin("unity")
        if not b:
            return _missing("unity")
        if action == "setup":
            return ok(**unity.setup(b, p))
        return fail("unity actions: scaffold, setup (export via forge_export target=unity:<platform>)")
    if engine == "blender":
        b = _bin("blender")
        if not b:
            return _missing("blender")
        op_args = {k: (str(_resolve(p, v)) if k in ("input", "output", "script") else v)
                   for k, v in args.items() if k in ("input", "output", "ratios", "frames", "size", "preset", "duration",
                                                    "script", "args")}
        res = blender.run(b, action, op_args)
        return ok(**res) if res["ok"] else fail("Blender reported a failure", **res)
    if engine == "unreal":
        uproject = args.get("uproject")
        script = unreal.import_script(p)
        b = _bin("unreal")
        if action == "import" and b and uproject:
            return ok(script=script, **unreal.run_import(b, Path(os.path.expanduser(uproject)), script))
        return ok(script=script, hint="Run it in the Unreal editor (Tools > Execute Python Script), or pass uproject + "
                  "an UnrealEditor-Cmd install for a headless import. For live editor control load the unreal-mcp skill.")
    return fail("engine must be web, godot, unity, blender or unreal")


def _resolve(p: Path, v: str) -> Path:
    path = Path(os.path.expanduser(v))
    return path if path.is_absolute() else p / path


@handler
def forge_playtest(args: dict) -> str:
    p = _project(args)
    target = args.get("target", "web")
    duration = float(args.get("duration", 60))
    stamp = proj._now().replace(":", "").replace("-", "")
    out = proj.asset_dir(p, "playtest") / f"{target.split(':')[0]}_{stamp}"
    if target == "godot":
        b = _bin("godot")
        if not b:
            return _missing("godot")
        rep = godot.playtest(b, p, out, duration, int(args.get("seed", 1)), screenshots=bool(args.get("screenshots")))
        return ok(report=rep, report_file=out / "report.json", media=(rep.get("screenshots") or [])[:2])
    if target == "web" or target.startswith(("http://", "https://")) or _resolve(p, target).exists() \
            or Path(os.path.expanduser(target)).exists():
        tgt = p / "web" if target == "web" else target
        if target != "web" and not target.startswith("http"):
            # Resolve against the project first: a relative target is relative to the game,
            # not to whatever directory the Hermes process happens to run in.
            tgt = _resolve(p, target)
        policy = args.get("policy", "explorer")
        model = llm() if policy == "agent" else None
        if policy == "agent" and model is None:
            return fail("policy 'agent' needs Hermes' LLM access (run inside Hermes); use 'explorer' otherwise")
        rep = WebPlaytester(tgt, out, duration, policy, int(args.get("seed", 1)), config("browser_path"), model,
                            args.get("goal", "")).run()
        summary = {k: rep[k] for k in ("verdict", "duration_s", "fps", "events", "deaths", "wins", "coverage_cells",
                                      "time_to_first_event_s", "issues", "agent_notes", "notes")}
        return ok(report=summary, html=out / "report.html", markdown=out / "report.md",
                  media=[out / "moments.jpg", out / "timeline.png"])
    return fail("target must be 'web', 'godot', a URL, or a path to a web build directory")


@handler
def forge_export(args: dict) -> str:
    p = _project(args)
    target = args.get("target", "web")
    title = proj.load(p).get("name") or "game"
    cfg_file = p / "web" / "game.json"
    if cfg_file.exists():
        title = json.loads(cfg_file.read_text()).get("title", title)
    if args.get("source"):
        web_dir = Path(os.path.expanduser(args["source"])).resolve()
        root = p.resolve()
        if web_dir != root and root not in web_dir.parents:
            return fail(f"source {web_dir} is outside the project directory {root}; "
                        "export only what this project built")
    else:
        web_dir = p / "web"
    dist = proj.asset_dir(p, "export")
    icon = next((p / f for f in (proj.find(p, "sprite", "player") or {}).get("files", []) if f.endswith("player.png")), None)
    name = web_export.slug(title)
    if target == "web":
        b = web_export.bundle(web_dir, dist / "web", title, icon)
        z = web_export.zip_dir(dist / "web", dist / f"{name}-web.zip")
        return ok(bundle=b, zip=z, hint="Phones: open the hosted bundle and 'Add to Home Screen' — it installs and "
                  "plays offline. Upload the zip to itch.io as an HTML game.")
    if target == "single":
        return ok(**web_export.single_file(web_dir, dist / f"{name}.html"))
    if target == "capacitor":
        b = web_export.bundle(web_dir, dist / "web", title, icon)
        return ok(**web_export.capacitor(Path(b["dir"]), dist / "mobile", title,
                                         args.get("app_id") or f"com.gameforge.{name.replace('-', '')}"))
    if target == "itch":
        if not args.get("itch_target"):
            return fail("target 'itch' publishes publicly; pass itch_target 'user/game:html5' to confirm")
        b = web_export.bundle(web_dir, dist / "web", title, icon)
        return ok(**web_export.itch_push(Path(b["dir"]), args["itch_target"], args.get("version")))
    if target == "godot_templates":
        b = _bin("godot")
        return ok(**godot.install_templates(b)) if b else _missing("godot")
    if target.startswith("godot:"):
        b = _bin("godot")
        if not b:
            return _missing("godot")
        res = godot.export(b, p, target.split(":", 1)[1], bool(args.get("debug")))
        return ok(**res) if res.get("ok") else fail(res.get("error") or "Godot export failed", **res)
    if target.startswith("unity:"):
        b = _bin("unity")
        if not b:
            return _missing("unity")
        res = unity.build(b, p, target.split(":", 1)[1])
        return ok(**res) if res["ok"] else fail("Unity build failed", **res)
    return fail("target: web, single, capacitor, itch, godot:<web|linux|windows|macos|android>, "
                "unity:<webgl|android|windows|linux|macos>, godot_templates")
