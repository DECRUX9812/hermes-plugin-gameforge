---
name: game-reverse-engineering
description: Decompile and analyze game binaries you have rights to.
version: 1.0.0
author: Ritesh Patel (DECRUX9812), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [reverse-engineering, decompilation, ghidra, modding, gamedev]
    category: creative
    related_skills: []
---

# Game Reverse Engineering Skill

Decompilation workflows for modding, preservation, interoperability and decomp projects: Ghidra headless
export of decompiled C, managed-code (Unity/.NET) decompilation, and engine pack inspection. Only for
binaries the user owns or has the right to analyze; never for cheats in online games or DRM removal.

## When to Use

Matching-decomp projects, modding a single-player game, recovering your own lost source, or
understanding a file format for a fan tool.

## Prerequisites

- Native code: Ghidra 11+ (`analyzeHeadless` in `<ghidra>/support/`) and a JDK.
- Unity Mono games: `ilspycmd` (`dotnet tool install -g ilspycmd`). IL2CPP games: Il2CppDumper first.
- Godot games: `gdsdecomp` (GDRE Tools) for .pck recovery.

## How to Run

1. Identify the target with `terminal`: `file <binary>`; Unity if `*_Data/Managed/Assembly-CSharp.dll`
   exists, IL2CPP if `GameAssembly.dll`/`libil2cpp.so`, Godot if a `.pck` sits beside the executable.
2. Native: `python scripts/ghidra_export.py --ghidra <ghidra dir> --binary <file> --out decomp/` runs a
   headless import + analysis and writes one `.c` file per function plus `functions.json` (name, address,
   size, callers). Start from `main`/entry points and strings of interest via `search_files`.
3. Unity Mono: `ilspycmd -p -o decomp/ <Managed>/Assembly-CSharp.dll` → a buildable C# project.
4. Godot: `gdre_tools --headless --recover=<game.pck> --output-dir=decomp/`.
5. Record findings in `decomp/NOTES.md`: symbol names you assign, structs, file formats.

## Pitfalls

- Respect licenses and EULAs; keep extracted assets out of public repos.
- Matching decomps need the original compiler; Ghidra output is a reading aid, not compilable source.
- Big binaries take Ghidra many minutes; run with a generous `terminal` timeout or in the background.

## Verification

`functions.json` lists the expected entry points; spot-check a few `.c` files against the disassembly.
