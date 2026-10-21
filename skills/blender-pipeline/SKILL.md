---
name: blender-pipeline
description: Convert, LOD, render and animate models in headless Blender.
version: 1.0.0
author: Ritesh Patel (DECRUX9812), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [blender, 3d, pipeline, gameforge]
    category: creative
    related_skills: [gameforge:3d-asset-pipeline]
---

# Blender Pipeline Skill

Unattended Blender through `forge_engine engine=blender`: no add-on, no open window. For live editing of
an open scene use the catalog's Blender MCP plugin instead; this is the batch path.

## When to Use

Format conversion (glb/gltf/fbx/obj/stl/ply/blend), LOD chains, turntable renders, simple procedural
animation, scene inspection, or any custom bpy job.

## Prerequisites

Blender 4.2+ (auto-detected, or `blender_path`). A portable Blender tarball works.

## How to Run

| Job | Call |
|---|---|
| Inspect | `action=info input=assets/models/house.glb` |
| Convert | `action=convert input=a.glb output=a.fbx` |
| LODs | `action=lod input=a.glb output=assets/models/a.glb ratios=[1,0.5,0.25]` |
| Turntable | `action=turntable input=a.glb output=renders/a frames=36 size=512` (Eevee, transparent PNGs) |
| Animate | `action=animate input=a.glb output=a_spin.glb preset=spin|bob|pulse duration=1` |
| Custom | write a bpy script with `write_file`, then `action=script script=path args={...}` |

## Procedure — custom scripts

Read arguments with `json.loads(sys.argv[sys.argv.index("--") + 1])`. Print one line
`GAMEFORGE_RESULT {json}` at the end; the tool returns it as `result`. Exit non-zero on failure.

## Pitfalls

- Paths in calls are relative to the project; outputs land where you point them.
- Each LOD level decimates the original mesh (not the previous level).
- `turntable` frames → GIF/MP4: use `terminal` with ffmpeg if the user wants a video.

## Verification

`ok: true`, `result` populated, and the output files exist (check with `search_files target='files'`).
