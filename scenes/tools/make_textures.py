#!/usr/bin/env python3
"""Generates the PPM textures used by the scenes (standard library only)."""
import math
import os
import sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "textures")


def write_ppm(name, w, h, fn):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    data = bytearray()
    for y in range(h):
        for x in range(w):
            r, g, b = fn(x, y)
            data += bytes((max(0, min(255, int(r))), max(0, min(255, int(g))), max(0, min(255, int(b)))))
    with open(path, "wb") as f:
        f.write(b"P6\n%d %d\n255\n" % (w, h))
        f.write(data)
    print("wrote", path)


def checker(x, y):
    c = ((x // 32) + (y // 32)) % 2
    return (230, 230, 230) if c == 0 else (40, 40, 40)


def uvgrid(x, y):
    # u increases to the right (red), v increases upwards (green): row 0 is the top (v = 1).
    w = h = 256
    u = x / (w - 1)
    v = 1 - y / (h - 1)
    line = (x % 32 == 0) or (y % 32 == 0)
    if line:
        return (255, 255, 255)
    return (255 * u, 255 * v, 60)


def bricks(x, y):
    bw, bh, mortar = 64, 32, 3
    row = y // bh
    xo = (x + (bw // 2 if row % 2 else 0)) % bw
    yo = y % bh
    if xo < mortar or yo < mortar:
        return (200, 195, 185)
    # deterministic per-brick tint
    bid = (row * 7 + (x + (bw // 2 if row % 2 else 0)) // bw * 13) % 5
    base = [(150, 60, 45), (165, 70, 50), (140, 55, 40), (170, 80, 55), (155, 65, 48)][bid]
    n = 10 * math.sin(x * 0.7) * math.cos(y * 0.9)
    return (base[0] + n, base[1] + n, base[2] + n)


def wood(x, y):
    cx, cy = 128, -200
    r = math.hypot(x - cx, y - cy) + 6 * math.sin(x * 0.05)
    ring = 0.5 + 0.5 * math.sin(r * 0.35)
    return (120 + 60 * ring, 75 + 40 * ring, 40 + 20 * ring)


def stripes(x, y):
    # fine diagonal stripes: a good aliasing / moire stress test
    return (240, 240, 240) if ((x + y) // 4) % 2 == 0 else (20, 20, 20)


if __name__ == "__main__":
    write_ppm("checker.ppm", 256, 256, checker)
    write_ppm("uvgrid.ppm", 256, 256, uvgrid)
    write_ppm("bricks.ppm", 256, 256, bricks)
    write_ppm("wood.ppm", 256, 256, wood)
    write_ppm("stripes.ppm", 256, 256, stripes)
    sys.exit(0)
