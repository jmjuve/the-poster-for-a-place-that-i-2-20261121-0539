#!/usr/bin/env python3
"""VELMORA — a travel poster for a place that isn't there.

Draws a 1024x1024 travel poster for VELMORA, the Floating Isles:
islands that drift above a sea of clouds at golden hour, crowned by
one crystal spire. Pure standard library, no network, deterministic:
two runs write byte-identical PNGs.

Writes $MAKEFUN_OUTPUT_DIR/entry.png when the variable is set, with
the repo's out/ directory only as a local fallback.
"""

import math
import os
import struct
import zlib

W = 1024
H = 1024

# ---------------------------------------------------------------- palette
INK_DEEP = (24, 30, 66)        # night indigo, top of sky
INK_VIOLET = (86, 60, 118)     # mid sky
INK_DUSK = (206, 116, 78)      # low sky
INK_AMBER = (246, 172, 92)     # horizon glow
SUN = (255, 208, 112)          # low sun
SUN_CORE = (255, 232, 170)
CLOUD_CREAM = (255, 240, 214)
CLOUD_PINK = (250, 205, 170)
CLOUD_SHADOW = (232, 178, 150)
CLOUD_DEEP = (214, 150, 128)
ISLE_GREEN = (96, 148, 92)
ISLE_GREEN_DARK = (62, 108, 66)
ISLE_ROCK = (122, 82, 62)
ISLE_ROCK_DARK = (88, 58, 46)
ISLE_ROCK_LIGHT = (150, 106, 80)
SPIRE = (190, 228, 240)
SPIRE_LIGHT = (228, 248, 252)
SPIRE_GLOW = (150, 215, 235)
WATER = (196, 226, 238)
WATER_DARK = (150, 196, 216)
CREAM = (255, 244, 222)        # poster type
TYPE_SHADOW = (46, 30, 60)
BIRD = (52, 36, 58)

# ---------------------------------------------------------------- canvas
class Canvas:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.px = bytearray(w * h * 3)

    def set(self, x, y, color, alpha=1.0):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            if alpha >= 1.0:
                self.px[i] = color[0]
                self.px[i + 1] = color[1]
                self.px[i + 2] = color[2]
            else:
                a = alpha
                self.px[i] = int(self.px[i] * (1 - a) + color[0] * a)
                self.px[i + 1] = int(self.px[i + 1] * (1 - a) + color[1] * a)
                self.px[i + 2] = int(self.px[i + 2] * (1 - a) + color[2] * a)

    def hline(self, x0, x1, y, color):
        if y < 0 or y >= self.h:
            return
        x0 = max(0, x0)
        x1 = min(self.w - 1, x1)
        for x in range(x0, x1 + 1):
            i = (y * self.w + x) * 3
            self.px[i] = color[0]
            self.px[i + 1] = color[1]
            self.px[i + 2] = color[2]

    def fill_circle(self, cx, cy, r, color, alpha=1.0):
        r2 = r * r
        for y in range(int(cy - r), int(cy + r) + 1):
            dy = y - cy
            dx = int(math.sqrt(max(0, r2 - dy * dy)))
            for x in range(int(cx - dx), int(cx + dx) + 1):
                self.set(x, y, color, alpha)

    def fill_ellipse(self, cx, cy, rx, ry, color, alpha=1.0):
        for y in range(int(cy - ry), int(cy + ry) + 1):
            dy = (y - cy) / max(1, ry)
            if abs(dy) >= 1:
                continue
            dx = int(rx * math.sqrt(1 - dy * dy))
            for x in range(int(cx - dx), int(cx + dx) + 1):
                self.set(x, y, color, alpha)

    def fill_polygon(self, pts, color, alpha=1.0):
        if len(pts) < 3:
            return
        ymin = max(0, int(min(p[1] for p in pts)))
        ymax = min(self.h - 1, int(max(p[1] for p in pts)))
        n = len(pts)
        for y in range(ymin, ymax + 1):
            xs = []
            for i in range(n):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % n]
                if (y0 <= y < y1) or (y1 <= y < y0):
                    t = (y - y0) / (y1 - y0)
                    xs.append(x0 + t * (x1 - x0))
            xs.sort()
            for j in range(0, len(xs) - 1, 2):
                self.hline(int(xs[j]), int(xs[j + 1]), y, color) \
                    if alpha >= 1.0 else self._hline_alpha(
                        int(xs[j]), int(xs[j + 1]), y, color, alpha)

    def _hline_alpha(self, x0, x1, y, color, alpha):
        for x in range(max(0, x0), min(self.w - 1, x1) + 1):
            self.set(x, y, color, alpha)

    def thick_line(self, x0, y0, x1, y1, width, color):
        dx = x1 - x0
        dy = y1 - y0
        dist = math.hypot(dx, dy)
        steps = max(1, int(dist * 2))
        r = max(1.0, width / 2.0)
        for s in range(steps + 1):
            t = s / steps
            self.fill_circle(x0 + dx * t, y0 + dy * t, r, color)

