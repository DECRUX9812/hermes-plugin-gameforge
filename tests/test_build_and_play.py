"""End to end: scaffold real builds, play them in a real browser / real Godot, export them.
Skipped when the machine lacks Chrome or Godot."""

import json
import re
import shutil
from pathlib import Path

import pytest

from gameforge.engines import godot, web
from gameforge.export import web_export
from gameforge.playtest.cdp import find_browser
from gameforge.playtest.web_runner import WebPlaytester

needs_browser = pytest.mark.skipif(find_browser() is None, reason="no Chrome/Chromium")
needs_godot = pytest.mark.skipif(godot.locate() is None, reason="no Godot 4")


@pytest.fixture(scope="module")
def game(tmp_path_factory):
    p = tmp_path_factory.mktemp("game")
    web.scaffold(p, "Test Quest", "forest", 7)
    return p


@needs_browser
def test_explorer_plays_the_web_game_and_sees_gameplay(game, tmp_path):
    rep = WebPlaytester(game / "web", tmp_path / "pt", duration=25, seed=1).run()
    assert rep["telemetry"] is True
    assert rep["verdict"] in ("SOLID", "PLAYABLE")
    assert rep["fps"]["avg"] and rep["fps"]["avg"] > 20
    assert rep["coverage_cells"] > 3
    assert (tmp_path / "pt" / "report.html").exists() and (tmp_path / "pt" / "moments.jpg").exists()


@needs_browser
def test_playtester_catches_a_runtime_crash(game, tmp_path):
    broken = tmp_path / "broken"
    shutil.copytree(game / "web", broken)
    js = (broken / "game.js").read_text(encoding="utf-8")
    js = js.replace("  const p = player, sp = cfg.player.speed;",
                    "  if ((now() - t0) > 3000) player.bag.items.push(1);\n  const p = player, sp = cfg.player.speed;", 1)
    (broken / "game.js").write_text(js)
    rep = WebPlaytester(broken, tmp_path / "pt", duration=12, seed=1).run()
    assert rep["verdict"] == "BROKEN"
    assert any(i["severity"] == "critical" and "TypeError" in i["detail"] for i in rep["issues"])
    assert not any(i["title"] == "Player got stuck" for i in rep["issues"])  # the freeze is the crash, not the map


@needs_browser
def test_playtester_flags_a_level_where_nothing_happens(game, tmp_path):
    empty = tmp_path / "empty"
    shutil.copytree(game / "web", empty)
    cfg = json.loads((empty / "game.json").read_text(encoding="utf-8"))
    cfg["map"] = [r.replace("c", ".").replace("s", ".") for r in cfg["map"]]
    (empty / "game.json").write_text(json.dumps(cfg))
    rep = WebPlaytester(empty, tmp_path / "pt", duration=25, seed=1).run()
    assert any(i["title"] == "Nothing happens" for i in rep["issues"])


@needs_godot
def test_godot_build_runs_clean_and_the_bot_plays_it(game, tmp_path):
    b = godot.locate()
    godot.scaffold(game, "Test Quest", "forest", 7, "hero")
    run = godot.run(b, game, 5)
    assert run["ok"], run["errors"]
    rep = godot.playtest(b, game, tmp_path / "gpt", seconds=120)
    assert rep["verdict"] != "BROKEN", rep
    assert rep["events"].get("start") and rep["coverage_cells"] > 5
    assert rep["wall_seconds"] < 60  # faster than real time


def test_single_file_export_has_no_external_references(game, tmp_path):
    res = web_export.single_file(game / "web", tmp_path / "game.html", compress_audio=False)
    html = Path(res["html"]).read_text(encoding="utf-8")
    assert '<script src="game.js">' not in html and "assets/" not in html.split("window.__GF_CONFIG")[1][:200]
    assert not re.search(r'"(assets/[^"]+\.(png|wav|json))"', html)


def test_web_bundle_is_an_installable_pwa(game, tmp_path):
    res = web_export.bundle(game / "web", tmp_path / "dist", "Test Quest")
    d = Path(res["dir"])
    manifest = json.loads((d / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["icons"] and (d / manifest["icons"][0]["src"]).exists()
    assert "serviceWorker" in (d / "index.html").read_text(encoding="utf-8")
    files = json.loads(re.search(r"const FILES = (\[.*\]);", (d / "sw.js").read_text(encoding="utf-8")).group(1))
    assert "game.js" in files and "index.html" in files
