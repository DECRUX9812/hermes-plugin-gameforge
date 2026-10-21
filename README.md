# Hermes GameForge

**The game-development plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent).**
Ask for a game and get one: sound effects, music, NPC voices, sprite sheets, tilesets and 3D models
generated into a real project; playable web, Godot and Unity builds; Blender and Unreal pipelines; a
playtester that **actually plays the build** and tells you where it breaks or gets boring; one-click
export to the web, phones and itch.io.

Everything runs offline by default (pure Python + Pillow, which Hermes already ships). AI providers
(fal.ai, Meshy, ElevenLabs, Edge TTS, your Hermes TTS) are opt-in upgrades, never requirements.
Nothing touches Hermes core: it is a standard `plugin.yaml` + `register(ctx)` plugin.

```
hermes plugins install DECRUX9812/hermes-plugin-gameforge --enable
hermes gameforge demo            # builds, playtests and exports a complete game in ~1 minute
```

## What's in the box

| Tool | Does | Offline |
|---|---|---|
| `forge_sfx` | 22 presets (sfxr-compatible synth + layered footsteps, whooshes, magic, impacts), tweakable params, variation pools, 4 styles · ElevenLabs prompts | ✓ |
| `forge_music` | mood → mode, chord progression, motif-based melody, bass, arp, drums → **seamless loop WAV + MIDI** (+ stems) in chiptune / synthwave / ambient / orchestral | ✓ |
| `forge_voice` | NPC casts: Animalese-style **babble**, Edge neural TTS or your Hermes TTS, with character FX (goblin, giant, robot, ghost, radio, demon, fairy, elder, cave) and typewriter timings | ✓ |
| `forge_sprite` | 16×16 RPG characters with 4-direction walk/idle, monsters, scalable item icons, props, **AI image → pixel sprite**, sheet packing → PNG + TexturePacker/Phaser JSON + Godot SpriteFrames + GIF | ✓ |
| `forge_tileset` | seamless Wang-corner transitions between 12 terrains (animated water/lava), fill variants, **Godot TileSet with terrains + collision** | ✓ |
| `forge_model3d` | 18 low-poly generators (trees, houses, terrain, dungeons from ASCII, rigged blocky characters…), animation clips (walk, wave, open, spin…) → **.glb** + turntable · fal.ai / Meshy text- and image-to-3D | ✓ |
| `forge_engine` | **web**: complete HTML5 game from your assets across 4 genres (`topdown`, `platformer`, `arena`, `roguelike`) · **Godot 4**: scaffold, import, headless run with parsed errors · **Unity**: scaffold + batch-mode setup · **Blender**: convert, LODs, Eevee turntables, animation, custom bpy · **Unreal**: asset import | ✓ |
| `forge_playtest` | plays the build in headless Chrome (explorer / monkey / **vision-LLM agent**) or bot-plays Godot at 40× real time → crashes, stuck spots, FPS, event droughts, boredom, deaths/wins, heatmap, HTML report | ✓ |
| `forge_export` | PWA bundle (installable on phones, offline), itch.io zip, **single-file HTML**, Capacitor Android/iOS wrapper, butler push, Godot and Unity platform builds | ✓ |

Ten bundled skills teach the agent the workflows: `gameforge:game-studio` (idea → shipped),
`playtesting`, `godot-dev`, `unity-dev`, `blender-pipeline`, `game-audio`, `pixel-art-pipeline`,
`3d-asset-pipeline`, `ship-it` and `game-reverse-engineering` (Ghidra headless export, ILSpy, GDRE).

## The playtester

The headline feature. `forge_playtest target=web` launches headless Chrome (a dependency-free CDP
client, no Playwright), waits for the game, and plays it:

- **explorer** walks toward ground it hasn't seen, remembers dead ends, fights when it can and
  restarts after game over; **monkey** mashes inputs to shake out crashes; **agent** lets your vision
  model look at the screen every few seconds, choose inputs and write tester notes.
- It records uncaught exceptions and console errors (with screenshots), FPS, input that changes
  nothing, getting stuck, **event droughts** (20 s+ with no pickup, fight or progress), low-novelty
  stretches, deaths per minute, damage-free wins, time to first event, and map coverage.
- Output: `report.html` / `report.md` / `report.json`, a timeline chart, a movement heatmap and a
  contact sheet of key moments. Verdict: SOLID, PLAYABLE, ROUGH or BROKEN.

Any web game works; games that publish `window.__gameforge = {controls, state, events}` (like the
GameForge template) get richer signals. For Godot, a bot scene drives the input map with
`--fixed-fps 60`, so **10 minutes of play run in about 15 seconds**, and it can render real frames
through Xvfb.

## One design, every engine

`forge_engine engine=web action=scaffold` generates every asset and writes `web/game.json`: the
level map, tuning and asset paths. The Godot scaffold (`main.gd`) and the Unity scaffold
(`GameForgeTopDown.cs`) read the **same level** and build it at runtime, so a design tweak in one
file reaches all three builds. The project root doubles as the Godot project, so every
`res://assets/...` path in generated `.tres` files just works.

## Asset ledger

Every tool records what it made in `<project>/gameforge.json`: files, the exact recipe (tool,
preset, seed, parameters) and licence. Any asset can be regenerated, varied or credited later.
Procedural output is CC0. AI-provider output follows that provider's terms.

## Settings

Hermes Desktop → Settings → Plugins → GameForge, or `plugins.entries.gameforge.settings` in `config.yaml`:
`default_project`, `godot_path`, `unity_path`, `blender_path`, `unreal_path`, `browser_path`, and the
optional secrets `FAL_KEY`, `MESHY_API_KEY`, `ELEVENLABS_API_KEY` (stored in `.env`).

## Disclosure

- **Network:** none by default. Opt-in calls: fal.ai / Meshy (3D generation; prompt and image are
  sent), ElevenLabs (SFX prompt), Edge TTS (dialogue text, when `edge-tts` is installed), GitHub
  (Godot export templates, only on `forge_export target=godot_templates`, about 1 GB), itch.io via
  butler (only on `target=itch` with an explicit `itch_target`).
- **Processes:** runs Chrome/Chromium headless for playtests, and Godot, Unity, Blender,
  UnrealEditor-Cmd, ffmpeg, xvfb-run or butler when a call asks for them. `forge_engine engine=blender
  action=script` runs a bpy script you point it at.
- **Files:** writes only inside the game project directory, plus a throwaway browser profile in the
  system temp dir. Export templates go to Godot's standard templates folder.
- **No telemetry.** No credentials read beyond the three optional keys above.

## Development

```
python -m pytest -c tests/pytest.ini tests     # 59 tests; browser/Godot ones skip when absent
hermes plugins doctor . && hermes plugins validate .
```

MIT licence.