# ---------------------------------------------------------------- helpers
def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def lcg(seed):
    """Deterministic pseudo-random stream (fixed seed, no time, no os)."""
    state = seed & 0x7FFFFFFF
    while True:
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        yield state / 0x7FFFFFFF


# ---------------------------------------------------------------- stroke font
# Single-stroke capitals on a 5 x 7 grid (x 0..4, y 0..6). Letters needed:
# VELMORA + WHERE ISLANDS FLOAT ABOVE A SEA OF CLOUDS.
FONT = {
    "A": [[(0, 6), (2, 0), (4, 6)], [(1, 4), (3, 4)]],
    "B": [[(0, 0), (0, 6)], [(0, 0), (2.5, 0), (3.5, 1), (3.5, 2.5), (0, 3)],
          [(0, 3), (2.5, 3), (3.5, 4), (3.5, 5), (0, 6)]],
    "C": [[(4, 1), (3, 0), (1, 0), (0, 1), (0, 5), (1, 6), (3, 6), (4, 5)]],
    "D": [[(0, 0), (0, 6)], [(0, 0), (3, 0), (4, 1), (4, 5), (3, 6), (0, 6)]],
    "E": [[(0, 0), (0, 6)], [(0, 0), (4, 0)], [(0, 3), (3, 3)], [(0, 6), (4, 6)]],
    "F": [[(0, 0), (0, 6)], [(0, 0), (4, 0)], [(0, 3), (3, 3)]],
    "H": [[(0, 0), (0, 6)], [(4, 0), (4, 6)], [(0, 3), (4, 3)]],
    "I": [[(0, 0), (4, 0)], [(2, 0), (2, 6)], [(0, 6), (4, 6)]],
    "L": [[(0, 0), (0, 6)], [(0, 6), (4, 6)]],
    "M": [[(0, 6), (0, 0), (2, 3), (4, 0), (4, 6)]],
    "N": [[(0, 6), (0, 0), (4, 6), (4, 0)]],
    "O": [[(1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0)]],
    "R": [[(0, 0), (0, 6)], [(0, 0), (3, 0), (4, 1), (4, 2), (3, 3), (0, 3)],
          [(2, 3), (4, 6)]],
    "S": [[(4, 1), (3, 0), (1, 0), (0, 1), (0, 2), (1, 3), (3, 3),
           (4, 4), (4, 5), (3, 6), (1, 6), (0, 5)]],
    "T": [[(0, 0), (4, 0)], [(2, 0), (2, 6)]],
    "U": [[(0, 0), (0, 5), (1, 6), (3, 6), (4, 5), (4, 0)]],
    "V": [[(0, 0), (2, 6), (4, 0)]],
    "W": [[(0, 0), (1, 6), (2, 3), (3, 6), (4, 0)]],
}


def text_width(text, unit):
    adv = 6.0 * unit
    return len(text) * adv - unit


def draw_text(cv, text, cx, top, unit, width, color):
    """Draw centred capitals; unit = pixels per grid cell."""
    total = text_width(text, unit)
    x = cx - total / 2.0
    for ch in text:
        if ch == " ":
            x += 6.0 * unit
            continue
        glyph = FONT.get(ch)
        if glyph is None:
            x += 6.0 * unit
            continue
        for stroke in glyph:
            for (ax, ay), (bx, by) in zip(stroke, stroke[1:]):
                cv.thick_line(x + ax * unit, top + ay * unit,
                              x + bx * unit, top + by * unit,
                              width, color)
        x += 6.0 * unit


# ---------------------------------------------------------------- scene
def draw_sky(cv):
    stops = [(0.0, INK_DEEP), (0.42, INK_VIOLET), (0.72, INK_DUSK),
             (1.0, INK_AMBER)]
    horizon = 660
    for y in range(horizon):
        t = y / horizon
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1:
                f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
                cv.hline(0, W - 1, y, lerp(c0, c1, f))
                break


