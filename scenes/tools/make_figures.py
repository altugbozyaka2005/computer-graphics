#!/usr/bin/env python3
"""Report figures for the Module 1 images (Python 3 standard library only).

For each rendered image (output/<name>.png) this writes, into output/figures/:
  <name>_annotated.png  numbered callouts with arrows and frames around the zoomed regions
  <name>_insets.png     the framed regions enlarged, each with its number
  <name>_legend.txt     number -> feature, as a starting point for the captions
plus
  compare_wsrt_drt.png  the same regions of WSRT_creative and DRT_creative side by side
  <DRT>_tonemap.png     DRT_simple / DRT_creative with four tone mappings recomputed from the
                        linear HDR output (<DRT>.pfm): clamp, Reinhard on luminance (as rendered),
                        Reinhard per channel, Reinhard with another white point; plus enlarged regions
  photo_vs_render.png   (with --photo PATH.png) photograph | WSRT_creative | DRT_creative

Callouts are placed by projecting each feature's 3D position with the same camera
model as the renderer (pbrt LookAt, fov on the shorter image axis), so they stay on
target if the images are re-rendered at another resolution.

Usage: python3 scenes/tools/make_figures.py [--outdir output] [--photo photo.png]
  (a JPEG photo can be converted first: sips -s format png --resampleHeightWidthMax 1600 photo.jpg --out photo.png;
   the EXIF orientation that phones store is applied, so the photo appears upright as in a photo viewer)
"""
import array
import math
import os
import re
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from make_poolroom import _glyphs, BALLS, GLASS_POS, PERFUME_POS, GRATER_POS, CUE_TIP, CUE_BUTT  # noqa: E402

# ---------------------------------------------------------------- cameras (as in the scene files)
CAMERAS = {
    "WSRT_creative": ((0, 9.2, 0), (0, 6.027, 9.4832), (0, 1, 0), 46.2),
    "DRT_creative": ((0, 9.2, 0), (0, 6.027, 9.4832), (0, 1, 0), 46.2),
    "WSRT_simple": ((0, 2.6, -7.5), (0, 1, 0), (0, 1, 0), 40.0),
    "DRT_simple": ((0, 2, -7.5), (0, 1.4, 0), (0, 1, 0), 42.0),
}


def _sub(a, b): return [a[i] - b[i] for i in range(3)]
def _dot(a, b): return sum(a[i] * b[i] for i in range(3))
def _cross(a, b): return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
def _norm(a):
    L = math.sqrt(_dot(a, a)); return [x / L for x in a]


def project(name, p, W, H):
    """World point -> raster (x, y), exactly like the renderer's perspective camera."""
    eye, look, up, fov = CAMERAS[name]
    d = _norm(_sub(look, eye))
    right = _norm(_cross(_norm(up), d))
    nup = _cross(d, right)
    v = _sub(p, eye)
    xc, yc, zc = _dot(v, right), _dot(v, nup), _dot(v, d)
    t = math.tan(math.radians(fov) / 2)
    sx, sy = xc / (zc * t), yc / (zc * t)
    a = W / H
    x0, x1, y0, y1 = (-a, a, -1, 1) if a > 1 else (-1, 1, -1 / a, 1 / a)
    return (sx - x0) / (x1 - x0) * W, (y1 - sy) / (y1 - y0) * H


# ---------------------------------------------------------------- features to point out
def _ball(tex):
    for x, z, t in BALLS:
        if t == tex:
            return (x, 1.0, z)
    raise KeyError(tex)


def _cue_point(t):
    return (CUE_TIP[0] + (CUE_BUTT[0] - CUE_TIP[0]) * t, 0.3, CUE_TIP[1] + (CUE_BUTT[1] - CUE_TIP[1]) * t)


