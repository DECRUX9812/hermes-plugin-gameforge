"""The built-in web engine: a complete HTML5 game generated from GameForge assets.

One shared runtime (``templates/_shared.js``: input incl. gamepad, audio, particles, camera,
pause, best scores, the RAF loop, playtester telemetry) plus one genre module per genre
(``templates/genres/*.js``). ``scaffold`` writes ``game.js`` as genre-first + runtime-second:
inside a single classic script the genre's ``const GENRE`` is therefore initialised before the
runtime's ``boot()`` runs at the end of the same file.

Genres
------
topdown     collect every coin, then open the chest (island map, chasing enemies, burst attack)
platformer  physics side-scroller (coyote time, jump buffering, stomps, spikes, goal flag)
arena       wave survival in a walled pit (auto-aimed shots, dash, five escalating waves)
roguelike   room-to-room dungeon crawl (keys open the exit, potions, ghosts through walls)

Every genre is driven by ``web/game.json``; the ASCII map is editable without touching code.
"""

from __future__ import annotations

import json
import math
import random
import shutil
from collections import deque
from pathlib import Path

from .. import project as proj
from ..tools_assets import forge_music, forge_sfx, forge_sprite, forge_tileset

TEMPLATES = Path(__file__).parent / "templates"
SHARED_JS = TEMPLATES / "_shared.js"
GENRE_DIR = TEMPLATES / "genres"
INDEX_HTML = TEMPLATES / "web_topdown" / "index.html"   # genre-independent shell

GENRES = ("topdown", "platformer", "arena", "roguelike")

THEMES = {
    "forest": {"lower": "water", "upper": "grass", "mood": "adventure", "enemy_hue": "lime", "tree": "tree",
               "sky_top": "#6b9bd1", "sky_bottom": "#29366f"},
    "winter": {"lower": "deep_water", "upper": "snow", "mood": "mysterious", "enemy_hue": "cyan", "tree": "pine",
               "sky_top": "#a8d0e6", "sky_bottom": "#29366f"},
    "desert": {"lower": "water", "upper": "sand", "mood": "heroic", "enemy_hue": "orange", "tree": "rock",
               "sky_top": "#e8b64c", "sky_bottom": "#7b4b2a"},
    "volcano": {"lower": "lava", "upper": "stone", "mood": "boss", "enemy_hue": "red", "tree": "rock",
                "sky_top": "#7b2d26", "sky_bottom": "#1a1c2c"},
    "dungeon": {"lower": "void", "upper": "dungeon", "mood": "spooky", "enemy_hue": "purple", "tree": "torch",
                "sky_top": "#29366f", "sky_bottom": "#14121f"},
}

GOALS = {
    "topdown": "GRAB EVERY COIN THEN THE CHEST",
    "platformer": "REACH THE FLAG",
    "arena": "SURVIVE FIVE WAVES",
    "roguelike": "FIND THE KEYS THEN THE EXIT",
}


# ---------------------------------------------------------------------------- maps
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


# Mirrors the physics in genres/platformer.js: v=390, g=1350 up / 1750 down, speed 132 gives
# ~0.54 s of airtime = ~4.4 tiles of travel, so a 3-tile gap is a comfortable running jump and a
# 4-tile gap would be pixel-perfect. JUMP_TILES_UP comes from the 56 px jump height (3.5 tiles).
JUMP_TILES_UP = 3
JUMP_TILES_ACROSS = 3