def draw_stars(cv):
    rnd = lcg(20261121)
    for _ in range(70):
        x = int(next(rnd) * W)
        y = int(next(rnd) * 300)
        r = 1 if next(rnd) < 0.7 else 2
        a = 0.35 + 0.5 * next(rnd)
        cv.fill_circle(x, y, r, (255, 244, 220), a)


def draw_sun(cv):
    cx, cy, r = 852, 412, 66
    for i, (rr, a) in enumerate([(132, 0.10), (110, 0.14), (90, 0.20)]):
        cv.fill_circle(cx, cy, rr, SUN, a)
    cv.fill_circle(cx, cy, r, SUN)
    cv.fill_circle(cx, cy, r - 16, SUN_CORE)


def draw_cloud_sea(cv):
    # Base: warm cream filling the bottom of the frame.
    for y in range(640, H):
        t = (y - 640) / (H - 640)
        cv.hline(0, W - 1, y, lerp(CLOUD_CREAM, CLOUD_PINK, t * 0.7))
    # Layered cloud banks, back to front.
    rnd = lcg(777)
    bands = [
        (660, 760, 150, 34, CLOUD_PINK, 0.85),
        (720, 830, 170, 40, CLOUD_CREAM, 0.95),
        (800, 920, 190, 46, CLOUD_SHADOW, 0.55),
        (880, 1024, 210, 52, CLOUD_DEEP, 0.45),
    ]
    for (y0, y1, rx, ry, col, a) in bands:
        for _ in range(26):
            x = int(next(rnd) * (W + 240)) - 120
            y = y0 + int(next(rnd) * (y1 - y0))
            cv.fill_ellipse(x, y, rx * (0.7 + 0.6 * next(rnd)),
                            ry * (0.7 + 0.6 * next(rnd)), col, a)


def draw_waterfall(cv, x, y_top, y_bot, w_top, w_bot):
    """A pale stream pouring off an island edge into the clouds."""
    pts = [(x - w_top, y_top), (x + w_top, y_top),
           (x + w_bot, y_bot), (x - w_bot, y_bot)]
    cv.fill_polygon(pts, WATER, 0.95)
    cv.fill_polygon([(x - w_top * 0.35, y_top), (x + w_top * 0.15, y_top),
                     (x + w_bot * 0.2, y_bot), (x - w_bot * 0.3, y_bot)],
                    (240, 248, 252), 0.9)
    cv.fill_polygon([(x + w_top * 0.45, y_top), (x + w_top * 0.8, y_top),
                     (x + w_bot * 0.75, y_bot), (x + w_bot * 0.4, y_bot)],
                    WATER_DARK, 0.8)


def draw_island(cv, cx, top_y, half_w, top_h, rock_depth, scale=1.0):
    """Floating island: green tabletop, tapering rocky underside."""
    # Rocky underside: tapering cone with a slight curve.
    tip_y = top_y + rock_depth
    cv.fill_polygon([
        (cx - half_w, top_y),
        (cx + half_w, top_y),
        (cx + half_w * 0.55, top_y + rock_depth * 0.55),
        (cx, tip_y),
        (cx - half_w * 0.55, top_y + rock_depth * 0.55),
    ], ISLE_ROCK)
    # Strata lines on the rock.
    for f, col in [(0.25, ISLE_ROCK_LIGHT), (0.5, ISLE_ROCK_DARK),
                   (0.72, ISLE_ROCK_LIGHT)]:
        y = top_y + rock_depth * f
        hw = half_w * (1 - f * 0.85)
        cv.thick_line(cx - hw, y, cx + hw, y, 3 * scale, col)
    # Green tabletop.
    cv.fill_ellipse(cx, top_y, half_w, top_h, ISLE_GREEN)
    cv.fill_ellipse(cx, top_y - top_h * 0.25, half_w * 0.82,
                    top_h * 0.7, ISLE_GREEN_DARK)
    return top_y


def draw_tree(cv, x, y, s):
    cv.thick_line(x, y, x, y - 34 * s, 7 * s, (90, 62, 44))
    cv.fill_circle(x - 12 * s, y - 44 * s, 20 * s, ISLE_GREEN_DARK)
    cv.fill_circle(x + 12 * s, y - 46 * s, 22 * s, ISLE_GREEN)
    cv.fill_circle(x, y - 60 * s, 22 * s, ISLE_GREEN)