# (label, 3D anchor, region half-size as a fraction of the image width, badge direction (dx, dy))
FEATURES = {
    "WSRT_creative": [
        ("Mirror reflection (recursive): steel grater", (GRATER_POS[0] + 0.4, 4.6, GRATER_POS[1] - 1.3), 0.07, (1, -1)),
        ("Refraction, Fresnel and total internal reflection: water glass (balls behind are swapped)",
         (GLASS_POS[0], 3.0, GLASS_POS[1] - 1.6), 0.09, (1, -1)),
        ("Refraction through faceted crystal (cap)", (PERFUME_POS[0], 3.3, PERFUME_POS[1] - 1.4), 0.06, (-1, -1)),
        ("Coloured transparent shadow (amber bottle, filtered shadow rays)", (-4.3, 0.0, 15.6), 0.07, (-1, 1)),
        ("Light through the grater holes: dots of light in its shadow (alpha cut-outs)", (-9.0, 0.0, 23.0), 0.06, (1, 1)),
        ("Hard shadows from two point lights: cool key (towards camera) and warm fill (to the left)",
         (5.6, 0.0, 19.9), 0.07, (1, 1)),
        ("Blinn-Phong: ambient, diffuse and a small specular highlight", (-1.82, 1.55, 23.19 - 0.6), 0.045, (-1, 1)),
        ("UV texture on a sphere (numbered ball)", (5.19, 1.0, 26.07 - 1.0), 0.045, (1, -1)),
        ("Textures on triangles: felt weave and speckled rail (+ white strip)", (0.64, 1.5, 10.0), 0.06, (-1, -1)),
        ("Triangles + object instancing: rack built from one bar", (-4.52, 0.5, 43.57), 0.06, (1, -1)),
    ],
    "DRT_creative": [
        ("Soft shadows (penumbra) from the area key light", (5.6, 0.0, 19.9), 0.07, (1, 1)),
        ("Phong BRDF: glossy highlight and clear-coat reflection", (5.19, 1.6, 26.07 - 0.8), 0.045, (1, -1)),
        ("OBJ meshes with vertex normals: smooth refraction through the glass", (GLASS_POS[0], 3.0, GLASS_POS[1] - 1.6),
         0.09, (-1, -1)),
        ("Texture on a mesh through its UVs: cue wood", _cue_point(0.1), 0.035, (1, -1)),
        ("Depth of field: background out of focus (thin lens): wall lamp bokeh", (30.0, 22.0, 469.8), 0.06, (-1, 1)),
        ("Depth of field: near rail out of focus", (3.11, 1.5, 12.03), 0.07, (1, 1)),
        ("Filtered (transparent) shadow of the glass: dark walls, light passing through the middle",
         (0.9, 0.0, 18.7), 0.1, (-1, 1)),
        ("Reinhard tone mapping: the brightest felt keeps its gradation instead of clipping "
         "(see DRT_creative_tonemap.png)", (-10.52, 0.0, 59.31), 0.04, (1, -1)),
    ],
    "WSRT_simple": [
        ("Recursive mirror reflection (sphere)", (-1.7, 1.0, 0.8), 0.08, (1, -1)),
        ("Refraction + Fresnel + total internal reflection (glass sphere)", (0.3, 0.95, -1.6), 0.07, (1, 1)),
        ("Blinn-Phong highlight (red sphere)", (2.1, 0.95, 0.2 - 0.5), 0.06, (1, -1)),
        ("UV texture on a sphere", (0.6, 1.574, 1.781), 0.06, (1, -1)),
        ("UV texture on a plane (checker floor) + hard shadow of the glass sphere", (-0.6, 0.0, -1.2), 0.06, (-1, 1)),
        ("UV texture on triangles (brick wall)", (3.5, 3.5, 5.0), 0.07, (1, -1)),
        ("Single triangle primitive", (-3.35, 1.85, 2.8), 0.045, (-1, -1)),
    ],
    "DRT_simple": [
        ("OBJ triangle mesh: smooth normals + UV wood texture (torus)", (-1.5, 1.4, 0.65), 0.045, (-1, -1)),
        ("Area light (emissive rectangle)", (0.7, 3.98, 1.2), 0.05, (1, 1)),
        ("Soft shadow (penumbra) of the torus", (-1.7, 0.0, 0.5), 0.05, (-1, 1)),
        ("Energy-conserving Phong BRDF (glossy sphere)", (1.25, 0.92, 0.85), 0.08, (1, -1)),
        ("Depth of field: foreground glass sphere out of focus", (0.45, 0.45, -2.4), 0.08, (-1, 1)),
        ("Reinhard tone mapping: the highlight rolls off into white (see DRT_simple_tonemap.png)",
         (-0.95, 0.72, 0.3), 0.035, (1, 1)),
    ],
}