def generate_platformer_map(seed: int, w: int = 128, h: int = 16) -> list[str]:
    """A left-to-right level that is completable by construction: ground gaps never exceed a
    running jump, every floating platform sits within jump height of a surface below it."""
    rng = random.Random(seed)
    floor_y = h - 3
    grid = [["." for _ in range(w)] for _ in range(h)]
    for x in range(w):
        for y in range(floor_y, h):
            grid[y][x] = "#"
    x = 12
    while x < w - 14:
        gap = rng.randint(2, JUMP_TILES_ACROSS)
        if rng.random() < 0.45:
            for gx in range(x, min(w - 6, x + gap)):
                for y in range(floor_y, h):
                    grid[y][gx] = "."
            x += gap + rng.randint(4, 9)
        else:
            x += rng.randint(5, 10)
    # Floating platforms: placed over solid ground (never hovering right over a pit edge where
    # they block the jump arc), or spanning across a pit as a stepping stone.
    for px in range(9, w - 9, rng.randint(7, 11)):
        # don't start a platform on a pit edge where the face intercepts jumping players
        if any(grid[floor_y][min(w - 1, px + d)] == "." for d in (-1, 0, 1)):
            continue
        width = rng.randint(3, 5)
        rise = rng.randint(2, JUMP_TILES_UP)
        py = floor_y - rise
        if py < 3:
            continue
        for dx in range(width):
            if px + dx < w - 1:
                grid[py][px + dx] = "#"
        if rng.random() < 0.75:
            grid[py - 1][px + rng.randrange(width)] = "c"
        if rng.random() < 0.3:
            grid[py - 1][px + rng.randrange(width)] = "b"
    for gx in range(4, w - 4):
        if grid[floor_y][gx] != "#":
            continue
        r = rng.random()
        if r < 0.045:
            grid[floor_y - 1][gx] = "c"
        elif r < 0.075:
            grid[floor_y - 1][gx] = "s"
    # spikes are a hazard you jump OVER, never a wall in a pit mouth (a pit has no floor to put
    # them on), and never within 2 tiles of a pit edge: the landing zone after a jump is not a
    # place the player can react, so a spike there reads as an unavoidable death.
    pit_cols = {x for x in range(w) if grid[floor_y][x] == "."}
    def near_pit(x: int) -> bool:
        return any((x + d) in pit_cols for d in range(-2, 3))
    for _ in range(rng.randint(3, 6)):
        gx = rng.randint(10, w - 12)
        run = rng.randint(1, 2)
        for x in range(gx, min(w - 4, gx + run)):
            if grid[floor_y][x] == "#" and grid[floor_y - 1][x] == "." and not near_pit(x):
                grid[floor_y - 1][x] = "^"
    grid[floor_y - 1][3] = "P"
    grid[floor_y - 1][w - 4] = "X"
    return ["".join(row) for row in grid]


