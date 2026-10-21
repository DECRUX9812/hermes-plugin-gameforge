"""Behaviour contracts for the asset generators and their tool handlers."""

import json
import struct
import wave
from collections import deque
from pathlib import Path

import pytest
from PIL import Image

from gameforge.audio import dsp, music, sfx
from gameforge.gfx import sprites, tiles
from gameforge.three import gltf, procgen, render
from gameforge.tools_assets import forge_model3d, forge_music, forge_sfx, forge_sprite, forge_tileset, forge_voice


def call(fn, **args):
    return json.loads(fn(args))


@pytest.mark.parametrize("preset", sfx.PRESETS)
def test_every_sfx_preset_is_audible_and_short(preset):
    buf, recipe = sfx.render(preset, seed=3)
    assert 0.01 < len(buf) / dsp.RATE < 4.5
    assert dsp.peak_db(buf) > -6
    assert recipe["preset"] == preset


def test_sfx_is_deterministic_per_seed_and_variations_differ(tmp_path):
    a = call(forge_sfx, project=str(tmp_path / "a"), preset="laser", seed=11, variations=3)
    b = call(forge_sfx, project=str(tmp_path / "b"), preset="laser", seed=11, variations=3)
    fa, fb = [Path(f).read_bytes() for f in a["files"]], [Path(f).read_bytes() for f in b["files"]]
    assert fa == fb
    assert len(set(fa)) == 3


def test_music_loop_has_exact_bar_length_and_valid_midi(tmp_path):
    res = call(forge_music, project=str(tmp_path), mood="heroic", bars=8, bpm=120, seed=2)
    wav, mid = (Path(f) for f in res["files"][:2])
    with wave.open(str(wav)) as w:
        assert w.getnchannels() == 2
        assert abs(w.getnframes() / w.getframerate() - 8 * 4 * 60 / 120) < 0.01
    data = mid.read_bytes()
    assert data[:4] == b"MThd" and struct.unpack(">H", data[8:10])[0] == 1
    assert data.count(b"MTrk") == struct.unpack(">H", data[10:12])[0]


def test_music_rejects_unknown_mood_without_raising(tmp_path):
    res = call(forge_music, project=str(tmp_path), mood="jazz-fusion")
    assert res["ok"] is False and "mood" in res["error"]


def test_character_sheet_has_four_facings_with_idle_and_walk(tmp_path):
    res = call(forge_sprite, project=str(tmp_path), kind="character", archetype="knight", seed=4)
    anims = res["animations"]
    for facing in sprites.FACINGS:
        assert len(anims[f"idle_{facing}"]) == 2 and len(anims[f"walk_{facing}"]) == 4
    atlas = json.loads(Path(res["atlas_json"]).read_text())
    assert len(atlas["frames"]) == 24 and atlas["meta"]["frameTags"]
    tres = Path(res["godot_spriteframes"]).read_text()
    assert tres.startswith('[gd_resource type="SpriteFrames"') and '&"walk_left"' in tres


def test_walk_frames_actually_animate():
    spec = sprites.character_spec("hero", 1)
    frames = [sprites.character_frame(spec, "right", f).tobytes() for f in range(4)]
    assert len(set(frames)) >= 2


def test_pixelize_turns_an_image_into_an_outlined_sprite_with_transparent_background(tmp_path):
    src = Image.new("RGB", (200, 200), (255, 255, 255))
    for x in range(60, 140):
        for y in range(40, 160):
            src.putpixel((x, y), (200, 40, 40))
    src_path = tmp_path / "art.png"
    src.save(src_path)
    res = call(forge_sprite, project=str(tmp_path), kind="pixelize", source=str(src_path), size=24)
    out = Image.open(res["files"][0])
    assert out.size == (24, 24)
    assert out.getpixel((0, 0))[3] == 0
    assert any(out.getpixel((x, y))[3] for x in range(24) for y in range(24))