# Regions for the WSRT vs DRT comparison (same camera): (label, anchor, half-size fraction)
COMPARE = [
    ("Hard vs soft shadows", (5.6, 0.0, 19.9), 0.08),
    ("Glass: Whitted ray tree vs distributed paths", (GLASS_POS[0], 2.4, GLASS_POS[1] - 1.6), 0.09),
    ("Bottle shadow and crystal cap", (-4.0, 1.5, 17.0), 0.09),
    ("Pinhole vs thin lens: background", (30.0, 22.0, 469.8), 0.09),
]


# Tone mappings for <DRT>_tonemap.png, applied to the linear HDR output with the renderer's operator
# (source/core/image.cpp): (label, op, mode, white point: None = the scene's, 0 = maximum luminance,
# which is what the renderer uses when the scene gives no white point)
TONEMAP_VARIANTS = [
    ("No tone mapping: linear radiance x exposure, clamped to [0, 1]", "none", "luminance", None),
    ("Reinhard on luminance with the scene's white point (the rendered image)", "reinhard", "luminance", None),
    ("Reinhard per channel (rgb) with the same white point", "reinhard", "rgb", None),
    ("Reinhard on luminance with white point = maximum luminance", "reinhard", "luminance", 0.0),
]
# Regions enlarged under the four panels: (label, anchor, half-size fraction)
TONEMAP_REGIONS = {
    "DRT_simple": [
        ("Highlight on the glossy sphere", (1.25, 1.2, 0.3), 0.05),
        ("Torus: highlight and wood texture", (-0.95, 0.75, 0.25), 0.05),
    ],
    "DRT_creative": [
        ("Brightest felt, under the key light (callout 8)", (-10.52, 0.0, 59.31), 0.05),
        ("White strip on the near rail", (0.5, 0.0, 12.15), 0.06),
    ],
}