def generate_arena_map(seed: int, w: int = 20, h: int = 15) -> list[str]:
    """A walled pit with a few pillars for cover. Waves spawn on free floor away from the player."""
    rng = random.Random(seed)
    grid = [["#" if x in (0, w - 1) or y in (0, h - 1) else "." for x in range(w)] for y in range(h)]
    for _ in range(rng.randint(2, 4)):
        px, py = rng.randint(4, w - 6), rng.randint(3, h - 5)
        bw, bh = rng.randint(1, 3), rng.randint(1, 2)
        for x in range(px, min(w - 2, px + bw)):
            for y in range(py, min(h - 2, py + bh)):
                grid[y][x] = "#"
    grid[h // 2][w // 2] = "P"
    return ["".join(row) for row in grid]


def generate_roguelike_map(seed: int, rooms: int = 6, room_w: int = 11, room_h: int = 9) -> list[str]:
    """Rooms on a loose grid joined by corridors, with the exit in the furthest room so the level
    forces a full traversal; keys and loot sit in the rooms along the way."""
    rng = random.Random(seed)
    cols = 3
    grid_rows = max(2, math.ceil(rooms / cols))
    w, h = cols * room_w, grid_rows * room_h
    grid = [["#" for _ in range(w)] for _ in range(h)]
    centers: list[tuple[int, int]] = []
    for i in range(rooms):
        cx = (i % cols) * room_w + room_w // 2
        cy = (i // cols) * room_h + room_h // 2
        rw, rh = rng.randint(6, 8), rng.randint(5, 6)
        for x in range(cx - rw // 2, cx + rw // 2 + 1):
            for y in range(cy - rh // 2, cy + rh // 2 + 1):
                if 0 < x < w - 1 and 0 < y < h - 1:
                    grid[y][x] = "."
        centers.append((cx, cy))
    for (ax, ay), (bx, by) in zip(centers, centers[1:]):
        for x in range(min(ax, bx), max(ax, bx) + 1):
            grid[ay][x] = "."
        for y in range(min(ay, by), max(ay, by) + 1):
            grid[y][bx] = "."
    sx, sy = centers[0]
    grid[sy][sx] = "P"
    ex, ey = centers[-1]
    grid[ey][ex] = "D"
    for cx, cy in centers[1:-1]:
        if rng.random() < 0.65:
            grid[cy][cx] = "k"
    for cx, cy in centers[1:]:
        for _ in range(rng.randint(2, 4)):
            x, y = cx + rng.randint(-3, 3), cy + rng.randint(-2, 2)
            if 0 < x < w - 1 and 0 < y < h - 1 and grid[y][x] == ".":
                grid[y][x] = rng.choice("cshg")
    return ["".join(row) for row in grid]


MAPS = {"topdown": generate_map, "platformer": generate_platformer_map, "arena": generate_arena_map,
        "roguelike": generate_roguelike_map}


# ---------------------------------------------------------------------------- assets
def _gen(handler, args: dict) -> dict:
    res = json.loads(handler(args))
    if not res.get("ok"):
        raise RuntimeError(f"{handler.__name__} failed: {res.get('error')}")
    return res


def _sprite_plan(genre: str, th: dict, seed: int, hero: str) -> list[tuple[str, dict]]:
    """(ledger name, forge_sprite args) for every sprite sheet a genre needs."""
    plan = [("player", {"kind": "character", "archetype": hero, "seed": seed}),
            ("items", {"kind": "items", "items": ["coin", "heart", "chest", "key", "potion"]})]
    if genre == "topdown":
        plan.append(("enemy", {"kind": "monster", "monster": "slime", "hue": th["enemy_hue"], "seed": seed}))
        plan.append(("props", {"kind": "props", "props": [th["tree"], "rock", "flowers"], "seed": seed}))
    elif genre == "platformer":
        plan.append(("enemy", {"kind": "monster", "monster": "slime", "hue": th["enemy_hue"], "seed": seed}))
        plan.append(("bat", {"kind": "monster", "monster": "bat", "hue": "purple", "seed": seed + 3}))
    elif genre == "arena":
        plan.append(("enemy", {"kind": "monster", "monster": "spaceship", "hue": th["enemy_hue"], "seed": seed}))
        plan.append(("brute", {"kind": "monster", "monster": "golem", "hue": "orange", "seed": seed + 5}))
    else:
        plan.append(("enemy", {"kind": "monster", "monster": "bat", "hue": th["enemy_hue"], "seed": seed}))
        plan.append(("ghost", {"kind": "monster", "monster": "ghost", "hue": "cyan", "seed": seed + 2}))
    return plan


def _sfx_plan(genre: str) -> dict[str, tuple[str, str, int]]:
    common = {"coin": ("coin", "retro", 3), "hurt": ("hurt", "retro", 2), "kill": ("explosion", "crunchy", 2),
              "win": ("powerup", "modern", 1), "lose": ("thud", "distant", 1), "step": ("footstep", "retro", 3)}
    if genre == "topdown":
        return {**common, "attack": ("whoosh", "retro", 2)}
    if genre == "platformer":
        return {**common, "jump": ("jump", "retro", 2)}
    if genre == "arena":
        return {**common, "attack": ("laser", "retro", 3), "wave": ("powerup", "retro", 1), "whoosh": ("whoosh", "retro", 1)}
    return {**common, "attack": ("swing", "crunchy", 2), "door": ("powerup", "modern", 1)}


def scaffold(project: Path, title: str = "Hermes Quest", theme: str = "forest", seed: int = 7,
             hero: str = "hero", subtitle: str = "", regenerate: bool = False, genre: str = "topdown") -> dict:
    """Generate every asset the genre needs (skipping ones already in the ledger unless
    ``regenerate``), copy them into ``web/assets`` and write a playable ``web/`` build."""
    if theme not in THEMES:
        raise ValueError(f"unknown theme {theme!r}; choose from {', '.join(THEMES)}")
    if genre not in GENRES:
        raise ValueError(f"unknown genre {genre!r}; choose from {', '.join(GENRES)}")
    genre_js = GENRE_DIR / f"{genre}.js"
    if not genre_js.exists():
        raise FileNotFoundError(f"missing genre runtime {genre_js}")
    th = THEMES[theme]
    pstr = str(project)
    have = {(a["kind"], a["name"]) for a in proj.load(project)["assets"]}

    def need(kind: str, name: str) -> bool:
        return regenerate or (kind, name) not in have

    sprite_plan = _sprite_plan(genre, th, seed, hero)
    for name, args in sprite_plan:
        if need("sprite", name):
            _gen(forge_sprite, {"project": pstr, "name": name, **args})
    tiles_name = f"{th['lower']}_{th['upper']}"
    if need("tileset", tiles_name):
        _gen(forge_tileset, {"project": pstr, "lower": th["lower"], "upper": th["upper"], "seed": seed,
                             "name": tiles_name})
    sfx_plan = _sfx_plan(genre)
    for key, (preset, style, n) in sfx_plan.items():
        if need("sfx", key):
            _gen(forge_sfx, {"project": pstr, "preset": preset, "style": style, "variations": n,
                             "seed": seed + len(key), "name": key})
    if need("music", "theme"):
        _gen(forge_music, {"project": pstr, "mood": th["mood"], "style": "chiptune", "bars": 16, "seed": seed,
                           "name": "theme"})

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

    def pick(files: list[str], suffix: str) -> str | None:
        return next((f for f in files if f.endswith(suffix)), None)

    sprite_names = [name for name, _ in sprite_plan]
    files_by_sprite = {n: ledger_files("sprite", n) for n in sprite_names}
    tile_files = ledger_files("tileset", tiles_name)
    anim_sheet = pick(tile_files, "_anim.png")
    sheet = anim_sheet or pick(tile_files, ".png")

    def sprite_pair(name: str) -> tuple[str | None, str | None]:
        png = pick(files_by_sprite[name], f"{name}.png")
        js = pick(files_by_sprite[name], ".json")
        return (copy(png), copy(js)) if png and js else (None, None)

    assets: dict = {}
    assets["player"], assets["player_json"] = sprite_pair("player")
    assets["enemy"], assets["enemy_json"] = sprite_pair("enemy")
    for extra in ("bat", "brute", "ghost"):
        if extra in files_by_sprite:
            assets[extra], assets[f"{extra}_json"] = sprite_pair(extra)
    assets["tiles"] = copy(sheet) if sheet else ""
    for item in ("coin", "heart", "chest", "key", "potion"):
        f = pick(files_by_sprite["items"], f"_{item}.png")
        if f:
            assets[item] = copy(f)
    if "props" in files_by_sprite:
        for key, suffix in (("tree", f"_{th['tree']}_0.png"), ("rock", "_rock_1.png"), ("flowers", "_flowers_2.png")):
            f = pick(files_by_sprite["props"], suffix)
            if f:
                assets[key] = copy(f)
    assets["sfx"] = {k: [copy(f) for f in ledger_files("sfx", k) if f.endswith(".wav")] for k in sfx_plan}
    music = pick(ledger_files("music", "theme"), ".wav")
    assets["music"] = copy(music) if music else ""

    cfg_path = web / "game.json"
    old = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() and not regenerate else {}
    cfg = {
        "title": title, "subtitle": subtitle or GOALS[genre], "theme": theme, "genre": genre, "seed": seed,
        "music_volume": 0.35,
        "player": {"speed": 72, "hp": 3, "attack_radius": 26, "attack_cooldown": 0.6},
        "enemy": {"speed": 34 if genre == "arena" else 28, "chase_radius": 70},
        "goal_hint": GOALS[genre],
        "tiles": {"frames": 4 if anim_sheet else 1, "lower": th["lower"], "upper": th["upper"]},
        "sky_top": th["sky_top"], "sky_bottom": th["sky_bottom"],
        **{k: v for k, v in old.items() if k in ("player", "enemy", "map", "music_volume", "subtitle")},
        "assets": assets,
    }
    cfg.setdefault("map", MAPS[genre](seed))
    cfg_path.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    game_js = genre_js.read_text(encoding="utf-8") + "\n\n" + SHARED_JS.read_text(encoding="utf-8")
    (web / "game.js").write_text(game_js, encoding="utf-8")
    (web / "index.html").write_text(INDEX_HTML.read_text(encoding="utf-8").replace("{{TITLE}}", title), encoding="utf-8")
    proj.set_meta(project, "engines", {**proj.load(project).get("engines", {}), "web": "web/index.html"})
    return {"web_dir": web, "entry": web / "index.html", "config": cfg_path, "theme": theme, "genre": genre,
            "map_size": [len(cfg["map"][0]), len(cfg["map"])],
            "hint": f"{genre}: edit web/game.json — the map is plain ASCII, no code change needed — then "
                    f"forge_playtest target=web policy={genre}."}
