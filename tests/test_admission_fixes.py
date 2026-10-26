"""Regression tests for the catalog-admission security review (teknium1, PR #142443)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from gameforge.engines import godot
from gameforge.three import ai3d


# --- 1. profile-scoped secrets ------------------------------------------------------------
def test_get_secret_prefers_secret_scope(monkeypatch):
    from gameforge import secrets as secrets_mod

    monkeypatch.setenv("FAL_KEY", "from-env")
    monkeypatch.setitem(__import__("sys").modules, "agent.secret_scope",
                        type("m", (), {"get_secret": staticmethod(lambda name: "from-profile")}))
    assert secrets_mod.get_secret("FAL_KEY") == "from-profile"


def test_get_secret_falls_back_to_env(monkeypatch):
    from gameforge import secrets as secrets_mod

    monkeypatch.setenv("GAMEFORGE_TEST_KEY", "from-env")
    assert secrets_mod.get_secret("GAMEFORGE_TEST_KEY") == "from-env"


# --- 2/3. approval gate for blender -P and itch publish -----------------------------------
def test_blender_script_requires_approval():
    from gameforge.policy import pre_tool_call as _pre_tool_call

    out = _pre_tool_call(tool_name="forge_engine",
                         args={"engine": "blender", "action": "script", "script": "evil.py"})
    assert out and out["action"] == "approve" and "evil.py" in out["message"]


def test_other_blender_actions_do_not_require_approval():
    from gameforge.policy import pre_tool_call as _pre_tool_call

    assert _pre_tool_call(tool_name="forge_engine",
                          args={"engine": "blender", "action": "render", "input": "a.blend"}) is None


def test_itch_publish_requires_approval():
    from gameforge.policy import pre_tool_call as _pre_tool_call

    out = _pre_tool_call(tool_name="forge_export",
                         args={"target": "itch", "itch_target": "me/game:html5"})
    assert out and out["action"] == "approve" and "me/game:html5" in out["message"]


def test_web_export_does_not_require_approval():
    from gameforge.policy import pre_tool_call as _pre_tool_call

    assert _pre_tool_call(tool_name="forge_export", args={"target": "web"}) is None


# --- 4. local image upload ----------------------------------------------------------------
def _png(path: Path) -> Path:
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    return path


def test_image_inside_project_is_accepted(tmp_path):
    img = _png(tmp_path / "shot.png")
    ref = ai3d.validated_image_ref(str(img), tmp_path)
    assert ref.startswith("data:image/png;base64,")


def test_image_outside_project_is_refused(tmp_path):
    outside = _png(tmp_path / "outside" / "shot.png") if (tmp_path / "outside").mkdir() is None else None
    project = tmp_path / "game"
    project.mkdir()
    with pytest.raises(ai3d.ProviderError, match="outside the project directory"):
        ai3d.validated_image_ref(str(outside), project)


def test_non_image_bytes_are_refused(tmp_path):
    fake = tmp_path / "notes.png"
    fake.write_bytes(b"this is not a png, it is a text file")
    with pytest.raises(ai3d.ProviderError, match="does not look like"):
        ai3d.validated_image_ref(str(fake), tmp_path)


def test_unsupported_extension_is_refused(tmp_path):
    doc = tmp_path / "secret.txt"
    doc.write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ai3d.ProviderError, match="must be one of"):
        ai3d.validated_image_ref(str(doc), tmp_path)


def test_urls_pass_through_untouched():
    assert ai3d.validated_image_ref("https://example.com/a.png") == "https://example.com/a.png"


# --- 3. export source containment ---------------------------------------------------------
def test_export_source_outside_project_is_refused(tmp_path, monkeypatch):
    from gameforge import tools_engine

    project = tmp_path / "game"
    project.mkdir()
    monkeypatch.setattr(tools_engine, "_project", lambda args: project)
    out = tools_engine.forge_export({"project": str(project), "source": "/etc", "target": "web"})
    assert '"ok": false' in out.lower() or "outside the project directory" in out


# --- 5. godot template extraction ---------------------------------------------------------
def _zip(names: dict[str, bytes]) -> zipfile.ZipFile:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in names.items():
            z.writestr(name, data)
    buf.seek(0)
    return zipfile.ZipFile(buf)


def test_extract_skips_traversal_and_absolute_names(tmp_path):
    z = _zip({
        "templates/linux_release.x86_64": b"ok",
        "templates/../escape.txt": b"nope",
        "/abs.txt": b"nope",
        "__MACOSX/templates/._x": b"nope",
    })
    count = godot._extract_tpz(z, tmp_path)
    assert count == 1
    assert (tmp_path / "linux_release.x86_64").read_bytes() == b"ok"
    assert not (tmp_path.parent / "escape.txt").exists()
    assert not Path("/abs.txt").exists()