# ---------------------------------------------------------------- PNG I/O
def load_png(path):
    data = open(path, "rb").read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(path + ": not a PNG file")
    pos, idat, orientation = 8, b"", 1
    while pos < len(data):
        (n,) = struct.unpack(">I", data[pos:pos + 4])
        t, c = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if t == b"eXIf":
            orientation = _exif_orientation(c)
        elif t == b"IHDR":
            w, h, depth, color, _, _, il = struct.unpack(">IIBBBBB", c)
            if depth != 8 or color not in (2, 6) or il:
                raise ValueError(path + ": only 8-bit RGB/RGBA non-interlaced PNGs are supported")
            bpp = 3 if color == 2 else 4
        elif t == b"IDAT":
            idat += c
    raw = zlib.decompress(idat)
    stride, prev, out, p = w * bpp, bytearray(w * bpp), bytearray(), 0
    for _ in range(h):
        ft, line = raw[p], bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        if ft:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b, cc = prev[i], (prev[i - bpp] if i >= bpp else 0)
                if ft == 1: line[i] = (line[i] + a) & 255
                elif ft == 2: line[i] = (line[i] + b) & 255
                elif ft == 3: line[i] = (line[i] + (a + b) // 2) & 255
                else:
                    pa, pb, pc = abs(b - cc), abs(a - cc), abs(a + b - 2 * cc)
                    line[i] = (line[i] + (a if pa <= pb and pa <= pc else (b if pb <= pc else cc))) & 255
        out += line if bpp == 3 else bytes(v for k, v in enumerate(line) if k % 4 != 3)
        prev = line
    return _orient([w, h, out], orientation)


def _exif_orientation(exif):
    """Orientation tag (0x0112) of a PNG eXIf chunk (TIFF header + IFD0); 1 when absent."""
    try:
        fmt = "<" if exif[:2] == b"II" else ">"
        (off,) = struct.unpack(fmt + "I", exif[4:8])
        (count,) = struct.unpack(fmt + "H", exif[off:off + 2])
        for k in range(count):
            e = off + 2 + 12 * k
            tag, _, _ = struct.unpack(fmt + "HHI", exif[e:e + 8])
            if tag == 0x0112:
                return struct.unpack(fmt + "H", exif[e + 8:e + 10])[0]
    except struct.error:
        pass
    return 1


def _orient(img, o):
    """Applies an EXIF orientation, as photo viewers do (phone photos are often stored sideways)."""
    if o not in (2, 3, 4, 5, 6, 7, 8):
        return img
    w, h, d = img
    W2, H2 = (h, w) if o >= 5 else (w, h)
    src = {2: lambda X, Y: (w - 1 - X, Y), 3: lambda X, Y: (w - 1 - X, h - 1 - Y), 4: lambda X, Y: (X, h - 1 - Y),
           5: lambda X, Y: (Y, X), 6: lambda X, Y: (Y, h - 1 - X), 7: lambda X, Y: (w - 1 - Y, h - 1 - X),
           8: lambda X, Y: (w - 1 - Y, X)}[o]
    out = bytearray(W2 * H2 * 3)
    for Y in range(H2):
        for X in range(W2):
            x, y = src(X, Y)
            i, j = (Y * W2 + X) * 3, (y * w + x) * 3
            out[i:i + 3] = d[j:j + 3]
    return [W2, H2, out]


def load_pfm(path):
    """Colour PFM -> [w, h, floats] with rows top to bottom (a PFM stores the bottom row first)."""
    data = open(path, "rb").read()
    tokens, pos = [], 0
    while len(tokens) < 4:  # "PF", width, height, scale (negative = little endian)
        while data[pos:pos + 1].isspace():
            pos += 1
        start = pos
        while pos < len(data) and not data[pos:pos + 1].isspace():
            pos += 1
        tokens.append(data[start:pos].decode("ascii"))
    pos += 1
    if tokens[0] != "PF":
        raise ValueError(path + ": only colour (PF) PFM files are supported")
    w, h, endian = int(tokens[1]), int(tokens[2]), float(tokens[3])
    rows = array.array("f")
    rows.frombytes(data[pos:pos + w * h * 12])
    if (endian < 0) != (sys.byteorder == "little"):
        rows.byteswap()
    px = array.array("f")
    for y in range(h - 1, -1, -1):
        px.extend(rows[y * w * 3:(y + 1) * w * 3])
    return [w, h, px]


def save_png(path, img):
    w, h, d = img
    raw = b"".join(b"\x00" + bytes(d[y * w * 3:(y + 1) * w * 3]) for y in range(h))
    def chunk(t, b): return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xffffffff)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
                chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def new_image(w, h, col=(255, 255, 255)):
    return [w, h, bytearray(bytes(col) * (w * h))]


# ---------------------------------------------------------------- drawing (anti-aliased by coverage)
def _blend(img, x, y, col, a):
    w, h, d = img
    if 0 <= x < w and 0 <= y < h and a > 0:
        i = (y * w + x) * 3
        a = min(1.0, a)
        for k in range(3):
            d[i + k] = int(d[i + k] * (1 - a) + col[k] * a + 0.5)


def _seg_dist(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / L2))
    return math.hypot(px - ax - t * vx, py - ay - t * vy)


def draw_line(img, ax, ay, bx, by, col, width):
    r = width / 2
    for y in range(int(min(ay, by) - r - 1), int(max(ay, by) + r + 2)):
        for x in range(int(min(ax, bx) - r - 1), int(max(ax, bx) + r + 2)):
            _blend(img, x, y, col, r + 0.5 - _seg_dist(x + 0.5, y + 0.5, ax, ay, bx, by))


def draw_disc(img, cx, cy, rad, col):
    for y in range(int(cy - rad - 1), int(cy + rad + 2)):
        for x in range(int(cx - rad - 1), int(cx + rad + 2)):
            _blend(img, x, y, col, rad + 0.5 - math.hypot(x + 0.5 - cx, y + 0.5 - cy))


def draw_rect(img, x0, y0, x1, y1, col, width):
    for (a, b, c, d) in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
        draw_line(img, a, b, c, d, col, width)


