"""The built-in web engine: a complete HTML5 top-down action game generated from GameForge assets.
Needs nothing installed, runs in any browser (touch controls on phones), and is what the
playtester and the one-click web/mobile export work on out of the box."""

from __future__ import annotations

import json
import math
import random
import shutil
from collections import deque
from pathlib import Path

from .. import project as proj
from ..tools_assets import forge_music, forge_sfx, forge_sprite, forge_tileset

TEMPLATE = Path(__file__).parent / "templates" / "web_topdown"

THEMES = {
    "forest": {"lower": "water", "upper": "grass", "mood": "adventure", "enemy_hue": "lime", "tree": "tree"},
    "winter": {"lower": "deep_water", "upper": "snow", "mood": "mysterious", "enemy_hue": "cyan", "tree": "pine"},
    "desert": {"lower": "water", "upper": "sand", "mood": "heroic", "enemy_hue": "orange", "tree": "rock"},
    "volcano": {"lower": "lava", "upper": "stone", "mood": "boss", "enemy_hue": "red", "tree": "rock"},
    "dungeon": {"lower": "void", "upper": "dungeon", "mood": "spooky", "enemy_hue": "purple", "tree": "torch"},
}


def generate_map(seed: int, w: int = 36, h: int = 26, coins: int = 12, slimes: int = 7) -> list[str]:
    """Island level: noisy falloff for land, scattered props, everything placed on cells reachable
    from the start (BFS), coins spread out, the chest as far from the player as the island allows."""
    rng = random.Random(seed)
    waves = [(rng.uniform(0.15, 0.35), rng.uniform(0.15, 0.35), rng.uniform(0, 6), rng.uniform(0, 6)) for _ in range(4)]
    grid = [["~"] * w for _ in range(h)]
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            nx, ny = (x - w / 2) / (w / 2), (y - h / 2) / (h / 2)
            fall = 1 - (nx * nx + ny * ny)
            n = sum(math.sin(x * a + p) * math.cos(y * b + q) for a, b, p, q in waves) / 4
            if fall + n * 0.45 > 0.25:
                grid[y][x] = "."
    start = min(((x, y) for y in range(h) for x in range(w) if grid[y][x] == "."),
                key=lambda c: (c[0] - w / 2) ** 2 + (c[1] - h / 2) ** 2)
    for y in range(h):
        for x in range(w):
            if grid[y][x] == "." and abs(x - start[0]) + abs(y - start[1]) > 2:
                r = rng.random()
                grid[y][x] = "T" if r < 0.05 else "R" if r < 0.07 else "f" if r < 0.12 else "."
    dist = _bfs(grid, start)
    reach = sorted(dist, key=lambda c: dist[c])
    chest = reach[-1]
    picked: list[tuple[int, int]] = []
    for c in sorted(reach[len(reach) // 5:-1], key=lambda _: rng.random()):
        if len(picked) >= coins:
            break
        if all(abs(c[0] - o[0]) + abs(c[1] - o[1]) >= 4 for o in picked + [chest]):
            picked.append(c)
    for x, y in picked:
        grid[y][x] = "c"
    far = [c for c in reach if dist[c] >= 7 and grid[c[1]][c[0]] in ".f"]
    for x, y in rng.sample(far, min(slimes, len(far))):
        grid[y][x] = "s"
    grid[chest[1]][chest[0]] = "X"
    grid[start[1]][start[0]] = "@"
    return ["".join(r) for r in grid]


def _bfs(grid: list[list[str]], start: tuple[int, int]) -> dict[tuple[int, int], int]:
    dist = {start: 0}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= ny < len(grid) and 0 <= nx < len(grid[0]) and (nx, ny) not in dist and grid[ny][nx] not in "~TR":
                dist[(nx, ny)] = dist[(x, y)] + 1
                q.append((nx, ny))
    return dist


def _gen(handler, args: dict) -> dict:
    res = json.loads(handler(args))
    if not res.get("ok"):
        raise RuntimeError(f"{handler.__name__} failed: {res.get('error')}")
    return res


def scaffold(project: Path, title: str = "Hermes Quest", theme: str = "forest", seed: int = 7,
             hero: str = "hero", subtitle: str = "", regenerate: bool = False) -> dict:
    """Generate every asset the template needs (skipping ones already in the ledger unless
    ``regenerate``), copy them into ``web/assets`` and write a playable ``web/`` build."""
    if theme not in THEMES:
        raise ValueError(f"unknown theme {theme!r}; choose from {', '.join(THEMES)}")
    th = THEMES[theme]
    pstr = str(project)
    have = {(a["kind"], a["name"]) for a in proj.load(project)["assets"]}

    def need(kind: str, name: str) -> bool:
        return regenerate or (kind, name) not in have

    if need("sprite", "player"):
        _gen(forge_sprite, {"project": pstr, "kind": "character", "archetype": hero, "seed": seed, "name": "player"})
    if need("sprite", "enemy"):
        _gen(forge_sprite, {"project": pstr, "kind": "monster", "monster": "slime", "hue": th["enemy_hue"], "seed": seed,
                            "name": "enemy"})
    if need("sprite", "items"):
        _gen(forge_sprite, {"project": pstr, "kind": "items", "items": ["coin", "heart", "chest"], "name": "items"})
    if need("sprite", "props"):
        _gen(forge_sprite, {"project": pstr, "kind": "props", "props": [th["tree"], "rock", "flowers"], "seed": seed,
                            "name": "props"})
    tiles_name = f"{th['lower']}_{th['upper']}"
    if need("tileset", tiles_name):
        _gen(forge_tileset, {"project": pstr, "lower": th["lower"], "upper": th["upper"], "seed": seed, "name": tiles_name})
    sfx_plan = {"coin": ("coin", "retro", 3), "hurt": ("hurt", "retro", 2), "attack": ("whoosh", "retro", 2),
                "kill": ("explosion", "crunchy", 2), "win": ("powerup", "modern", 1), "lose": ("thud", "distant", 1),
                "step": ("footstep", "retro", 3)}
    for key, (preset, style, n) in sfx_plan.items():
        if need("sfx", key):
            _gen(forge_sfx, {"project": pstr, "preset": preset, "style": style, "variations": n, "seed": seed + len(key),
                             "name": key})
    if need("music", "theme"):
        _gen(forge_music, {"project": pstr, "mood": th["mood"], "style": "chiptune", "bars": 16, "seed": seed, "name": "theme"})

    web = project / "web"
    dst = web / "assets"
    dst.mkdir(parents=True, exist_ok=True)

    def copy(rel: str) -> str:
        src = project / rel
        shutil.copy2(src, dst / src.name)
        return f"assets/{src.name}"

    def ledger_files(kind: str, name: str) -> list[str]:
        entry = proj.find(project, kind, name)
        if entry is None:
            raise RuntimeError(f"ledger has no {kind} '{name}'")
        return entry["files"]

    sprite = {n: ledger_files("sprite", n) for n in ("player", "enemy", "items", "props")}
    tile_files = ledger_files("tileset", tiles_name)
    anim_sheet = next((f for f in tile_files if f.endswith("_anim.png")), None)
    sheet = anim_sheet or next(f for f in tile_files if f.endswith(".png"))
    pick = lambda files, suffix: next(f for f in files if f.endswith(suffix))  # noqa: E731
    assets = {
        "player": copy(pick(sprite["player"], "player.png")), "player_json": copy(pick(sprite["player"], ".json")),
        "enemy": copy(pick(sprite["enemy"], "enemy.png")), "enemy_json": copy(pick(sprite["enemy"], ".json")),
        "tiles": copy(sheet),
        "coin": copy(pick(sprite["items"], "_coin.png")), "heart": copy(pick(sprite["items"], "_heart.png")),
        "chest": copy(pick(sprite["items"], "_chest.png")),
        "tree": copy(pick(sprite["props"], f"_{th['tree']}_0.png")), "rock": copy(pick(sprite["props"], "_rock_1.png")),
        "flowers": copy(pick(sprite["props"], "_flowers_2.png")),
        "sfx": {k: [copy(f) for f in ledger_files("sfx", k) if f.endswith(".wav")] for k in sfx_plan},
        "music": copy(next(f for f in ledger_files("music", "theme") if f.endswith(".wav"))),
    }
    cfg_path = web / "game.json"
    old = json.loads(cfg_path.read_text()) if cfg_path.exists() and not regenerate else {}
    cfg = {
        "title": title, "subtitle": subtitle, "theme": theme, "seed": seed, "music_volume": 0.35,
        "player": {"speed": 72, "hp": 3, "attack_radius": 26, "attack_cooldown": 0.6},
        "enemy": {"speed": 28, "chase_radius": 70},
        "tiles": {"frames": 4 if anim_sheet else 1, "lower": th["lower"], "upper": th["upper"]},
        **{k: v for k, v in old.items() if k in ("player", "enemy", "map", "music_volume", "subtitle")},
        "assets": assets,
    }
    cfg.setdefault("map", generate_map(seed))
    cfg_path.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    (web / "index.html").write_text((TEMPLATE / "index.html").read_text().replace("{{TITLE}}", title), encoding="utf-8")
    shutil.copy2(TEMPLATE / "game.js", web / "game.js")
    proj.set_meta(project, "engines", {**proj.load(project).get("engines", {}), "web": "web/index.html"})
    return {"web_dir": web, "entry": web / "index.html", "config": cfg_path, "theme": theme,
            "map_size": [len(cfg["map"][0]), len(cfg["map"])],
            "hint": "Edit web/game.json (map rows: ~ lower terrain, . ground, T tree, R rock, f flowers, c coin, s enemy, "
                    "@ start, X chest) — no code change needed. Then forge_playtest target=web."}
