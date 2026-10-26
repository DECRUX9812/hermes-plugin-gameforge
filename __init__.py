"""Hermes GameForge — the game-development plugin: assets (SFX, music, voices, sprites, tilesets, 3D),
engines (web, Godot, Unity, Blender, Unreal), a playtester that actually plays, and one-click export."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .gameforge import runtime, schemas
from .gameforge.policy import pre_tool_call
from .gameforge.tools_assets import forge_model3d, forge_music, forge_sfx, forge_sprite, forge_tileset, forge_voice
from .gameforge.tools_engine import forge_engine, forge_export, forge_playtest, status

logger = logging.getLogger(__name__)

TOOLSET = "gameforge"
HANDLERS = {"forge_sfx": forge_sfx, "forge_music": forge_music, "forge_voice": forge_voice, "forge_sprite": forge_sprite,
            "forge_tileset": forge_tileset, "forge_model3d": forge_model3d, "forge_engine": forge_engine,
            "forge_playtest": forge_playtest, "forge_export": forge_export}
EMOJI = {"forge_sfx": "🔊", "forge_music": "🎵", "forge_voice": "🗣️", "forge_sprite": "👾", "forge_tileset": "🧱",
         "forge_model3d": "🧊", "forge_engine": "🎮", "forge_playtest": "🕹️", "forge_export": "📦"}


def register(ctx) -> None:
    runtime.bind(ctx)
    for schema in schemas.ALL:
        name = schema["name"]
        ctx.register_tool(name=name, toolset=TOOLSET, schema=schema, handler=HANDLERS[name],
                          description=schema["description"], emoji=EMOJI[name])
    skills = Path(__file__).parent / "skills"
    for child in sorted(skills.iterdir()):
        if (child / "SKILL.md").exists():
            ctx.register_skill(child.name, child / "SKILL.md")
    ctx.register_command("forge", _slash, description="GameForge: engines, providers and the current project's assets",
                         args_hint="[project dir]")
    ctx.register_cli_command("gameforge", "Hermes GameForge: game dev toolkit", _cli_setup, _cli_run,
                             description="Inspect the toolchain or build the end-to-end demo game.")
    ctx.register_hook("pre_tool_call", pre_tool_call)


def _slash(raw: str) -> str:
    from .gameforge import project as proj
    lines = ["**GameForge**"]
    for engine, info in status().items():
        if engine == "providers":
            lines.append("providers: " + ", ".join(f"{k} {'✓' if v else '—'}" for k, v in info.items()))
        else:
            lines.append(f"{engine}: {info.get('version') or info.get('path') or 'not found'}")
    target = (raw or "").strip() or runtime.config("default_project") or "game"
    p = Path(target).expanduser()
    if (p / proj.LEDGER).exists():
        s = proj.summary(p.resolve())
        lines.append(f"project {s['project']}: {s['total']} assets {s['assets']}")
    return "\n".join(lines)


def _cli_setup(parser) -> None:
    sub = parser.add_subparsers(dest="gameforge_cmd")
    sub.add_parser("status", help="engines, browser and providers GameForge can use")
    demo = sub.add_parser("demo", help="build a complete game: assets, web + Godot builds, playtest, export")
    demo.add_argument("project", nargs="?", default="gameforge-demo")
    demo.add_argument("--theme", default="forest")
    demo.add_argument("--seed", type=int, default=7)
    demo.add_argument("--title", default="Hermes Quest")


def _cli_run(args) -> int:
    if getattr(args, "gameforge_cmd", None) == "demo":
        return _demo(args)
    print(json.dumps(status(), indent=1))
    return 0


def _demo(args) -> int:
    proj_dir = str(Path(args.project).expanduser().resolve())
    steps = [
        ("web game", forge_engine, {"engine": "web", "action": "scaffold", "project": proj_dir, "theme": args.theme,
                                    "seed": args.seed, "title": args.title}),
        ("villager voice", forge_voice, {"project": proj_dir, "engine": "babble",
                                         "cast": {"Elder": {"fx": "elder", "pitch_hz": 150}, "Goblin": {"fx": "goblin", "pitch_hz": 260}},
                                         "lines": [{"character": "Elder", "text": "Collect every coin, young one."},
                                                   {"character": "Goblin", "text": "Shiny coins? Mine! All mine!"}]}),
        ("3D props", forge_model3d, {"project": proj_dir, "kind": "chest", "animations": ["open"], "seed": args.seed}),
        ("godot build", forge_engine, {"engine": "godot", "action": "scaffold", "project": proj_dir, "theme": args.theme,
                                       "seed": args.seed, "title": args.title}),
        ("playtest (web)", forge_playtest, {"project": proj_dir, "target": "web", "duration": 45}),
        ("export", forge_export, {"project": proj_dir, "target": "web"}),
        ("single-file", forge_export, {"project": proj_dir, "target": "single"}),
    ]
    for label, fn, a in steps:
        res = json.loads(fn(a))
        mark = "✓" if res.get("ok") else "✗"
        detail = res.get("error") or res.get("report", {}).get("verdict") or ""
        print(f"{mark} {label} {detail}")
    print(f"\nDone: {proj_dir}  (open web/index.html through any static server, or dist/*.html directly)")
    return 0
