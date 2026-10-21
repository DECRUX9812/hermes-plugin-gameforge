"""Asset tool handlers: sound effects, music, voices, sprites, tilesets and 3D models. Each writes
into the game project, records its recipe in the ledger, and returns paths plus a preview."""

from __future__ import annotations

import json
import os
import random
import shutil
import urllib.request
from pathlib import Path

from PIL import Image

from . import project as proj
from .audio import dsp, music, sfx, voice
from .gfx import atlas, canvas, pixelize, sprites, tiles
from .runtime import config, dispatch, fail, handler, ok
from .three import ai3d, gltf, procgen, render


def _project(args: dict) -> Path:
    return proj.resolve_project(args.get("project"), config("default_project"))


def _seed(args: dict) -> int:
    s = args.get("seed")
    return int(s) if s is not None else random.randrange(1, 1_000_000)


# ---------------------------------------------------------------------------- forge_sfx

@handler
def forge_sfx(args: dict) -> str:
    p = _project(args)
    out_dir = proj.asset_dir(p, "sfx")
    engine = args.get("engine", "synth")
    name = proj.safe_name(args.get("name") or args.get("preset") or "sfx")
    count = max(1, min(8, int(args.get("variations", 1))))
    if engine == "elevenlabs":
        return _sfx_elevenlabs(p, out_dir, name, args, count)
    preset = (args.get("preset") or "coin").lower()
    seed = _seed(args)
    style = args.get("style", "retro")
    files, recipes = [], []
    for v in range(count):
        buf, recipe = sfx.render(preset, seed, args.get("params"), style, variation=v)
        f = dsp.write_wav(out_dir / (f"{name}.wav" if count == 1 else f"{name}_{v + 1}.wav"), buf)
        files.append(f)
        recipes.append({**recipe, "file": f.name, "seconds": round(len(buf) / dsp.RATE, 3)})
    proj.record(p, "sfx", files, {"tool": "forge_sfx", "engine": "synth", "variants": recipes}, name)
    return ok(files=files, sounds=[{"file": r["file"], "seconds": r["seconds"]} for r in recipes],
              seed=seed, preset=preset, style=style, media=[files[0]],
              hint="Pass the same seed + preset to reproduce; 'params' (sfxr names) tweaks it; variations>1 gives a "
                   "random-pick pool so repeated actions never sound identical.")