def draw_arrow(img, ax, ay, bx, by, col, width):
    """Line from (ax, ay) to (bx, by) with an arrowhead at (bx, by)."""
    L = math.hypot(bx - ax, by - ay) or 1
    ux, uy = (bx - ax) / L, (by - ay) / L
    hl = 4.5 * width
    draw_line(img, ax, ay, bx - ux * hl * 0.8, by - uy * hl * 0.8, col, width)
    for s in (1, -1):
        draw_line(img, bx, by, bx - ux * hl - s * uy * hl * 0.55, by - uy * hl + s * ux * hl * 0.55, col, width)


def draw_number(img, cx, cy, height, text, col):
    g = _glyphs()
    em_w, gap = 0.62 * height, 0.12 * height
    total = len(text) * em_w + (len(text) - 1) * gap
    lw = 0.17 * height
    for k, ch in enumerate(text):
        x0 = cx - total / 2 + k * (em_w + gap)
        for line in g[ch]:
            pts = [(x0 + x * height, cy + (0.5 - y) * height) for (x, y) in line]
            for i in range(len(pts) - 1):
                draw_line(img, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], col, lw)


def badge(img, cx, cy, rad, n):
    draw_disc(img, cx, cy, rad + 2.5, (0, 0, 0))
    draw_disc(img, cx, cy, rad, (255, 214, 0))
    draw_number(img, cx, cy, rad * 1.05, str(n), (0, 0, 0))