def test_wang_transitions_join_seamlessly():
    """Two tiles that share an edge whose corners are both 'upper' must both be solid upper terrain there."""
    ts = dict(tiles.transition_tiles("water", "grass", 3))
    left, right = ts[(0, 1, 0, 1)], ts[(1, 0, 1, 0)]
    for y in range(4, 12):
        assert left.getpixel((15, y)) != tiles.texture("water", 3, 0).getpixel((15, y))
        assert right.getpixel((0, y)) != tiles.texture("water", 3, 0).getpixel((0, y))


def test_tileset_writes_godot_terrains_for_all_tiles(tmp_path):
    res = call(forge_tileset, project=str(tmp_path), lower="water", upper="grass", seed=1)
    tres = Path(res["godot_tileset"]).read_text()
    assert "terrain_set_0/mode = 1" in tres
    assert tres.count("/terrain_set = 0") == 16 + 8
    assert "physics_layer_0/polygon_0" in tres  # deep water is solid
    sheet = Image.open(res["sheet"])
    assert sheet.size == (64, 96)


@pytest.mark.parametrize("kind", procgen.KINDS)
def test_every_model_kind_round_trips_through_glb(tmp_path, kind):
    scene = procgen.build(kind, 2)
    path = gltf.write_glb(scene, tmp_path / f"{kind}.glb")
    js = gltf.read_glb_json(path)
    pos = [a for a in js["accessors"] if "min" in a and a["type"] == "VEC3"]
    assert pos and all(len(a["min"]) == 3 for a in pos)
    back = render.load_glb(path)
    faces = sum(len(n.mesh.faces) for n in back.nodes() if n.mesh)
    assert faces == sum(len(n.mesh.faces) for n in scene.nodes() if n.mesh) > 0


def test_character_animation_clips_are_exported(tmp_path):
    res = call(forge_model3d, project=str(tmp_path), kind="character", animations=["walk", "wave"], seed=1)
    assert res["animations"] == ["walk", "wave"]
    assert Path(res["turntable"]).exists() and Path(res["views"]).exists()


def test_rig_presets_refuse_models_without_a_rig(tmp_path):
    res = call(forge_model3d, project=str(tmp_path), kind="rock", animations=["walk"])
    assert res["ok"] is False and "character" in res["error"]


def test_babble_voice_writes_lines_and_typewriter_timings(tmp_path):
    res = call(forge_voice, project=str(tmp_path), engine="babble",
               cast={"Goblin": {"fx": "goblin", "pitch_hz": 260}},
               lines=[{"character": "Goblin", "text": "Shiny! Mine?"}])
    dialogue = json.loads(Path(res["dialogue"]).read_text())
    line = dialogue["lines"][0]
    assert line["character"] == "Goblin" and len(line["timings"]) == len("Shiny! Mine?")
    times = [t["t"] for t in line["timings"]]
    assert times == sorted(times)
    assert Path(tmp_path / line["file"]).stat().st_size > 1000


def test_ledger_records_recipes_for_regeneration(tmp_path):
    call(forge_sfx, project=str(tmp_path), preset="coin", seed=5, name="pickup")
    ledger = json.loads((tmp_path / "gameforge.json").read_text())
    entry = next(a for a in ledger["assets"] if a["name"] == "pickup")
    assert entry["recipe"]["variants"][0]["seed"] == 5 and entry["files"] == ["assets/sfx/pickup.wav"]


def test_generated_level_is_completable():
    from gameforge.engines.web import generate_map
    for seed in range(6):
        rows = generate_map(seed)
        assert len({len(r) for r in rows}) == 1
        flat = "".join(rows)
        assert flat.count("@") == 1 and flat.count("X") == 1 and flat.count("c") >= 6
        start = next((x, y) for y, r in enumerate(rows) for x, c in enumerate(r) if c == "@")
        seen, q = {start}, deque([start])
        while q:
            x, y = q.popleft()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if rows[ny][nx] not in "~TR" and (nx, ny) not in seen:
                    seen.add((nx, ny))
                    q.append((nx, ny))
        targets = {(x, y) for y, r in enumerate(rows) for x, c in enumerate(r) if c in "cX"}
        assert targets <= seen
