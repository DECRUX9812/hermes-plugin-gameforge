"""Tool schemas. Kept tight: every schema rides on every API call while the toolset is enabled."""

from .audio import music, sfx, voice
from .engines import web
from .gfx import sprites, tiles
from .three import procgen

_PROJECT = {"type": "string", "description": "Game project directory (created if missing). Default: ./game"}
_SEED = {"type": "integer", "description": "Seed; same seed + params = same asset"}
_NAME = {"type": "string", "description": "Asset name (file stem + ledger key)"}

FORGE_SFX = {
    "name": "forge_sfx",
    "description": "Generate game sound effects into the project (WAV). Offline sfxr-style synth with presets, "
                   "tweakable params and variation pools; or engine='elevenlabs' for a text prompt.",
    "parameters": {"type": "object", "properties": {
        "project": _PROJECT, "name": _NAME, "seed": _SEED,
        "preset": {"type": "string", "enum": sfx.PRESETS},
        "variations": {"type": "integer", "description": "1-8 variants for random playback"},
        "style": {"type": "string", "enum": ["retro", "modern", "crunchy", "distant"]},
        "params": {"type": "object", "description": "sfxr parameter overrides (base_freq, freq_ramp, env_decay, wave_type...)"},
        "engine": {"type": "string", "enum": ["synth", "elevenlabs"]},
        "prompt": {"type": "string", "description": "elevenlabs: describe the sound"},
        "duration": {"type": "number"}}},
}

FORGE_MUSIC = {
    "name": "forge_music",
    "description": "Compose game music offline: seamless loop WAV + multi-track MIDI (+ optional stems), from mood, key, "
                   "tempo and style.",
    "parameters": {"type": "object", "properties": {
        "project": _PROJECT, "name": _NAME, "seed": _SEED,
        "mood": {"type": "string", "enum": list(music.MOODS)},
        "style": {"type": "string", "enum": list(music.STYLES)},
        "key": {"type": "string", "description": "Root note, e.g. C, F#, Bb"},
        "mode": {"type": "string", "enum": list(music.MODES), "description": "Override the mood's mode"},
        "bpm": {"type": "integer"}, "bars": {"type": "integer", "description": "4-64, multiple of 4"},
        "stems": {"type": "boolean"}}},
}

FORGE_VOICE = {
    "name": "forge_voice",
    "description": "NPC dialogue voices. Define a cast (character -> engine/voice/fx) once; then render lines. Engines: "
                   "babble (offline Animalese-style), edge (neural TTS), hermes (your configured TTS). FX give "
                   "characters a sound. Writes WAVs + dialogue.json with typewriter timings.",
    "parameters": {"type": "object", "properties": {
        "project": _PROJECT, "name": {"type": "string", "description": "Dialogue file name (default dialogue)"},
        "cast": {"type": "object", "description": "{character: {engine, voice, fx, pitch_hz, speed, instructions, timbre}}; "
                 f"fx one of {', '.join(voice.CHARACTER_FX)}"},
        "lines": {"type": "array", "items": {"type": "object", "properties": {
            "character": {"type": "string"}, "text": {"type": "string"}, "id": {"type": "string"}},
            "required": ["character", "text"]}},
        "character": {"type": "string"}, "text": {"type": "string", "description": "Single line shortcut"},
        "engine": {"type": "string", "enum": list(voice.ENGINES)}}},
}

FORGE_SPRITE = {
    "name": "forge_sprite",
    "description": "2D pixel-art assets: animated characters (4-dir walk/idle), monsters, item icons, props; pixelize any "
                   "image (e.g. from image_generate); pack frames into sheets. Outputs PNG sheet, TexturePacker JSON, "
                   "Godot SpriteFrames .tres and GIF preview.",
    "parameters": {"type": "object", "properties": {
        "project": _PROJECT, "name": _NAME, "seed": _SEED,
        "kind": {"type": "string", "enum": ["character", "monster", "items", "props", "pixelize", "sheet"]},
        "archetype": {"type": "string", "enum": list(sprites.ARCHETYPES)},
        "hair": {"type": "string", "enum": list(sprites.HAIR)}, "outfit": {"type": "string", "enum": list(sprites.OUTFITS)},
        "hair_hue": {"type": "string"}, "body_hue": {"type": "string"}, "legs_hue": {"type": "string"},
        "monster": {"type": "string", "enum": list(sprites.MONSTER_MASKS)},
        "items": {"type": "array", "items": {"type": "string", "enum": list(sprites.ITEM_KINDS)}},
        "props": {"type": "array", "items": {"type": "string", "enum": list(tiles.PROPS)}},
        "hue": {"type": "string", "description": "Colour name (red, teal...) or #hex"},
        "size": {"type": "integer", "description": "Pixel size (items/monsters/pixelize)"},
        "source": {"type": "string", "description": "pixelize: image path"},
        "palette": {"type": "string", "enum": ["pico8", "sweetie16", "endesga32", "gameboy", "nes"]},
        "colors": {"type": "integer"},
        "frames": {"type": "array", "items": {"type": "string"}, "description": "sheet: image paths"},
        "animations": {"type": "object", "description": "sheet: {name: [frame indices]}"},
        "fps": {"type": "integer"}}},
}

