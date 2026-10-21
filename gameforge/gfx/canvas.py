"""A symbol grid that becomes pixel art: regions are painted with symbols, then auto-shaded (light
from the top-left), selectively outlined and turned into a Pillow image."""

from __future__ import annotations

from PIL import Image

from .palette import RGBA, outline_for

EMPTY = "."


class Grid:
    def __init__(self, w: int, h: int) -> None:
        self.w, self.h = w, h
        self.cells = [[EMPTY] * w for _ in range(h)]

    @classmethod
    def from_rows(cls, rows: list[str]) -> "Grid":
        g = cls(len(rows[0]), len(rows))
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                g.cells[y][x] = ch
        return g

    def get(self, x: int, y: int) -> str:
        return self.cells[y][x] if 0 <= x < self.w and 0 <= y < self.h else EMPTY

    def set(self, x: int, y: int, sym: str) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.cells[y][x] = sym

    def overlay(self, rows: list[str], dy: int = 0, dx: int = 0) -> None:
        """Paint non-empty symbols of ``rows`` over this grid."""
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch != EMPTY:
                    self.set(x + dx, y + dy, ch)

    def remap(self, mapping: dict[str, str]) -> None:
        for row in self.cells:
            for x, ch in enumerate(row):
                row[x] = mapping.get(ch, ch)

    def shifted(self, dx: int, dy: int) -> "Grid":
        g = Grid(self.w, self.h)
        for y in range(self.h):
            for x in range(self.w):
                g.set(x + dx, y + dy, self.cells[y][x])
        return g

    def mirrored(self) -> "Grid":
        return Grid.from_rows(["".join(reversed(r)) for r in self.cells])

    # -- primitive fills for procedural shapes
    def disc(self, cx: float, cy: float, r: float, sym: str) -> None:
        for y in range(self.h):
            for x in range(self.w):
                if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= r * r:
                    self.cells[y][x] = sym

    def rect(self, x0: int, y0: int, x1: int, y1: int, sym: str) -> None:
        for y in range(max(0, y0), min(self.h, y1 + 1)):
            for x in range(max(0, x0), min(self.w, x1 + 1)):
                self.cells[y][x] = sym

    def poly(self, pts: list[tuple[float, float]], sym: str) -> None:
        for y in range(self.h):
            for x in range(self.w):
                if _inside(x + 0.5, y + 0.5, pts):
                    self.cells[y][x] = sym

    def line(self, x0: int, y0: int, x1: int, y1: int, sym: str) -> None:
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            self.set(x0, y0, sym)
            if x0 == x1 and y0 == y1:
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy


def _inside(x: float, y: float, pts: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def render(grid: Grid, ramps: dict[str, list[RGBA]], *, shade: bool = True, outline: bool = True,
           flat: set[str] | None = None, outline_color: RGBA | None = None) -> Image.Image:
    """Symbols → RGBA. Each ramp is dark→light (index 1 shadow, 2 base, 3 light). Symbols in
    ``flat`` (eyes, glints) are drawn with their base colour only."""
    flat = flat or set()
    img = Image.new("RGBA", (grid.w, grid.h), (0, 0, 0, 0))
    px = img.load()
    for y in range(grid.h):
        for x in range(grid.w):
            sym = grid.cells[y][x]
            if sym == EMPTY or sym not in ramps:
                continue
            r = ramps[sym]
            idx = min(2, len(r) - 1)
            if shade and sym not in flat and len(r) >= 3:
                lit = grid.get(x, y - 1) != sym or grid.get(x - 1, y) != sym
                dark = grid.get(x, y + 1) != sym or grid.get(x + 1, y) != sym
                if dark and not lit:
                    idx = 1
                elif lit and not dark:
                    idx = 3 if len(r) > 3 else 2
                if grid.get(x, y + 1) == EMPTY and grid.get(x + 1, y) == EMPTY:
                    idx = 0
            px[x, y] = r[idx]
    if outline:
        _outline(img, grid, ramps, outline_color)
    return img


def _outline(img: Image.Image, grid: Grid, ramps: dict[str, list[RGBA]], color: RGBA | None) -> None:
    px = img.load()
    src = img.copy().load()
    for y in range(grid.h):
        for x in range(grid.w):
            if src[x, y][3]:
                continue
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < grid.w and 0 <= ny < grid.h and src[nx, ny][3]:
                    sym = grid.cells[ny][nx]
                    base = ramps.get(sym, [src[nx, ny]] * 3)
                    px[x, y] = color or outline_for(base[min(2, len(base) - 1)])
                    break


def upscale(img: Image.Image, factor: int) -> Image.Image:
    return img.resize((img.width * factor, img.height * factor), Image.NEAREST)
