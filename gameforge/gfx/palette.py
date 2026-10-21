"""Palettes and hue-shifted colour ramps: shadows lean cool, highlights lean warm, which is most of
what separates pixel art from tinted squares."""

from __future__ import annotations

import colorsys

RGBA = tuple[int, int, int, int]

PALETTES: dict[str, list[str]] = {
    "pico8": ["000000", "1d2b53", "7e2553", "008751", "ab5236", "5f574f", "c2c3c7", "fff1e8", "ff004d",
              "ffa300", "ffec27", "00e436", "29adff", "83769c", "ff77a8", "ffccaa"],
    "sweetie16": ["1a1c2c", "5d275d", "b13e53", "ef7d57", "ffcd75", "a7f070", "38b764", "257179", "29366f",
                  "3b5dc9", "41a6f6", "73eff7", "f4f4f4", "94b0c2", "566c86", "333c57"],
    "endesga32": ["be4a2f", "d77643", "ead4aa", "e4a672", "b86f50", "733e39", "3e2731", "a22633", "e43b44",
                  "f77622", "feae34", "fee761", "63c74d", "3e8948", "265c42", "193c3e", "124e89", "0099db",
                  "2ce8f5", "ffffff", "c0cbdc", "8b9bb4", "5a6988", "3a4466", "262b44", "181425", "ff0044",
                  "68386c", "b55088", "f6757a", "e8b796", "c28569"],
    "gameboy": ["0f380f", "306230", "8bac0f", "9bbc0f"],
    "nes": ["000000", "fcfcfc", "f8f8f8", "bcbcbc", "7c7c7c", "a4e4fc", "3cbcfc", "0078f8", "0000fc", "b8b8f8",
            "6888fc", "0058f8", "0000bc", "d8b8f8", "9878f8", "6844fc", "4428bc", "f8b8f8", "f878f8", "d800cc",
            "940084", "f8a4c0", "f85898", "e40058", "a80020", "f0d0b0", "f87858", "f83800", "a81000", "fce0a8",
            "fca044", "e45c10", "881400", "f8d878", "f8b800", "ac7c00", "503000", "d8f878", "b8f818", "00b800",
            "007800", "b8f8b8", "58d854", "00a800", "006800", "b8f8d8", "58f898", "00a844", "005800", "00fcfc",
            "00e8d8", "008888", "004058", "f8d8f8", "787878"],
}


def hex_rgba(h: str, a: int = 255) -> RGBA:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a


def rgba_hex(c: RGBA) -> str:
    return "#%02x%02x%02x" % c[:3]


def hsv(h: float, s: float, v: float, a: int = 255) -> RGBA:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return int(r * 255), int(g * 255), int(b * 255), a


def ramp(hue: float, sat: float = 0.65, val: float = 0.75, steps: int = 4) -> list[RGBA]:
    """Dark → light ramp with hue shifting (shadows toward blue/purple, lights toward yellow)."""
    out = []
    for i in range(steps):
        t = i / max(1, steps - 1)  # 0 dark .. 1 light
        shift = (t - 0.5) * 0.08
        h = hue + (shift if 0.08 < hue % 1 < 0.6 else -shift)
        out.append(hsv(h, sat * (1.1 - 0.35 * t), val * (0.45 + 0.7 * t)))
    return out


def outline_for(c: RGBA) -> RGBA:
    h, s, v = colorsys.rgb_to_hsv(c[0] / 255, c[1] / 255, c[2] / 255)
    return hsv(h + 0.02, min(1.0, s * 0.8 + 0.2), v * 0.22)


def nearest(c: RGBA, palette: list[RGBA]) -> RGBA:
    """Perceptually weighted nearest palette colour (redmean distance)."""
    def dist(p: RGBA) -> float:
        rm = (c[0] + p[0]) / 2
        dr, dg, db = c[0] - p[0], c[1] - p[1], c[2] - p[2]
        return (2 + rm / 256) * dr * dr + 4 * dg * dg + (2 + (255 - rm) / 256) * db * db
    best = min(palette, key=dist)
    return best[0], best[1], best[2], c[3]


def named(name: str) -> list[RGBA]:
    if name not in PALETTES:
        raise ValueError(f"unknown palette {name!r}; choose from {', '.join(PALETTES)}")
    return [hex_rgba(h) for h in PALETTES[name]]


HUES = {"red": 0.0, "orange": 0.07, "gold": 0.12, "yellow": 0.15, "lime": 0.25, "green": 0.33, "teal": 0.47,
        "cyan": 0.5, "blue": 0.6, "indigo": 0.68, "purple": 0.75, "magenta": 0.83, "pink": 0.92, "brown": 0.07}


def hue_of(name_or_hex: str | float | None, default: float) -> float:
    if name_or_hex is None:
        return default
    if isinstance(name_or_hex, (int, float)):
        return float(name_or_hex) % 1
    key = name_or_hex.lower().strip()
    if key in HUES:
        return HUES[key]
    r, g, b, _ = hex_rgba(key)
    return colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[0]
