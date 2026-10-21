---
name: game-studio
description: Take a game idea from pitch to a playtested build.
version: 1.0.0
author: Ritesh Patel (DECRUX9812), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [gamedev, game-design, workflow, gameforge]
    category: creative
    related_skills: [gameforge:playtesting, gameforge:ship-it, gameforge:godot-dev, gameforge:game-audio]
---

# Game Studio Skill

The director's workflow for GameForge: turn "make me a game about X" into a playable, playtested,
shareable build, using the `forge_*` tools for every asset and the playtester as the quality gate.
It does not replace engine-specific depth: load `gameforge:godot-dev` or `gameforge:unity-dev` for that.

## When to Use

- The user wants a game (or a prototype, jam entry, level, vertical slice) built end to end.
- The user hands you an existing GameForge project and asks to make it better or more fun.

## Prerequisites

- GameForge enabled (`hermes plugins enable gameforge`) with the `gameforge` toolset on.
- Nothing else for the web path. Optional: Godot 4, Unity, Blender (see `forge_engine action=status`).

## How to Run

1. `forge_engine engine=web action=status` — learn what this machine has (engines, browser, providers).
2. Pin the design in 6 lines before touching tools: genre, core verb, win/lose, session length, mood,
   art direction (palette + theme). Write it to `<project>/DESIGN.md` with `write_file`.
3. Scaffold: `forge_engine engine=web action=scaffold theme=<forest|winter|desert|volcano|dungeon> hero=<archetype>`.
   This generates every asset (sprites, tiles, SFX pools, music loop) and a playable build in `web/`.
4. Customise through data first: `web/game.json` (map rows, speeds, HP, attack radius). Regenerate any
   single asset with its tool and the same `name` (the ledger keeps recipes), then re-run the scaffold.
5. Gate on the playtester: `forge_playtest target=web duration=90`. Fix every critical/major issue, then
   reconsider each design issue. Re-test until the verdict is SOLID or PLAYABLE with reasons you accept.
6. Second engine when wanted: `forge_engine engine=godot action=scaffold` reuses the same assets and level;
   `forge_playtest target=godot duration=300` bot-plays 5 minutes in seconds.
7. Ship: load `gameforge:ship-it`.

## Quick Reference

| Need | Call |
|---|---|
| Hero / NPC sprite | `forge_sprite kind=character archetype=knight` |
| Enemy | `forge_sprite kind=monster monster=bat hue=purple` |
| Icons | `forge_sprite kind=items items=[coin,heart,key]` |
| Terrain | `forge_tileset lower=water upper=grass` |
| SFX pool | `forge_sfx preset=coin variations=4` |
| Music loop | `forge_music mood=boss style=synthwave bars=16` |
| Dialogue | `forge_voice cast={...} lines=[...]` |
| 3D prop | `forge_model3d kind=chest animations=[open]` |
| Map map map | edit `web/game.json` `map` rows |

## Procedure — making it fun

- **First 10 seconds**: something must happen. The playtester's `time_to_first_event_s` should be < 5.
- **Event density**: "Nothing happens" issues mean dead zones — add coins/enemies to those map areas.
- **Difficulty**: more than 2 deaths/minute for the explorer bot = too hard; a no-damage win = too easy.
  Tune `enemy.speed`, `enemy.chase_radius`, `player.hp`, `player.attack_radius` in `game.json`.
- **Juice**: every player action needs feedback — a sound from a variation pool plus particles.
- **Audio identity**: one music mood per area; SFX style `retro` for chiptune, `modern` for synthwave.

## Pitfalls

- Don't hand-write pixel art or synth code inline — the tools are seeded and recorded; inline work is lost.
- Don't call the job done on "it runs". Done means a playtest report without critical/major issues.
- Keep the map rectangular (all rows equal length) and ensure exactly one `@` and one `X`.

## Verification

- `forge_playtest` report verdict and its `moments.jpg` screenshots look right (send them to the user).
- `gameforge.json` lists every asset with a recipe; `/forge <project>` summarises it.