def draw_spire(cv, cx, base_y, height):
    """The crystal spire: the poster's one landmark."""
    tip_y = base_y - height
    # Glow around the spire.
    cv.fill_ellipse(cx, base_y - height * 0.55, 46, height * 0.62,
                    SPIRE_GLOW, 0.16)
    # Crystal facets: a tall diamond with a bright left face.
    cv.fill_polygon([
        (cx, tip_y), (cx + 26, base_y - height * 0.45),
        (cx + 18, base_y), (cx - 18, base_y),
        (cx - 26, base_y - height * 0.45),
    ], SPIRE)
    cv.fill_polygon([
        (cx, tip_y), (cx - 26, base_y - height * 0.45),
        (cx - 18, base_y), (cx, base_y),
    ], SPIRE_LIGHT)
    cv.thick_line(cx, tip_y, cx, base_y, 3, (240, 250, 255))
    # Glowing tip.
    cv.fill_circle(cx, tip_y, 16, SPIRE_GLOW, 0.5)
    cv.fill_circle(cx, tip_y, 9, (255, 255, 255))


def draw_birds(cv):
    for (x, y, s) in [(300, 210, 9), (345, 185, 7), (820, 250, 8),
                      (860, 225, 6), (180, 300, 7)]:
        cv.thick_line(x - s, y, x, y + s * 0.6, 3, BIRD)
        cv.thick_line(x, y + s * 0.6, x + s, y, 3, BIRD)


def draw_poster(cv):
    draw_sky(cv)
    draw_stars(cv)
    draw_sun(cv)
    # Right island, small, with a waterfall (behind the main island).
    draw_island(cv, 858, 512, 96, 22, 110, 0.8)
    draw_waterfall(cv, 830, 560, 700, 9, 16)
    draw_tree(cv, 858, 508, 0.55)
    # Left island, small, with a lone tree.
    draw_island(cv, 168, 540, 108, 24, 120, 0.85)
    draw_tree(cv, 150, 536, 0.8)
    draw_waterfall(cv, 215, 590, 716, 7, 13)
    # Main island, centre, with the crystal spire.
    draw_island(cv, 512, 452, 268, 44, 250, 1.0)
    draw_tree(cv, 330, 448, 0.9)
    draw_tree(cv, 700, 446, 0.7)
    draw_spire(cv, 512, 448, 268)
    # Main waterfall pouring off the front edge into the clouds.
    draw_waterfall(cv, 470, 560, 730, 12, 22)
    draw_birds(cv)
    # Cloud sea washes over the island bases.
    draw_cloud_sea(cv)
    # Re-draw the sun's lower glow over the clouds for warmth.
    cv.fill_circle(852, 660, 120, SUN, 0.08)
    # Poster frame.
    for inset, wdt in [(26, 4), (34, 2)]:
        cv.thick_line(inset, inset, W - inset, inset, wdt, CREAM)
        cv.thick_line(W - inset, inset, W - inset, H - inset, wdt, CREAM)
        cv.thick_line(W - inset, H - inset, inset, H - inset, wdt, CREAM)
        cv.thick_line(inset, H - inset, inset, inset, wdt, CREAM)
    # Type: the place name, then one short tagline. Nothing else.
    # Deep indigo type on the pale cloud sea: high contrast, legible.
    draw_text(cv, "VELMORA", W // 2, 776, 15.5, 9, INK_DEEP)
    cv.thick_line(332, 898, 692, 898, 4, INK_AMBER)
    draw_text(cv, "WHERE ISLANDS FLOAT ABOVE A SEA OF CLOUDS",
              W // 2, 912, 3.4, 2, INK_DEEP)


# ---------------------------------------------------------------- png
def chunk(typ, data):
    out = struct.pack(">I", len(data)) + typ + data
    out += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
    return out


def write_png(cv, path):
    raw = bytearray()
    stride = W * 3
    for y in range(H):
        raw.append(0)  # filter: none
        raw += cv.px[y * stride:(y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR")
    if not out_dir:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "out")
    os.makedirs(out_dir, exist_ok=True)
    cv = Canvas(W, H)
    draw_poster(cv)
    path = os.path.join(out_dir, "entry.png")
    size = write_png(cv, path)
    print(f"wrote {path} ({size} bytes)")


if __name__ == "__main__":
    main()