def _sfx_elevenlabs(p: Path, out_dir: Path, name: str, args: dict, count: int) -> str:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        return fail("engine 'elevenlabs' needs ELEVENLABS_API_KEY (set it in the GameForge plugin settings); "
                    "engine 'synth' works offline")
    prompt = args.get("prompt") or args.get("preset")
    if not prompt:
        return fail("engine 'elevenlabs' needs a 'prompt' describing the sound")
    files = []
    for v in range(count):
        body = {"text": prompt, "prompt_influence": float(args.get("prompt_influence", 0.4))}
        if args.get("duration"):
            body["duration_seconds"] = float(args["duration"])
        req = urllib.request.Request("https://api.elevenlabs.io/v1/sound-generation", data=json.dumps(body).encode(),
                                     headers={"xi-api-key": key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            mp3 = out_dir / (f"{name}.mp3" if count == 1 else f"{name}_{v + 1}.mp3")
            mp3.write_bytes(resp.read())
        wav = voice.decode_to_wav(mp3, mp3.with_suffix(".wav"), 44100)
        files.append(wav or mp3)
    proj.record(p, "sfx", files, {"tool": "forge_sfx", "engine": "elevenlabs", "prompt": prompt,
                                  "license": "ElevenLabs terms of service"}, name)
    return ok(files=files, engine="elevenlabs", media=[files[0]])


# ---------------------------------------------------------------------------- forge_music

@handler
def forge_music(args: dict) -> str:
    p = _project(args)
    out_dir = proj.asset_dir(p, "music")
    mood = args.get("mood", "adventure")
    style = args.get("style", "chiptune")
    seed = _seed(args)
    name = proj.safe_name(args.get("name") or f"{mood}_{style}")
    score = music.compose(mood, args.get("key", "C"), int(args.get("bars", 16)), args.get("bpm"), seed, args.get("mode"))
    left, right = music.render(score, style, seed)
    wav = dsp.write_wav(out_dir / f"{name}.wav", left, music.RATE, stereo=right)
    mid = music.write_midi(score, out_dir / f"{name}.mid", style)
    files = [wav, mid]
    if args.get("stems"):
        for track in list(score.tracks):
            solo = music.Score(score.bpm, score.bars, {track: score.tracks[track]}, score.meta)
            l2, r2 = music.render(solo, style, seed)
            files.append(dsp.write_wav(out_dir / f"{name}_{track}.wav", l2, music.RATE, stereo=r2))
    seconds = round(len(left) / music.RATE, 2)
    recipe = {"tool": "forge_music", "mood": mood, "style": style, "seed": seed, "bpm": score.bpm, "bars": score.bars,
              **score.meta}
    proj.record(p, "music", files, recipe, name)
    return ok(files=files, seconds=seconds, loop=True, bpm=score.bpm, key=score.meta["key"], mode=score.meta["mode"],
              progression=score.meta["progression"], seed=seed, media=[wav],
              hint="The WAV loops seamlessly (reverb tail folded to the start). The .mid opens in any DAW. "
                   "stems=true renders each part separately for adaptive/layered music.")


# ---------------------------------------------------------------------------- forge_voice

@handler
def forge_voice(args: dict) -> str:
    p = _project(args)
    out_dir = proj.asset_dir(p, "voice")
    ledger = proj.load(p)
    cast: dict = dict(ledger.get("cast", {}))
    cast.update(args.get("cast") or {})
    lines = args.get("lines") or ([{"character": args.get("character", "narrator"), "text": args["text"]}]
                                  if args.get("text") else [])
    if not lines:
        if args.get("cast"):
            proj.set_meta(p, "cast", cast)
            return ok(cast=cast, hint="Cast saved. Now send 'lines'.")
        return fail("give 'text' (+ 'character') or a 'lines' list of {character, text}")
    default_engine = args.get("engine") or ("edge" if voice.edge_available() else "babble")
    manifest, files, notes = [], [], []
    for i, line in enumerate(lines):
        who = line.get("character", "narrator")
        role = cast.setdefault(who, _auto_role(who, len(cast)))
        engine = line.get("engine") or role.get("engine") or default_engine
        text = line["text"]
        stem = proj.safe_name(line.get("id") or f"{who}_{i + 1:02d}_{voice.slug(text, 20)}")
        wav_path = out_dir / f"{stem}.wav"
        fx = voice.CHARACTER_FX.get(role.get("fx", "none"), [])
        if engine == "babble":
            buf, timings = voice.babble(text, float(role.get("pitch_hz", 200)), float(role.get("speed", 1.0)),
                                        role.get("timbre", "warm"), seed=hash(who) & 0xFFFF)
            rate = 22050
            buf = voice.apply_fx(buf, fx, rate, seed=i) if fx else buf
            dsp.write_wav(wav_path, buf, rate)
        else:
            raw = _tts(engine, text, role, out_dir / f"{stem}.src.mp3")
            decoded = voice.decode_to_wav(raw, out_dir / f"{stem}.src.wav")
            if decoded is None:
                notes.append(f"{stem}: ffmpeg not found, kept {raw.name} without character FX")
                wav_path = raw
                timings = []
            else:
                buf, rate = dsp.read_wav(decoded)
                buf = voice.apply_fx(buf, fx, rate, seed=i) if fx else dsp.normalize(buf)
                dsp.write_wav(wav_path, buf, rate)
                timings = voice.estimate_timings(text, len(buf) / rate)
                for tmp in {raw, decoded} - {wav_path}:
                    tmp.unlink(missing_ok=True)
        files.append(wav_path)
        manifest.append({"id": stem, "character": who, "text": text, "file": str(wav_path.relative_to(p)),
                         "engine": engine, "timings": timings})
    dialogue = out_dir / (proj.safe_name(args.get("name") or "dialogue") + ".json")
    existing = json.loads(dialogue.read_text(encoding="utf-8")) if dialogue.exists() else {"lines": []}
    keep = [l for l in existing["lines"] if l["id"] not in {m["id"] for m in manifest}]
    dialogue.write_text(json.dumps({"cast": cast, "lines": keep + manifest}, indent=1), encoding="utf-8")
    proj.set_meta(p, "cast", cast)
    proj.record(p, "voice", files + [dialogue], {"tool": "forge_voice", "lines": len(manifest)}, dialogue.stem)
    return ok(files=files, dialogue=dialogue, cast=cast, notes=notes, media=files[:1],
              hint="dialogue.json carries per-character reveal timings for a typewriter text box.")


def _auto_role(name: str, idx: int) -> dict:
    low = name.lower()
    for key in voice.CHARACTER_FX:
        if key in low:
            return {"fx": key, "pitch_hz": 160 + (idx * 37) % 160}
    gender = "female" if idx % 2 else "male"
    return {"fx": "none", "voice": voice.EDGE_VOICES[gender][idx % 6], "pitch_hz": 140 + (idx * 47) % 200}


def _tts(engine: str, text: str, role: dict, dest: Path) -> Path:
    if engine == "edge":
        if not voice.edge_available():
            raise ValueError("engine 'edge' needs the edge-tts package (Hermes extra 'edge-tts'); use 'babble' "
                             "offline or 'hermes' for your configured TTS provider")
        return voice.edge_tts_to_file(text, role.get("voice", "en-US-GuyNeural"), dest,
                                      int(role.get("rate_pct", 0)), int(role.get("pitch_shift_hz", 0)))
    if engine == "hermes":
        res = json.loads(dispatch("text_to_speech", {"text": text, "output_path": str(dest),
                                                     **({"instructions": role["instructions"]} if role.get("instructions") else {})}))
        if not res.get("success"):
            raise ValueError(f"text_to_speech failed: {res.get('error')}")
        return Path(res["file_path"])
    raise ValueError(f"unknown voice engine {engine!r}; choose from {', '.join(voice.ENGINES)}")


# ---------------------------------------------------------------------------- forge_sprite

@handler
def forge_sprite(args: dict) -> str:
    p = _project(args)
    out_dir = proj.asset_dir(p, "sprite")
    kind = args.get("kind", "character")
    seed = _seed(args)
    scale = int(args.get("preview_scale", 6))
    name = proj.safe_name(args.get("name") or kind)
    fps = int(args.get("fps", 8))
    if kind == "character":
        spec = sprites.character_spec(args.get("archetype"), seed, {k: args.get(k) for k in
                                      ("hair", "outfit", "hair_hue", "body_hue", "legs_hue", "skin")})
        frames, anims = sprites.character_sheet(spec)
        return _write_sheet(p, out_dir, name, frames, anims, fps, scale, cols=6,
                            recipe={"tool": "forge_sprite", "kind": kind, "seed": seed, "spec": spec.__dict__})
    if kind == "monster":
        mk = args.get("monster", "slime")
        frames = sprites.monster_frames(mk, seed, args.get("hue"), int(args.get("size", 16)))
        return _write_sheet(p, out_dir, name, frames, {"idle": [0, 1]}, max(2, fps // 3), scale, cols=2,
                            recipe={"tool": "forge_sprite", "kind": kind, "monster": mk, "seed": seed, "hue": args.get("hue")})
    if kind in ("item", "items"):
        kinds = args.get("items") or [args.get("item", "coin")]
        size = int(args.get("size", 16))
        images = {k: sprites.item(k, size, args.get("hue")) for k in kinds}
        return _write_atlas(p, out_dir, name, images, scale, {"tool": "forge_sprite", "kind": "items", "items": kinds,
                                                              "size": size, "hue": args.get("hue")})
    if kind in ("prop", "props"):
        kinds = args.get("props") or [args.get("prop", "tree")]
        images = {f"{k}_{i}": tiles.prop(k, seed + i, args.get("hue")) for i, k in enumerate(kinds)}
        return _write_atlas(p, out_dir, name, images, scale, {"tool": "forge_sprite", "kind": "props", "props": kinds,
                                                              "seed": seed})
    if kind == "pixelize":
        src = args.get("source")
        if not src:
            return fail("kind 'pixelize' needs 'source' (an image path, e.g. from image_generate)")
        img = Image.open(os.path.expanduser(src))
        sprite = pixelize.pixelize(img, int(args.get("size", 32)), int(args.get("colors", 16)), args.get("palette"),
                                   bool(args.get("outline", True)))
        f = out_dir / f"{name}.png"
        sprite.save(f)
        prev = out_dir / f"{name}_preview.png"
        canvas.upscale(sprite, scale).save(prev)
        proj.record(p, "sprite", [f], {"tool": "forge_sprite", "kind": "pixelize", "source": str(src),
                                       "license": "derived from the source image"}, name)
        return ok(files=[f], preview=prev, media=[prev])
    if kind == "sheet":
        srcs = args.get("frames") or []
        if not srcs:
            return fail("kind 'sheet' needs 'frames': a list of image paths in playback order")
        frames = [Image.open(os.path.expanduser(s)).convert("RGBA") for s in srcs]
        anims = args.get("animations") or {"default": list(range(len(frames)))}
        return _write_sheet(p, out_dir, name, frames, anims, fps, max(1, scale // 2), cols=int(args.get("columns", 0)) or None,
                            recipe={"tool": "forge_sprite", "kind": "sheet", "frames": srcs})
    return fail(f"unknown kind {kind!r}; choose character, monster, item, prop, pixelize or sheet")


def _write_sheet(p: Path, out_dir: Path, name: str, frames: list, anims: dict, fps: int, scale: int, cols: int | None,
                 recipe: dict) -> str:
    sheet, rects = atlas.pack_grid(frames, cols)
    png = out_dir / f"{name}.png"
    sheet.save(png)
    names = [f"{name}_{i}" for i in range(len(frames))]
    js = atlas.write_json(out_dir / f"{name}.json", atlas.texturepacker_json(png.name, sheet, names, rects, anims, fps))
    res_path = "res://" + str(png.relative_to(p)).replace(os.sep, "/")
    tres = out_dir / f"{name}_frames.tres"
    tres.write_text(atlas.godot_spriteframes(res_path, rects, anims, fps), encoding="utf-8")
    first_anim = next(iter(anims.values()))
    walk = next((v for k, v in anims.items() if k.startswith("walk")), first_anim)
    gif = atlas.gif_preview([frames[i] for i in walk], out_dir / f"{name}_preview.gif", scale, fps)
    big = out_dir / f"{name}_sheet_preview.png"
    canvas.upscale(sheet, scale).save(big)
    proj.record(p, "sprite", [png, js, tres, gif], {**recipe, "animations": anims, "fps": fps,
                                                    "frame_size": [rects[0][2], rects[0][3]]}, name)
    return ok(sheet=png, atlas_json=js, godot_spriteframes=tres, preview_gif=gif, sheet_preview=big,
              frame_size=[rects[0][2], rects[0][3]], animations=anims, media=[gif, big],
              hint="atlas_json is TexturePacker JSON-hash (Phaser/Pixi/Defold) with Aseprite frameTags; the .tres is a "
                   "ready Godot 4 SpriteFrames for AnimatedSprite2D.")


def _write_atlas(p: Path, out_dir: Path, name: str, images: dict, scale: int, recipe: dict) -> str:
    sheet, placed = atlas.pack_shelf(images, 256)
    png = out_dir / f"{name}.png"
    sheet.save(png)
    keys = list(placed)
    js = atlas.write_json(out_dir / f"{name}.json",
                          atlas.texturepacker_json(png.name, sheet, keys, [placed[k] for k in keys]))
    singles = []
    for k, im in images.items():
        f = out_dir / f"{name}_{k}.png"
        im.save(f)
        singles.append(f)
    prev = out_dir / f"{name}_preview.png"
    canvas.upscale(sheet, scale).save(prev)
    proj.record(p, "sprite", [png, js, *singles], recipe, name)
    return ok(atlas=png, atlas_json=js, files=singles, preview=prev, media=[prev])


# ---------------------------------------------------------------------------- forge_tileset

@handler
def forge_tileset(args: dict) -> str:
    p = _project(args)
    out_dir = proj.asset_dir(p, "tileset")
    lower, upper = args.get("lower", "water"), args.get("upper", "grass")
    for t in (lower, upper):
        if t not in tiles.TERRAINS:
            return fail(f"unknown terrain {t!r}; choose from {', '.join(tiles.TERRAINS)}")
    seed = _seed(args)
    name = proj.safe_name(args.get("name") or f"{lower}_{upper}")
    animated = tiles.TERRAINS[lower].animated or tiles.TERRAINS[upper].animated
    frames = [tiles.wang_sheet(lower, upper, seed, f) for f in range(4 if animated else 1)]
    png = out_dir / f"{name}.png"
    frames[0].save(png)
    files = [png]
    if animated:  # extra frames side by side for engines that animate by atlas columns
        strip = Image.new("RGBA", (frames[0].width * len(frames), frames[0].height))
        for i, fr in enumerate(frames):
            strip.alpha_composite(fr, (i * fr.width, 0))
        anim_png = out_dir / f"{name}_anim.png"
        strip.save(anim_png)
        files.append(anim_png)
    tres = out_dir / f"{name}.tres"
    tres.write_text(tiles.godot_tileset("res://" + str(png.relative_to(p)).replace(os.sep, "/"), lower, upper),
                    encoding="utf-8")
    layout = {"tile_size": tiles.T, "columns": 4, "terrains": [lower, upper],
              "wang_order": [list(c) for c in tiles.WANG_ORDER],
              "corner_bits": "tl,tr,bl,br; 1 = upper terrain", "fill_variants": {"upper_row": 4, "lower_row": 5},
              "animated_frames": len(frames)}
    js = atlas.write_json(out_dir / f"{name}.json", layout)
    demo = _demo_map(lower, upper, seed)
    prev = out_dir / f"{name}_preview.png"
    canvas.upscale(demo, 3).save(prev)
    files += [tres, js]
    proj.record(p, "tileset", files, {"tool": "forge_tileset", "lower": lower, "upper": upper, "seed": seed}, name)
    return ok(sheet=png, godot_tileset=tres, layout=js, preview=prev, files=files, media=[prev],
              hint="Godot: assign the .tres to a TileMapLayer and paint with the terrain tool (Match Corners). "
                   "Other engines: layout.json maps each tile's corner bits.")


def _demo_map(lower: str, upper: str, seed: int, w: int = 14, h: int = 9) -> Image.Image:
    rng = random.Random(seed)
    ts = dict(tiles.transition_tiles(lower, upper, seed))
    cx, cy = w / 2, h / 2
    corners = [[1 if ((x - cx) / (w * 0.42)) ** 2 + ((y - cy) / (h * 0.42)) ** 2 < rng.uniform(0.6, 1.0) else 0
                for x in range(w + 1)] for y in range(h + 1)]
    img = Image.new("RGBA", (w * tiles.T, h * tiles.T))
    for y in range(h):
        for x in range(w):
            c = (corners[y][x], corners[y][x + 1], corners[y + 1][x], corners[y + 1][x + 1])
            img.alpha_composite(ts[c], (x * tiles.T, y * tiles.T))
    return img


# ---------------------------------------------------------------------------- forge_model3d

@handler
def forge_model3d(args: dict) -> str:
    p = _project(args)
    out_dir = proj.asset_dir(p, "model")
    source = args.get("source", "procedural")
    name = proj.safe_name(args.get("name") or args.get("kind") or "model")
    glb = out_dir / f"{name}.glb"
    if source == "procedural":
        kind = args.get("kind", "tree")
        seed = _seed(args)
        scene = procgen.build(kind, seed, args.get("hue"), args.get("layout"))
        for a in args.get("animations") or []:
            procgen.animate(scene, a, float(args.get("duration", 1.0)))
        gltf.write_glb(scene, glb)
        recipe = {"tool": "forge_model3d", "source": "procedural", "kind": kind, "seed": seed,
                  "animations": args.get("animations") or []}
    elif source in ai3d.PROVIDERS:
        if not ai3d.available()[source]:
            env = "FAL_KEY" if source == "fal" else "MESHY_API_KEY"
            return fail(f"source '{source}' needs {env} (GameForge plugin settings); source 'procedural' works offline")
        meta = ai3d.generate(source, args.get("prompt"), args.get("image"), glb, args.get("model"),
                             args.get("params"), int(args.get("timeout", 600)))
        scene = render.load_glb(glb)  # textures stay in the .glb; previews use base colours
        recipe = {"tool": "forge_model3d", **meta, "prompt": args.get("prompt"), "image": args.get("image"),
                  "license": f"{source} terms of service"}
    elif source == "import":
        src = Path(os.path.expanduser(args.get("path", "")))
        if src.suffix.lower() != ".glb":
            return fail("source 'import' takes a .glb path (convert other formats with forge_engine engine=blender action=convert)")
        shutil.copy2(src, glb)
        scene = render.load_glb(glb)
        recipe = {"tool": "forge_model3d", "source": "import", "path": str(src)}
    else:
        return fail("source must be 'procedural', 'fal', 'meshy' or 'import'")
    sheet = render.contact_sheet(scene, out_dir / f"{name}_views.png")
    anim = (args.get("animations") or [None])[0] if source == "procedural" else None
    gif = render.turntable(scene, out_dir / f"{name}_turntable.gif", anim=anim, duration=float(args.get("duration", 1.0)))
    info = gltf.read_glb_json(glb)
    tri = sum(len(n.mesh.faces) for n in scene.nodes() if n.mesh is not None)
    proj.record(p, "model", [glb, sheet, gif], recipe, name)
    return ok(model=glb, views=sheet, turntable=gif, triangles=tri,
              animations=[a["name"] for a in info.get("animations", [])], media=[sheet, gif],
              hint="GLB imports directly into Godot, Unity (glTFast), Unreal, Blender and three.js.")

