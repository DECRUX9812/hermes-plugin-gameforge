---
name: unity-dev
description: Scaffold and batch-build Unity games from GameForge.
version: 1.0.0
author: Ritesh Patel (DECRUX9812), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [unity, csharp, gamedev, gameforge]
    category: creative
    related_skills: [gameforge:game-studio, gameforge:ship-it]
---

# Unity Dev Skill

Create a Unity project from GameForge assets and drive Unity in batch mode: scene setup, builds, and
compiler/build error triage from the log. Live editor automation is out of scope.

## When to Use

The user targets Unity, or wants the GameForge game ported to Unity.

## Prerequisites

A Unity editor (Unity Hub install; auto-detected or `unity_path`). WebGL/Android builds need those
modules installed through Unity Hub. A Unity license must be activated on the machine.

## How to Run

1. `forge_engine engine=unity action=scaffold` — writes `unity/` with `Assets/Scripts/GameForgeTopDown.cs`
   (runtime level builder), editor scripts, and `Assets/Resources/GameForge/` (assets + `level.json`).
2. `forge_engine engine=unity action=setup` — batch-mode creates `Assets/Scenes/Main.unity` and build settings.
3. `forge_export target=unity:webgl` (or android, windows, linux, macos) → `dist/unity-<target>/`.
4. Test the WebGL build: `forge_playtest target=<project>/dist/unity-webgl` (pixel-only signals).

## Quick Reference

- Errors: results list `error CS####` lines; open the file:line with `read_file`, fix with `patch`, re-run setup.
- Textures under `/GameForge/` import as point-filtered, uncompressed, non-power-of-two (GameForgeImport.cs).
- Sprites are sliced at runtime from the atlas rects in `level.json`, so no import slicing step exists.

## Pitfalls

- First batch-mode open of a new project takes minutes (Library import). Don't kill it early.
- Unity 6 projects created in the Hub may default to the new Input System only: set Active Input Handling
  to "Both" (the template reads legacy axes).

## Verification

Setup log contains `GAMEFORGE_SETUP_DONE`; builds return `ok: true` and log `GAMEFORGE_BUILD Succeeded`.