FORGE_TILESET = {
    "name": "forge_tileset",
    "description": "Seamless autotiling tileset between two terrains (Wang corner set + fill variants, animated for "
                   "water/lava) with a Godot 4 TileSet .tres (terrains + collision) and layout JSON for other engines.",
    "parameters": {"type": "object", "properties": {
        "project": _PROJECT, "name": _NAME, "seed": _SEED,
        "lower": {"type": "string", "enum": list(tiles.TERRAINS)}, "upper": {"type": "string", "enum": list(tiles.TERRAINS)}}},
}

FORGE_MODEL3D = {
    "name": "forge_model3d",
    "description": "3D models as .glb with previews (views + turntable GIF). source=procedural: offline low-poly "
                   "generators with animations; fal/meshy: AI text- or image-to-3D (needs key); import: an existing .glb.",
    "parameters": {"type": "object", "properties": {
        "project": _PROJECT, "name": _NAME, "seed": _SEED,
        "source": {"type": "string", "enum": ["procedural", "fal", "meshy", "import"]},
        "kind": {"type": "string", "enum": list(procgen.KINDS)},
        "animations": {"type": "array", "items": {"type": "string", "enum": list(procgen.ANIMATIONS)}},
        "duration": {"type": "number"}, "hue": {"type": "number", "description": "0-1"},
        "layout": {"type": "array", "items": {"type": "string"}, "description": "dungeon rows: # wall . floor D door C chest T torch"},
        "prompt": {"type": "string"}, "image": {"type": "string", "description": "Image path or URL for image-to-3D"},
        "model": {"type": "string", "description": "fal model id override"}, "params": {"type": "object"},
        "path": {"type": "string", "description": "import: .glb path"}}},
}

FORGE_ENGINE = {
    "name": "forge_engine",
    "description": "Game engines. web: scaffold a complete playable HTML5 game from project assets (no install). "
                   "godot: scaffold/import/run headless (errors parsed). unity: scaffold/setup (batch mode). blender: "
                   "headless convert/lod/turntable/animate/info/script. unreal: asset import script. action=status "
                   "shows installed engines and configured providers.",
    "parameters": {"type": "object", "properties": {
        "project": _PROJECT,
        "engine": {"type": "string", "enum": ["web", "godot", "unity", "blender", "unreal"]},
        "action": {"type": "string", "description": "status | scaffold | import | run | setup | blender: convert, lod, "
                   "turntable, animate, info, script"},
        "title": {"type": "string"}, "subtitle": {"type": "string"}, "seed": _SEED,
        "theme": {"type": "string", "enum": list(web.THEMES)},
        "hero": {"type": "string", "enum": list(sprites.ARCHETYPES)},
        "regenerate": {"type": "boolean", "description": "Rebuild assets that already exist"},
        "seconds": {"type": "number"}, "scene": {"type": "string"},
        "input": {"type": "string"}, "output": {"type": "string"}, "ratios": {"type": "array", "items": {"type": "number"}},
        "frames": {"type": "integer"}, "size": {"type": "integer"}, "preset": {"type": "string"},
        "script": {"type": "string", "description": "blender script: path to your bpy file"},
        "args": {"type": "object"}, "uproject": {"type": "string"}},
        "required": ["engine"]},
}

FORGE_PLAYTEST = {
    "name": "forge_playtest",
    "description": "Actually play the build and report where it breaks or gets boring: crashes/console errors, stuck "
                   "spots, ignored input, FPS, event droughts, deaths/wins, coverage, screenshots, HTML report. web: "
                   "headless Chrome (policy explorer|monkey|agent — agent uses your vision model). godot: bot plays "
                   "at faster than real time.",
    "parameters": {"type": "object", "properties": {
        "project": _PROJECT,
        "target": {"type": "string", "description": "web | godot | URL | path to a web build"},
        "duration": {"type": "number", "description": "Seconds of play (godot: game time)"},
        "policy": {"type": "string", "enum": ["explorer", "monkey", "agent"]},
        "goal": {"type": "string", "description": "agent: what to try"},
        "screenshots": {"type": "boolean", "description": "godot: render frames (needs a display or xvfb)"},
        "seed": _SEED}},
}

FORGE_EXPORT = {
    "name": "forge_export",
    "description": "Ship it. web: PWA bundle (installable on phones, offline) + itch.io zip; single: one self-contained "
                   "HTML; capacitor: native Android/iOS wrapper; itch: butler push (publishes!); godot:<platform>; "
                   "unity:<platform>; godot_templates: install Godot export templates.",
    "parameters": {"type": "object", "properties": {
        "project": _PROJECT, "target": {"type": "string"},
        "source": {"type": "string", "description": "Web build dir (default <project>/web)"},
        "itch_target": {"type": "string", "description": "user/game:channel — required for target itch"},
        "app_id": {"type": "string"}, "version": {"type": "string"}, "debug": {"type": "boolean"}},
        "required": ["target"]},
}

ALL = [FORGE_SFX, FORGE_MUSIC, FORGE_VOICE, FORGE_SPRITE, FORGE_TILESET, FORGE_MODEL3D, FORGE_ENGINE, FORGE_PLAYTEST,
       FORGE_EXPORT]
