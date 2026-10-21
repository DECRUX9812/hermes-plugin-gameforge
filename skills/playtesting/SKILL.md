---
name: playtesting
description: Playtest builds and turn reports into fixes.
version: 1.0.0
author: Ritesh Patel (DECRUX9812), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [gamedev, qa, playtest, gameforge]
    category: creative
    related_skills: [gameforge:game-studio]
---

# Playtesting Skill

`forge_playtest` plays the build (headless Chrome for web builds, a bot for Godot) and reports where it
breaks or gets boring. This skill covers choosing a policy, reading the report and fixing what it finds.

## When to Use

After any gameplay change, before any export, and whenever the user asks "is it fun / does it work".

## Prerequisites

Chrome, Chromium or Edge for web builds (auto-detected; set `browser_path` otherwise). Godot 4 for
`target=godot`; `screenshots=true` there needs a display or `xvfb-run`.

## How to Run

- Smoke + design pass: `forge_playtest target=web duration=90` (policy `explorer`).
- Crash hunting: `policy=monkey duration=120`.
- Human-like notes: `policy=agent goal="find the chest"` — your vision model plays and comments. Costs tokens.
- Long-session balance: `forge_playtest target=godot duration=600` (10 minutes of game time in ~15 s).
- Any web game, not just GameForge's: pass a URL or a build directory as `target`.

## Quick Reference — signals

| Issue | Meaning | Usual fix |
|---|---|---|
| Runtime error (critical) | uncaught exception / console error | fix the line in the stack trace |
| Player got stuck (major) | position frozen while moving | collision gap, spawn inside a wall, map hole |
| Input had no visible effect | screen frozen under input (no telemetry games) | focus/start-screen bug, crash |
| Frame-rate drops / slow frames | p5 FPS < 30, Godot p95 > 16.7 ms | too many particles/props, per-frame allocations |
| Nothing happens | ≥ 20 s without a game event | dead zone; add pickups/enemies/landmarks |
| Low-novelty stretch | the screen kept repeating | scenery variety, new areas, pacing |
| Too hard / too easy | deaths per minute / damage-free wins | tune `game.json` |

## Procedure

1. Run, then read `report.md` with `read_file` and look at `moments.jpg` with `vision_analyze`.
2. Fix criticals first, then majors; re-run with the **same seed** to confirm the fix.
3. Change one tuning value at a time for design issues and compare reports.
4. Telemetry makes reports richer: a custom game can publish `window.__gameforge = {controls, state, events}`
   (see the GameForge web template's `game.js`).

## Pitfalls

- One run is a sample. For balance decisions run 3 seeds and compare.
- The explorer is not a good player; "too hard" from it means "hard for a newcomer", which is useful.

## Verification

The re-run report no longer lists the issue, and the verdict improved or held.
