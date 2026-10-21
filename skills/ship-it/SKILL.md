---
name: ship-it
description: Export games to the web, phones, itch.io and desktop.
version: 1.0.0
author: Ritesh Patel (DECRUX9812), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [export, web, mobile, itch, release, gameforge]
    category: creative
    related_skills: [gameforge:playtesting]
---

# Ship It Skill

`forge_export` turns a tested build into something people can play: a PWA bundle, an itch.io zip, a
single HTML file, a native mobile wrapper, or Godot/Unity platform builds.

## When to Use

The user wants to share, publish, or put the game on a phone. Playtest first (`gameforge:playtesting`).

## Prerequisites

Nothing for web, single and capacitor. Native mobile builds: Node + Android Studio (Android) or Xcode
(iOS). itch.io: `butler` logged in. Godot: export templates. Unity: the platform module.

## How to Run

| Goal | Call | Result |
|---|---|---|
| Share a link-free file | `target=single` | `dist/<game>.html`, plays offline anywhere |
| Web + phones | `target=web` | `dist/web/` PWA (Add to Home Screen) + `dist/<game>-web.zip` |
| itch.io (manual) | `target=web` then upload the zip as HTML | |
| itch.io (push) | `target=itch itch_target=user/game:html5` | **publishes publicly — confirm first** |
| Android/iOS app | `target=capacitor` then the printed `npm` steps | |
| Godot builds | `target=godot:web|linux|windows|macos|android` | `dist/godot-<platform>/` |
| Unity builds | `target=unity:webgl|android|windows|linux|macos` | `dist/unity-<target>/` |

## Pitfalls

- PWAs only install from https (or localhost). Host `dist/web` on itch.io, GitHub Pages or Netlify.
- Never push to itch.io without the user's explicit go-ahead: it is public.
- The single HTML compresses music to MP3 when ffmpeg is present; otherwise it stays WAV (larger).

## Verification

Run `forge_playtest target=<project>/dist/web` on the exported bundle before announcing it.
