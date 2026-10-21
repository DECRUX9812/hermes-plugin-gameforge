---
name: pixel-art-pipeline
description: Make sprite sheets, tilesets and icons for 2D games.
version: 1.0.0
author: Ritesh Patel (DECRUX9812), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [pixel-art, sprites, tilesets, 2d, gamedev, gameforge]
    category: creative
    related_skills: [gameforge:game-studio]
---

# Pixel Art Pipeline Skill

2D art with `forge_sprite` and `forge_tileset`: procedural characters, monsters, icons and props, plus a
path from any AI image to a clean game sprite. Every output carries engine-ready metadata.

## When to Use

Sprite sheets, animations, tilesets, icons, or turning concept art into pixel sprites.

## Prerequisites

None. For AI art, Hermes' `image_generate` tool must be configured.

## How to Run

- Character: `forge_sprite kind=character archetype=<hero|knight|mage|rogue|villager|princess|healer>`
  → 24 frames (idle 2 + walk 4 per facing), JSON atlas with frame tags, Godot SpriteFrames, GIF.
- Monster: `kind=monster monster=<slime|bat|beast|ghost|golem|spaceship> hue=<colour>`, `size=32` for 2x.
- Icons: `kind=items items=[sword,potion,gem,...] size=16|24|32`. Props: `kind=props props=[tree,pine,...]`.
- Tiles: `forge_tileset lower=water upper=grass` → 16 Wang tiles + fill variants (+ animation strip).
- AI → sprite: `image_generate` a subject on a plain background, then
  `forge_sprite kind=pixelize source=<path> size=32 palette=sweetie16`.
- Your frames → sheet: `kind=sheet frames=[...] animations={"run":[0,1,2,3]}`.

## Quick Reference — engines

| Engine | Use |
|---|---|
| Godot | `<name>_frames.tres` (SpriteFrames), tileset `.tres` (terrain painter) |
| Phaser / Pixi / Defold | `<name>.json` (JSON-hash + `meta.frameTags`) |
| Unity | the GameForge Unity scaffold slices from rects; or slice by grid at the frame size |
| Aseprite | open the PNG, use the frameTags as a guide |

## Pitfalls

- Keep one palette per game (`palette=` on pixelize) so AI-derived sprites match procedural ones.
- Upscale only with nearest-neighbour; previews already do (`preview_scale`).

## Verification

Look at `preview_gif` / `preview` with `vision_analyze` before using an asset.
