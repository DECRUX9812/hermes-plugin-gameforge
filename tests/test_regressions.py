"""Regression tests for defects found by audit: each one failed before the fix next to it."""

import json
import zipfile
from pathlib import Path

import pytest

from gameforge.audio import dsp, sfx
from gameforge.engines import godot, unreal, web
from gameforge.tools_engine import forge_playtest


def test_pitch_shift_keeps_short_buffers_audible():
    """A 1000-sample click used to come back as an empty list (silence) after pitch shifting."""
    buf = [0.5] * 1000
    for semitones in (2.0, 7.0, -3.0, 12.0):
        out = dsp.pitch_shift(buf, semitones)
        assert out, f"pitch_shift({semitones}) returned silence"
        assert 200 < len(out) < 4000, f"pitch_shift({semitones}) length {len(out)} is not near the input"
        assert any(abs(x) > 1e-6 for x in out)


def test_pitch_shift_still_works_for_normal_length_audio():
    tones = [0.3] * 44100
    out = dsp.pitch_shift(tones, 12.0)
    assert len(out) > 20000


def test_layered_preset_with_post_params_keeps_the_layered_sound():
    """``footstep`` + params used to fall through to a 440 Hz square wave (25k samples, wrong sound)."""
    plain, _ = sfx.render("footstep", 7)
    volumed, recipe = sfx.render("footstep", 7, params={"sound_vol": 0.5})
    assert abs(len(volumed) - len(plain)) < len(plain) * 0.1, "volume change must not replace the sound"
    assert max(abs(x) for x in volumed) < max(abs(x) for x in plain) + 1e-9
    assert recipe["params"] == {"sound_vol": 0.5}


def test_layered_preset_rejects_waveform_params_by_name():
    with pytest.raises(ValueError, match="layered preset"):
        sfx.render("footstep", 7, params={"wave_type": 1})


def test_sfxr_preset_still_accepts_waveform_params():
    _, recipe = sfx.render("coin", 3, params={"sound_vol": 0.5})
    assert recipe["sfxr"]["sound_vol"] == 0.5


def test_playtest_accepts_a_project_relative_target(tmp_path, monkeypatch):
    """``target="web/index.html"`` used to be validated against the process CWD, not the game."""
    game = tmp_path / "game"
    web.scaffold(game, "Rel Target", "forest", 7)
    monkeypatch.chdir(tmp_path)          # deliberately NOT the project directory
    res = json.loads(forge_playtest({"project": str(game), "target": "web/index.html", "duration": 3}))
    if res.get("ok") is False and "Chrome" in str(res.get("error", "")):
        pytest.skip("no browser available")
    assert res.get("ok") is True, res


def test_unreal_import_script_survives_an_empty_project(tmp_path):
    script = unreal.import_script(tmp_path / "fresh")
    assert script.exists()
    assert "import" in script.read_text(encoding="utf-8").lower()


def test_godot_web_preset_is_single_threaded():
    """A threaded web build needs SharedArrayBuffer (COOP/COEP) and dies on plain static hosting."""
    presets = godot.export_presets()
    web_at = presets.index('platform="Web"')
    options_at = presets.index("[preset.0.options]") if "[preset.0.options]" in presets else web_at
    web_section = presets[web_at:presets.find("[preset.", options_at + 1) if presets.find("[preset.", options_at + 1) != -1 else len(presets)]
    assert "threads/export_type=0" in web_section
    assert "threads/export_type=0" not in presets[:web_at], "only the web preset gets single-threading"


def test_export_template_zip_keeps_its_layout(tmp_path):
    tpz = tmp_path / "templates.tpz"
    with zipfile.ZipFile(tpz, "w") as z:
        z.writestr("templates/version.txt", "4.7.1.stable")
        z.writestr("templates/linux_release.x86_64", "bin")
        z.writestr("templates/web_release.zip", "zip")
        z.writestr("__MACOSX/._junk", "x")
    dest = tmp_path / "out"
    with zipfile.ZipFile(tpz) as z:
        count = godot._extract_tpz(z, dest)
    assert count == 3
    assert (dest / "linux_release.x86_64").read_text(encoding="utf-8") == "bin"
    assert (dest / "version.txt").read_text(encoding="utf-8") == "4.7.1.stable"
    assert not (dest / "templates").exists()
    assert not (dest / "__MACOSX").exists()


def test_godot_split_version_handles_patch_releases():
    assert godot._split_version("4.7.1.stable.official.a13da4feb") == ("4.7.1", "stable")
    assert godot._split_version("4.4.stable") == ("4.4", "stable")
