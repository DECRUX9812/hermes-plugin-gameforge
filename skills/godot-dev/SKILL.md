---
name: godot-dev
description: Build, debug and export Godot 4 games headlessly.
version: 1.0.0
author: Ritesh Patel (DECRUX9812), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [godot, gdscript, gamedev, gameforge]
    category: creative
    related_skills: [gameforge:game-studio, gameforge:playtesting, gameforge:ship-it]
---

# Godot Dev Skill

Work on Godot 4 projects without opening the editor: scaffold from GameForge assets, write GDScript,
import, run headless and read the parsed errors, bot-playtest, export.

## When to Use

The user wants a Godot game, or has a Godot project to fix or extend.

## Prerequisites

Godot 4.x (auto-detected, or `godot_path` in GameForge settings). Exports need the matching export
templates: `forge_export target=godot_templates` installs them (about 1 GB download).

## How to Run

- New: `forge_engine engine=godot action=scaffold theme=forest` — the game project root becomes the Godot
  project; `main.gd` builds the level from `level.json` at runtime; a smoke run is included.
- Iterate: edit `.gd` with `patch`, then `forge_engine engine=godot action=run seconds=10`. `errors` holds
  every `SCRIPT ERROR`/`ERROR` with its `at:` location; `ok` is false while any remain.
- Re-import after adding assets: `action=import`.
- Play: `forge_playtest target=godot duration=300 screenshots=true`.
- Ship: `forge_export target=godot:web` (or linux, windows, macos, android).

## Quick Reference

- GameForge sprites ship a `<name>_frames.tres` SpriteFrames: `AnimatedSprite2D.sprite_frames = load(...)`,
  animations `idle_<dir>` / `walk_<dir>`.
- Tilesets ship a `.tres` with a Match Corners terrain set: TileMapLayer → Terrains → paint.
- Telemetry contract for the bot: root node `gf_state() -> Dictionary` (scene, x, y, score...) and `events: Array`.

## Pitfalls

- GDScript `:=` cannot infer from Dictionary/Array element reads — annotate (`var ok: bool = d["k"] == 0`).
- Headless runs use `--fixed-fps 60`: timers advance in game time, so 5 minutes of play takes seconds.
- "resources still in use at exit" lines are shutdown noise and are reported as warnings.
- `web/`, `playtests/`, `dist/` carry `.gdignore` so Godot does not import build output.

## Verification

`action=run` returns `ok: true` with no errors, and a Godot playtest verdict without criticals.
