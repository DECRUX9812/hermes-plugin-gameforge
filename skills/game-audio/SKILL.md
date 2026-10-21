---
name: game-audio
description: Design game sound effects, music loops and NPC voices.
version: 1.0.0
author: Ritesh Patel (DECRUX9812), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [audio, sfx, music, voice, gamedev, gameforge]
    category: creative
    related_skills: [gameforge:game-studio]
---

# Game Audio Skill

Sound design with `forge_sfx`, `forge_music` and `forge_voice`: all offline by default, deterministic
per seed, recorded in the ledger. Provider engines (ElevenLabs, Edge, your Hermes TTS) are opt-in.

## When to Use

Any request for sound effects, background music, jingles, stingers, adaptive stems or character voices.

## Prerequisites

None for synth/compose/babble. ffmpeg enables FX on TTS voices and MP3 compression in exports.

## How to Run

- SFX: pick the preset nearest the action, then `variations=3-5` so repeats never sound identical.
  Tweak with sfxr `params` (`base_freq` pitch, `freq_ramp` slide, `env_decay` length, `wave_type`).
- Music: `forge_music mood=<heroic|happy|adventure|sad|mysterious|tense|boss|chill|spooky|victory>
  style=<chiptune|synthwave|ambient|orchestral> bars=16`. Loops are seamless. `stems=true` for layering.
- Voices: define the cast once, then send lines. `babble` gives every character a recognisable
  pitched-blip voice with no TTS; `fx` (goblin, giant, robot, ghost, radio, demon, fairy, elder, cave)
  works on any engine.

## Quick Reference — action → preset

| Action | Preset / style |
|---|---|
| Pickup, score | `coin` retro |
| Jump | `jump` |
| Shoot | `laser` |
| Hit / damage | `hit` crunchy |
| Enemy death | `explosion` crunchy |
| Melee | `whoosh` + `thud` |
| Level up | `powerup` modern |
| Heal, magic | `heal`, `magic` |
| UI | `click`, `blip` |
| Footsteps | `footstep` variations=4 |

## Pitfalls

- Mix: music around −16 dB RMS sits under SFX; keep music volume ≈ 0.35 in `game.json`.
- One mood per area; switching mid-loop breaks the seamless loop.

## Verification

Results report durations; `share` attaches the first file so the user can listen.
