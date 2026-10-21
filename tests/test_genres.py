"""Tests for the 4 web genres: scaffold, syntax check, and playtest verification."""

import json
import subprocess
from pathlib import Path

import pytest

from gameforge.engines import web
from gameforge.playtest.cdp import find_browser
from gameforge.playtest.web_runner import WebPlaytester

needs_browser = pytest.mark.skipif(find_browser() is None, reason="no Chrome/Chromium")


@pytest.mark.parametrize("genre", web.GENRES)
def test_every_genre_scaffolds_and_passes_node_syntax(genre, tmp_path):
    p = tmp_path / genre
    res = web.scaffold(p, f"Test {genre}", "forest", 7, genre=genre)
    assert res["genre"] == genre
    js = p / "web" / "game.js"
    assert js.exists()
    syn = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
    assert syn.returncode == 0, syn.stderr
    cfg = json.loads((p / "web" / "game.json").read_text(encoding="utf-8"))
    assert cfg["genre"] == genre
    assert "player" in cfg["assets"]
    assert "tiles" in cfg["assets"]


@needs_browser
@pytest.mark.parametrize("genre", ["arena", "roguelike"])
def test_arcade_genres_playtest_cleanly(genre, tmp_path):
    p = tmp_path / genre
    web.scaffold(p, f"Arcade {genre}", "forest", 7, genre=genre)
    rep = WebPlaytester(p / "web", tmp_path / f"pt-{genre}", duration=12, policy="auto", seed=1).run()
    assert rep["telemetry"] is True
    assert rep["verdict"] in ("SOLID", "PLAYABLE")
    assert rep["fps"]["avg"] and rep["fps"]["avg"] > 30
    assert rep["events"].get("boot")
    assert rep["events"].get("start")