def crop_scaled(img, x0, y0, x1, y1, scale):
    """Region [x0,x1) x [y0,y1) enlarged by an integer factor (nearest neighbour keeps pixels honest)."""
    w, h, d = img
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    cw, ch = x1 - x0, y1 - y0
    out = new_image(cw * scale, ch * scale)
    od = out[2]
    for y in range(ch * scale):
        sy = y0 + y // scale
        for x in range(cw * scale):
            si = (sy * w + x0 + x // scale) * 3
            oi = (y * cw * scale + x) * 3
            od[oi:oi + 3] = d[si:si + 3]
    return out


def paste(dst, src, ox, oy):
    dw, dh, dd = dst
    sw, sh, sd = src
    for y in range(sh):
        if 0 <= oy + y < dh:
            for x in range(sw):
                if 0 <= ox + x < dw:
                    di, si = ((oy + y) * dw + ox + x) * 3, (y * sw + x) * 3
                    dd[di:di + 3] = sd[si:si + 3]


def resize_box(img, W2, H2):
    """Area-average downscale (for the photo and side-by-side panels)."""
    w, h, d = img
    out = new_image(W2, H2)
    od = out[2]
    for y in range(H2):
        ya, yb = int(y * h / H2), max(int(y * h / H2) + 1, int((y + 1) * h / H2))
        for x in range(W2):
            xa, xb = int(x * w / W2), max(int(x * w / W2) + 1, int((x + 1) * w / W2))
            acc, n = [0, 0, 0], 0
            for yy in range(ya, yb):
                row = yy * w
                for xx in range(xa, xb):
                    i = (row + xx) * 3
                    acc[0] += d[i]; acc[1] += d[i + 1]; acc[2] += d[i + 2]
                    n += 1
            oi = (y * W2 + x) * 3
            od[oi:oi + 3] = bytes(int(a / n + 0.5) for a in acc)
    return out


# ---------------------------------------------------------------- figures
def annotate(name, outdir, figdir):
    path = os.path.join(outdir, name + ".png")
    if not os.path.exists(path):
        print("skip %s: %s not rendered yet" % (name, path))
        return
    img = load_png(path)
    W, H = img[0], img[1]
    ann = [W, H, bytearray(img[2])]
    lw = max(2.0, W / 400)
    rad = max(14, W / 48)
    tiles, legend = [], []
    for n, (label, anchor, hs, (dx, dy)) in enumerate(FEATURES[name], 1):
        px, py = project(name, anchor, W, H)
        r = int(hs * W)
        x0, y0, x1, y1 = int(px - r), int(py - r), int(px + r), int(py + r)
        if x1 <= 0 or y1 <= 0 or x0 >= W or y0 >= H:
            print("  warning: %s callout %d (%s) is outside the image; skipped" % (name, n, label))
            continue
        # region frame (black outline under yellow)
        draw_rect(ann, x0, y0, x1, y1, (0, 0, 0), lw + 2)
        draw_rect(ann, x0, y0, x1, y1, (255, 214, 0), lw)
        # badge outside the frame, arrow to the frame corner nearest to it
        bx = min(W - rad - 4, max(rad + 4, px + dx * (r + 2.6 * rad)))
        by = min(H - rad - 4, max(rad + 4, py + dy * (r + 2.6 * rad)))
        cx = x0 if bx < px else x1
        cy = y0 if by < py else y1
        draw_arrow(ann, bx, by, cx, cy, (0, 0, 0), lw + 2)
        draw_arrow(ann, bx, by, cx, cy, (255, 214, 0), lw)
        badge(ann, bx, by, rad, n)
        tiles.append((n, crop_scaled(img, x0, y0, x1, y1, max(1, round(360 / (x1 - x0))))))
        legend.append("%d  %s" % (n, label))
    os.makedirs(figdir, exist_ok=True)
    save_png(os.path.join(figdir, name + "_annotated.png"), ann)
    # insets sheet: tiles in rows of 3, each with its number
    tw = max(t[1][0] for t in tiles)
    th = max(t[1][1] for t in tiles)
    cols = 3
    rows = (len(tiles) + cols - 1) // cols
    pad = 12
    sheet = new_image(cols * (tw + pad) + pad, rows * (th + pad) + pad, (255, 255, 255))
    for k, (n, tile) in enumerate(tiles):
        ox, oy = pad + (k % cols) * (tw + pad), pad + (k // cols) * (th + pad)
        paste(sheet, tile, ox, oy)
        draw_rect(sheet, ox, oy, ox + tile[0], oy + tile[1], (0, 0, 0), 2)
        badge(sheet, ox + rad + 6, oy + rad + 6, rad, n)
    save_png(os.path.join(figdir, name + "_insets.png"), sheet)
    with open(os.path.join(figdir, name + "_legend.txt"), "w") as f:
        f.write("%s: numbered regions in %s_annotated.png / %s_insets.png\n" % (name, name, name))
        f.write("\n".join(legend) + "\n")
    print("wrote figures for %s (%d callouts)" % (name, len(tiles)))


def compare(outdir, figdir):
    a, b = (os.path.join(outdir, s + ".png") for s in ("WSRT_creative", "DRT_creative"))
    if not (os.path.exists(a) and os.path.exists(b)):
        print("skip comparison: creative images not rendered yet")
        return
    A, B = load_png(a), load_png(b)
    W, H = A[0], A[1]
    tiles = []
    for label, anchor, hs in COMPARE:
        px, py = project("WSRT_creative", anchor, W, H)
        r = int(hs * W)
        box = (int(px - r), int(py - r), int(px + r), int(py + r))
        tiles.append((crop_scaled(A, *box, 1), crop_scaled(B, *box, 1)))
    tw, th, pad = max(t[0][0] for t in tiles), max(t[0][1] for t in tiles), 12
    sheet = new_image(2 * tw + 3 * pad, len(tiles) * (th + pad) + pad)
    rad = max(14, W / 48)
    for k, (ta, tb) in enumerate(tiles):
        oy = pad + k * (th + pad)
        for j, t in enumerate((ta, tb)):
            ox = pad + j * (tw + pad)
            paste(sheet, t, ox, oy)
            draw_rect(sheet, ox, oy, ox + t[0], oy + t[1], (0, 0, 0), 2)
        badge(sheet, pad + rad + 6, oy + rad + 6, rad, k + 1)
    save_png(os.path.join(figdir, "compare_wsrt_drt.png"), sheet)
    with open(os.path.join(figdir, "compare_wsrt_drt_legend.txt"), "w") as f:
        f.write("compare_wsrt_drt.png: left column WSRT_creative, right column DRT_creative\n")
        f.write("\n".join("%d  %s" % (k + 1, c[0]) for k, c in enumerate(COMPARE)) + "\n")
    print("wrote compare_wsrt_drt.png")


def _srgb8(v):
    """Linear [0, 1] -> 8-bit sRGB, as srgbEncode() and writePNG() in source/core/image.cpp."""
    v = 0.0 if v < 0 else (1.0 if v > 1 else v)
    e = 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
    return int((0.0 if e < 0 else (1.0 if e > 1 else e)) * 255.0 + 0.5)


def tonemap(hdr, op, mode, scale, white):
    """toneMapAndEncode() of source/core/image.cpp on a linear image. Returns the 8-bit image,
    the fraction of pixels with a channel at or above display white, and the white point used."""
    w, h, px = hdr
    n = w * h
    if white <= 0:
        white = scale * max(max(0.0, 0.2126 * px[i] + 0.7152 * px[i + 1] + 0.0722 * px[i + 2])
                            for i in range(0, 3 * n, 3))
        if white <= 0:
            white = 1.0
    inv_w2 = 1.0 / (white * white)
    out, clipped = bytearray(3 * n), 0
    for i in range(0, 3 * n, 3):
        r, g, b = max(0.0, px[i] * scale), max(0.0, px[i + 1] * scale), max(0.0, px[i + 2] * scale)
        if op == "reinhard":
            if mode == "rgb":
                r, g, b = (r * (1 + r * inv_w2) / (1 + r), g * (1 + g * inv_w2) / (1 + g),
                           b * (1 + b * inv_w2) / (1 + b))
            else:
                L = 0.2126 * r + 0.7152 * g + 0.0722 * b
                if L > 0:
                    k = (L * (1 + L * inv_w2) / (1 + L)) / L
                    r, g, b = r * k, g * k, b * k
                else:
                    r = g = b = 0.0
        if r >= 1 or g >= 1 or b >= 1:
            clipped += 1
        out[i], out[i + 1], out[i + 2] = _srgb8(r), _srgb8(g), _srgb8(b)
    return [w, h, out], clipped / n, white


def tonemap_figure(name, outdir, figdir):
    pfm, png, log = (os.path.join(outdir, name + ext) for ext in (".pfm", ".png", ".log"))
    if not all(os.path.exists(p) for p in (pfm, png, log)):
        print("skip %s_tonemap.png: %s not rendered yet" % (name, name))
        return
    m = re.search(r"Reinhard: mode (\w+), log-average luminance (\S+), max luminance (\S+), "
                  r"scale (\S+), white point (\S+)", open(log).read())
    if not m:
        print("skip %s_tonemap.png: %s has no Reinhard line" % (name, log))
        return
    mode, log_avg, max_lum = m.group(1), m.group(2).rstrip(","), m.group(3).rstrip(",")
    scale, white = float(m.group(4).rstrip(",")), float(m.group(5))
    hdr = load_pfm(pfm)
    W, H = hdr[0], hdr[1]
    imgs, notes = [], []
    for label, op, md, wp in TONEMAP_VARIANTS:
        img, clipped, used = tonemap(hdr, op, md, scale, white if wp is None else wp)
        imgs.append(img)
        wtxt = "" if op == "none" else ", white point %.3g" % used
        notes.append("%s (exposure %.3g%s): %.2f%% of pixels at white" % (label, scale, wtxt, 100 * clipped))
    # the variant with the scene's own settings must reproduce the rendered PNG
    k = next(i for i, v in enumerate(TONEMAP_VARIANTS) if v[1] == "reinhard" and v[2] == mode and v[3] is None)
    ref = load_png(png)
    worst = differing = 0
    for a, b in zip(ref[2], imgs[k][2]):
        if a != b:
            differing += 1
            worst = max(worst, abs(a - b))
    check = "panel %d recomputed from %s.pfm vs %s.png: max difference %d/255, %.4f%% of values differ" % (
        k + 1, name, name, worst, 100 * differing / len(ref[2]))
    if worst > 2:
        print("  warning: " + check)
    # sheet: the four versions at half size (2 x 2), then one row of enlarged regions per region
    pad, pw, ph = 12, W // 2, H // 2
    sheet_w = 2 * pw + 3 * pad
    cell = (sheet_w - 5 * pad) // 4
    rad, srad = max(14, pw / 30), max(10, cell / 16)
    rows = []
    for label, anchor, hs in TONEMAP_REGIONS.get(name, []):
        cx, cy = project(name, anchor, W, H)
        r = int(hs * W)
        box = (int(cx - r), int(cy - r), int(cx + r), int(cy + r))
        z = max(1, cell // (2 * r))
        crops = []
        for im in imgs:
            c = crop_scaled(im, *box, z)
            if c[0] > cell:
                c = resize_box(c, cell, max(1, c[1] * cell // c[0]))
            crops.append(c)
        rows.append((box, crops))
    sheet = new_image(sheet_w, 2 * ph + 3 * pad + sum(max(c[1] for c in cr) + pad for _, cr in rows))
    for i, im in enumerate(imgs):
        ox, oy = pad + (i % 2) * (pw + pad), pad + (i // 2) * (ph + pad)
        paste(sheet, resize_box(im, pw, ph), ox, oy)
        for (x0, y0, x1, y1), _ in rows:
            draw_rect(sheet, ox + x0 // 2, oy + y0 // 2, ox + x1 // 2, oy + y1 // 2, (255, 214, 0), 2)
        draw_rect(sheet, ox, oy, ox + pw, oy + ph, (0, 0, 0), 2)
        badge(sheet, ox + rad + 6, oy + rad + 6, rad, i + 1)
    oy = 2 * ph + 3 * pad
    for _, crops in rows:
        for j, c in enumerate(crops):
            ox = pad + j * (cell + pad)
            paste(sheet, c, ox, oy)
            draw_rect(sheet, ox, oy, ox + c[0], oy + c[1], (0, 0, 0), 2)
            badge(sheet, ox + srad + 5, oy + srad + 5, srad, j + 1)
        oy += max(c[1] for c in crops) + pad
    os.makedirs(figdir, exist_ok=True)
    save_png(os.path.join(figdir, name + "_tonemap.png"), sheet)
    with open(os.path.join(figdir, name + "_tonemap_legend.txt"), "w") as f:
        f.write("%s_tonemap.png: one HDR render (%s.pfm, max luminance %s, log-average %s) shown with four\n"
                "tone mappings; panels 1 2 (top) and 3 4 (bottom); the rows under them enlarge the framed\n"
                "regions with the same numbers\n" % (name, name, max_lum, log_avg))
        f.write("\n".join("%d  %s" % (i + 1, t) for i, t in enumerate(notes)) + "\n")
        f.write("regions, top to bottom: " + "; ".join(t[0] for t in TONEMAP_REGIONS.get(name, [])) + "\n")
        f.write("check: " + check + "\n")
    print("wrote %s_tonemap.png (%s)" % (name, check))


def photo_vs_render(photo, outdir, figdir):
    paths = [photo] + [os.path.join(outdir, s + ".png") for s in ("WSRT_creative", "DRT_creative")]
    if not all(os.path.exists(p) for p in paths):
        print("skip photo comparison: photo or creative images missing")
        return
    try:
        panels = [load_png(p) for p in paths]
    except ValueError as e:
        print("skip photo comparison: %s (convert the photo first, e.g. "
              "sips -s format png --resampleHeightWidthMax 1600 photo.jpg --out photo.png)" % e)
        return
    ph = 1000
    scaled = [resize_box(p, int(round(p[0] * ph / p[1])), ph) for p in panels]
    pad = 12
    sheet = new_image(sum(s[0] for s in scaled) + pad * (len(scaled) + 1), ph + 2 * pad)
    ox = pad
    for s in scaled:
        paste(sheet, s, ox, pad)
        ox += s[0] + pad
    save_png(os.path.join(figdir, "photo_vs_render.png"), sheet)
    print("wrote photo_vs_render.png (photograph | WSRT_creative | DRT_creative)")


def main():
    args = sys.argv[1:]
    outdir = os.path.join(HERE, "..", "..", "output")
    photo = None
    if "--outdir" in args:
        outdir = args[args.index("--outdir") + 1]
    if "--photo" in args:
        photo = args[args.index("--photo") + 1]
    figdir = os.path.join(outdir, "figures")
    for name in FEATURES:
        annotate(name, outdir, figdir)
    compare(outdir, figdir)
    for name in ("DRT_simple", "DRT_creative"):
        tonemap_figure(name, outdir, figdir)
    if photo:
        photo_vs_render(photo, outdir, figdir)


if __name__ == "__main__":
    main()
