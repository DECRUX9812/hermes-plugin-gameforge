"""Turn any image (an AI render, a photo, concept art) into a game-ready pixel sprite: cut the
background, crop, downsample, snap to a palette, outline."""

from __future__ import annotations

from collections import deque

from PIL import Image

from . import palette as pal


def remove_background(img: Image.Image, tolerance: int = 40) -> Image.Image:
    """Flood-fill from the border with the corner colours; images that already carry alpha keep it."""
    img = img.convert("RGBA")
    if img.getextrema()[3][0] < 250:
        return img
    w, h = img.size
    px = img.load()
    seeds = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]

    def close(c: tuple) -> bool:
        return any(sum(abs(c[i] - s[i]) for i in range(3)) <= tolerance * 3 for s in seeds)

    seen = bytearray(w * h)
    q = deque((x, y) for x in range(w) for y in (0, h - 1))
    q.extend((x, y) for y in range(h) for x in (0, w - 1))
    while q:
        x, y = q.popleft()
        i = y * w + x
        if seen[i]:
            continue
        seen[i] = 1
        if not close(px[x, y]):
            continue
        px[x, y] = (0, 0, 0, 0)
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx]:
                q.append((nx, ny))
    return img


def pixelize(img: Image.Image, size: int = 32, colors: int = 16, palette: str | None = None,
             outline: bool = True, cut_background: bool = True) -> Image.Image:
    img = img.convert("RGBA")
    if cut_background:
        img = remove_background(img)
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    inner = size - 2 if outline else size
    scale = inner / max(img.width, img.height)
    small = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.BOX)
    alpha = small.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
    rgb = small.convert("RGB")
    if palette:
        swatch = pal.named(palette)
        pimg = Image.new("P", (1, 1))
        flat = [v for c in swatch for v in c[:3]]
        pimg.putpalette(flat + flat[:3] * (256 - len(swatch)))
        rgb = rgb.quantize(palette=pimg, dither=Image.Dither.NONE).convert("RGB")
    else:
        rgb = rgb.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert("RGB")
    sprite = rgb.convert("RGBA")
    sprite.putalpha(alpha)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(sprite, ((size - sprite.width) // 2, size - sprite.height - (1 if outline else 0)))
    if outline:
        canvas = add_outline(canvas)
    return canvas


def add_outline(img: Image.Image) -> Image.Image:
    out = img.copy()
    src, px = img.load(), out.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            if src[x, y][3]:
                continue
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < w and 0 <= ny < h and src[nx, ny][3]:
                    px[x, y] = pal.outline_for(src[nx, ny])
                    break
    return out
