---
name: 3d-asset-pipeline
description: Generate, preview and animate 3D game models as glTF.
version: 1.0.0
author: Ritesh Patel (DECRUX9812), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [3d, gltf, models, animation, gamedev, gameforge]
    category: creative
    related_skills: [gameforge:blender-pipeline]
---

# 3D Asset Pipeline Skill

`forge_model3d` makes .glb models three ways — offline low-poly generators with animation clips, AI
text/image-to-3D through Tripo (with auto-rigging and preset animations), fal.ai or Meshy, or import — and always returns views + a turntable GIF.

## When to Use

Props, environment pieces, simple animated characters, or AI models from a prompt or concept image.

## Prerequisites

None for procedural. AI: `FAL_KEY` or `MESHY_API_KEY` in the GameForge plugin settings (each request is
sent to that provider and billed by them). Blender optional for conversion/LODs.

## How to Run

- Procedural: `kind=<tree|pine|rock|crystal|house|tower|terrain|dungeon|character|chest|coin|potion|sword|
  mushroom|spaceship|cloud|fence|barrel> seed=N`.
- Animated: `kind=character animations=[walk,idle,wave]`; `kind=chest animations=[open]`; any model:
  `spin`, `bob`, `bounce`, `pulse`. Clips are named glTF animations every engine can play.
- Dungeon from a layout: `kind=dungeon layout=["#####","#.C.#","#####"]`.
- AI: `source=tripo prompt="a mossy stone well, low poly"` (needs `TRIPO_API_KEY`), or
  `source=fal` / `source=meshy` with `prompt=` / `image=` (`model=` overrides the endpoint).
- Rigged character in one call: `source=tripo prompt="a brass goblin chieftain" rig=true
  animate=[walk,wave]` — generation → `animations/rig` → `animations/retarget` → `.glb` with clips.
  `animate=` implies `rig=true`; up to five presets (idle, walk, run, jump, slash, shoot, hurt,
  fall, turn, climb, dive, or "preset:quadruped:walk"-style forms).
- No key? `source=procedural kind=character animations=[walk,wave]` gives a rigged, animated,
  engine-ready `.glb` offline, so the rest of the pipeline can be built before spending credits.
- Then: LODs / FBX via `gameforge:blender-pipeline`.

## Pitfalls

- Procedural models use vertex colours, no textures: tint in-engine with a material if needed.
- AI generations take 30 s–5 min; the call waits up to `timeout` seconds.

## Verification

Look at `views` (front, ¾, side, top) with `vision_analyze`; `triangles` stays within your budget.
