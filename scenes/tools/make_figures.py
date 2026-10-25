#!/usr/bin/env python3
"""Report figures for the Module 1 images (Python 3 standard library only).

For each rendered image (output/<name>.png) this writes, into output/figures/:
  <name>_annotated.png        numbered callouts with arrows and frames around the zoomed regions,
                              a title bar (renderer, resolution, samples and render time from the
                              log) and a key with a short label for every callout
  <name>_annotated_plain.png  the same callouts without the title bar and key
  <name>_insets.png           the framed regions enlarged, each with its number, label and zoom
  <name>_legend.txt           number -> full description of each region
plus
  compare_wsrt_drt.png  the same regions of WSRT_creative and DRT_creative side by side
  <DRT>_tonemap.png     DRT_simple / DRT_creative with four tone mappings recomputed from the
                        linear HDR output (<DRT>.pfm): clamp, Reinhard on luminance (as rendered),
                        Reinhard per channel, Reinhard with another white point; plus enlarged regions
  photo_vs_render.png   (with --photo PATH.png) photograph | WSRT_creative | DRT_creative
  WSRT_simple_maxdepth.png, DRT_simple_lightsamples.png
                        the same region of a scene rendered with one parameter changed (renders made
                        by renderReportedImages.sh with command-line overrides)

Callouts are placed by projecting each feature's 3D position with the same camera
model as the renderer (pbrt LookAt, fov on the shorter image axis), so they stay on
target if the images are re-rendered at another resolution.

Text is drawn with a TrueType font read by a small built-in rasteriser (Arial on macOS,
DejaVu or Liberation Sans on Linux); without such a font the figures have no text.

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


# (short label drawn on the figures, full label for the legend file, 3D anchor,
#  region half-size as a fraction of the image width, badge direction (dx, dy))
FEATURES = {
    "WSRT_creative": [
        ("Mirror reflection (grater)", "Mirror reflection (recursive): steel grater",
         (GRATER_POS[0] + 0.4, 4.6, GRATER_POS[1] - 1.3), 0.07, (1, -1)),
        ("Refraction + Fresnel (water glass)",
         "Refraction and Fresnel: water glass (the ball behind it is magnified and mirrored left to right)",
         (GLASS_POS[0], 3.0, GLASS_POS[1] - 1.6), 0.09, (1, -1)),
        ("Refraction (faceted crystal cap)", "Refraction through faceted crystal (cap)",
         (PERFUME_POS[0], 3.3, PERFUME_POS[1] - 1.4), 0.06, (-1, -1)),
        ("Coloured filtered shadow (bottle)", "Coloured transparent shadow (amber bottle, filtered shadow rays)",
         (-4.3, 0.0, 15.6), 0.07, (-1, 1)),
        ("Alpha cut-outs: light dots",
         "Light through the grater holes: dots of light in its shadow (alpha cut-outs)",
         (-9.0, 0.0, 23.0), 0.06, (1, 1)),
        ("Hard shadows, two point lights",
         "Hard shadows from two point lights: cool key (towards camera) and warm fill (to the left)",
         (5.6, 0.0, 19.9), 0.07, (1, 1)),
        ("Blinn-Phong shading (ball 3)", "Blinn-Phong: ambient, diffuse and a small specular highlight",
         (-1.82, 1.55, 23.19 - 0.6), 0.045, (-1, 1)),
        ("UV texture on a sphere (ball 11)", "UV texture on a sphere (numbered ball)",
         (5.19, 1.0, 26.07 - 1.0), 0.045, (1, -1)),
        ("Textures on triangles (felt, rail)", "Textures on triangles: felt weave and speckled rail (+ white strip)",
         (0.64, 1.5, 10.0), 0.06, (-1, -1)),
        ("Triangles + instancing (rack)", "Triangles + object instancing: rack built from one bar",
         (-4.52, 0.5, 43.57), 0.06, (1, -1)),
    ],
    "DRT_creative": [
        ("Soft shadow (area key light)", "Soft shadows (penumbra) from the area key light",
         (5.6, 0.0, 19.9), 0.07, (1, 1)),
        ("Phong BRDF highlight (ball 11)", "Phong BRDF: glossy highlight and clear-coat reflection",
         (5.19, 1.6, 26.07 - 0.8), 0.045, (1, -1)),
        ("Smooth OBJ meshes (glass, water)", "OBJ meshes with vertex normals: smooth refraction through the glass",
         (GLASS_POS[0], 3.0, GLASS_POS[1] - 1.6), 0.09, (-1, -1)),
        ("Texture on mesh UVs (cue wood)", "Texture on a mesh through its UVs: cue wood", _cue_point(0.1), 0.035,
         (1, -1)),
        ("Depth of field: lamp bokeh", "Depth of field: background out of focus (thin lens): wall lamp bokeh",
         (30.0, 22.0, 469.8), 0.06, (-1, 1)),
        ("Depth of field: near rail blurred", "Depth of field: near rail out of focus", (3.11, 1.5, 12.03), 0.07,
         (1, 1)),
        ("Filtered shadow of the glass",
         "Filtered (transparent) shadow of the glass: dark walls, light passing through the middle",
         (0.9, 0.0, 18.7), 0.1, (-1, 1)),
        ("Reinhard: bright felt not clipped",
         "Reinhard tone mapping: the brightest felt keeps its gradation instead of clipping "
         "(see DRT_creative_tonemap.png)", (-10.52, 0.0, 59.31), 0.04, (1, -1)),
    ],
    "WSRT_simple": [
        ("Recursive mirror reflection", "Recursive mirror reflection (sphere)", (-1.7, 1.0, 0.8), 0.08, (1, -1)),
        ("Refraction + Fresnel (glass)", "Refraction + Fresnel (glass sphere: inverted image; TIR cannot occur in a sphere, see val_wsrt_snell)",
         (0.3, 0.95, -1.6), 0.07, (1, 1)),
        ("Blinn-Phong highlight", "Blinn-Phong highlight (red sphere)", (2.1, 0.95, 0.2 - 0.5), 0.06, (1, -1)),
        ("UV texture on a sphere", "UV texture on a sphere", (0.6, 1.574, 1.781), 0.06, (1, -1)),
        ("Plane texture + hard shadow", "UV texture on a plane (checker floor) + hard shadow of the glass sphere",
         (-0.6, 0.0, -1.2), 0.06, (-1, 1)),
        ("Texture on triangles (wall)", "UV texture on triangles (brick wall)", (3.5, 3.5, 5.0), 0.07, (1, -1)),
        ("Single triangle", "Single triangle primitive", (-3.35, 1.85, 2.8), 0.045, (-1, -1)),
    ],
    "DRT_simple": [
        ("OBJ mesh: normals + UVs", "OBJ triangle mesh: smooth normals + UV wood texture (torus)",
         (-1.5, 1.4, 0.65), 0.045, (-1, -1)),
        ("Area light (emissive quad)", "Area light (emissive rectangle)", (0.7, 3.98, 1.2), 0.05, (1, 1)),
        ("Soft shadow (penumbra)", "Soft shadow (penumbra) of the torus", (-1.7, 0.0, 0.5), 0.05, (-1, 1)),
        ("Energy-conserving Phong BRDF", "Energy-conserving Phong BRDF (glossy sphere)", (1.25, 0.92, 0.85), 0.08,
         (1, -1)),
        ("Depth of field (thin lens)", "Depth of field: foreground glass sphere out of focus", (0.45, 0.45, -2.4),
         0.08, (-1, 1)),
        ("Reinhard: highlight roll-off",
         "Reinhard tone mapping: the highlight rolls off into white (see DRT_simple_tonemap.png)",
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
# (source/core/image.cpp): (title, label, op, mode, white point: None = the scene's, 0 = maximum luminance,
# which is what the renderer uses when the scene gives no white point)
TONEMAP_VARIANTS = [
    ("Clamp (no tone mapping)", "No tone mapping: linear radiance x exposure, clamped to [0, 1]",
     "none", "luminance", None),
    ("Reinhard, luminance (rendered)", "Reinhard on luminance with the scene's white point (the rendered image)",
     "reinhard", "luminance", None),
    ("Reinhard, per channel", "Reinhard per channel (rgb) with the same white point", "reinhard", "rgb", None),
    ("Reinhard, luminance, white = max", "Reinhard on luminance with white point = maximum luminance",
     "reinhard", "luminance", 0.0),
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


# The same scene with one parameter changed (renderReportedImages.sh renders the variants with
# command-line overrides): (figure, scene whose camera frames the region, region centre, half width
# and half height as fractions of the image width, zoom, panels: (image stem, title))
STRIPS = [
    ("WSRT_simple_maxdepth", "WSRT_simple", (-0.6, 0.85, -0.3), 0.27, 0.19, 1,
     [("WSRT_simple_md1", "maxdepth 1"), ("WSRT_simple_md2", "maxdepth 2"), ("WSRT_simple_md3", "maxdepth 3"),
      ("WSRT_simple", "maxdepth 8 (the scene's value)")]),
    ("DRT_simple_lightsamples", "DRT_simple", (-1.3, 0.0, 0.4), 0.125, 0.085, 2,
     [("DRT_simple_ls1", "1 shadow ray x 4 spp = 4 per pixel"), ("DRT_simple_ls4", "4 x 4 spp = 16 per pixel"),
      ("DRT_simple_ls16", "16 x 4 spp = 64 per pixel"), ("DRT_simple", "4 x 256 spp = 1024 per pixel (final)")]),
]


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


# ---------------------------------------------------------------- text (TrueType outlines, stdlib only)
class Font:
    """Minimal TrueType reader and rasteriser: cmap format 4, simple and composite glyphs,
    quadratic outlines filled with the non-zero winding rule and 4 sub-scanlines per pixel."""

    def __init__(self, path):
        d = self.d = open(path, "rb").read()
        self.tables = {}
        for i in range(struct.unpack(">H", d[4:6])[0]):
            tag, _, off, length = struct.unpack(">4sIII", d[12 + 16 * i:28 + 16 * i])
            self.tables[tag.decode("latin-1")] = off
        head, hhea = self.tables["head"], self.tables["hhea"]
        self.upem = struct.unpack(">H", d[head + 18:head + 20])[0]
        self.long_loca = struct.unpack(">h", d[head + 50:head + 52])[0] == 1
        self.ascent, self.descent = struct.unpack(">hh", d[hhea + 4:hhea + 8])
        self.n_hmetrics = struct.unpack(">H", d[hhea + 34:hhea + 36])[0]
        self.cmap = self._read_cmap()
        self.cache = {}

    def _read_cmap(self):
        d, base = self.d, self.tables["cmap"]
        sub = None
        for i in range(struct.unpack(">H", d[base + 2:base + 4])[0]):
            pid, eid, off = struct.unpack(">HHI", d[base + 4 + 8 * i:base + 12 + 8 * i])
            if (pid, eid) in ((3, 1), (0, 3), (0, 4)) and struct.unpack(">H", d[base + off:base + off + 2])[0] == 4:
                sub = base + off
                break
        if sub is None:
            raise ValueError("no Unicode format-4 cmap")
        seg2 = struct.unpack(">H", d[sub + 6:sub + 8])[0]
        seg = seg2 // 2
        ends = struct.unpack(">%dH" % seg, d[sub + 14:sub + 14 + seg2])
        starts = struct.unpack(">%dH" % seg, d[sub + 16 + seg2:sub + 16 + 2 * seg2])
        deltas = struct.unpack(">%dh" % seg, d[sub + 16 + 2 * seg2:sub + 16 + 3 * seg2])
        ro = sub + 16 + 3 * seg2
        ranges = struct.unpack(">%dH" % seg, d[ro:ro + seg2])
        cmap = {}
        for code in list(range(32, 127)) + [0xB0, 0xB2, 0xB7, 0xD7, 0x2013, 0x2014, 0x2192, 0x2248, 0x2264, 0x2265]:
            for k in range(seg):
                if code <= ends[k]:
                    if code >= starts[k]:
                        if ranges[k] == 0:
                            g = (code + deltas[k]) & 0xFFFF
                        else:
                            a = ro + 2 * k + ranges[k] + 2 * (code - starts[k])
                            g = struct.unpack(">H", d[a:a + 2])[0]
                            g = (g + deltas[k]) & 0xFFFF if g else 0
                        cmap[chr(code)] = g
                    break
        return cmap

    def advance(self, g):
        h = self.tables["hmtx"] + 4 * min(g, self.n_hmetrics - 1)
        return struct.unpack(">H", self.d[h:h + 2])[0]

    def _glyph_range(self, g):
        d, loca = self.d, self.tables["loca"]
        if self.long_loca:
            a, b = struct.unpack(">II", d[loca + 4 * g:loca + 4 * g + 8])
        else:
            a, b = (2 * v for v in struct.unpack(">HH", d[loca + 2 * g:loca + 2 * g + 4]))
        return self.tables["glyf"] + a, b - a

    def contours(self, g, depth=0):
        """Outline of glyph g as contours of (x, y, on_curve) in font units (y up)."""
        d = self.d
        off, length = self._glyph_range(g)
        if length == 0 or depth > 4:
            return []
        n = struct.unpack(">h", d[off:off + 2])[0]
        p = off + 10
        if n >= 0:
            ends = struct.unpack(">%dH" % n, d[p:p + 2 * n])
            p += 2 * n
            p += 2 + struct.unpack(">H", d[p:p + 2])[0]
            npts = ends[-1] + 1 if n else 0
            flags = []
            while len(flags) < npts:
                f = d[p]
                p += 1
                flags.append(f)
                if f & 8:
                    flags.extend([f] * d[p])
                    p += 1
            coords = []
            for short, same in ((2, 16), (4, 32)):
                v, vals = 0, []
                for f in flags[:npts]:
                    if f & short:
                        v += d[p] if f & same else -d[p]
                        p += 1
                    elif not f & same:
                        v += struct.unpack(">h", d[p:p + 2])[0]
                        p += 2
                    vals.append(v)
                coords.append(vals)
            pts = [(coords[0][i], coords[1][i], bool(flags[i] & 1)) for i in range(npts)]
            out, s = [], 0
            for e in ends:
                out.append(pts[s:e + 1])
                s = e + 1
            return out
        out = []
        while True:  # composite glyph
            fl, gi = struct.unpack(">HH", d[p:p + 4])
            p += 4
            if fl & 1:
                a1, a2 = struct.unpack(">hh", d[p:p + 4])
                p += 4
            else:
                a1, a2 = struct.unpack(">bb", d[p:p + 2])
                p += 2
            m = (1.0, 0.0, 0.0, 1.0)
            if fl & 8:
                s = struct.unpack(">h", d[p:p + 2])[0] / 16384.0
                m = (s, 0.0, 0.0, s)
                p += 2
            elif fl & 0x40:
                sx, sy = (v / 16384.0 for v in struct.unpack(">hh", d[p:p + 4]))
                m = (sx, 0.0, 0.0, sy)
                p += 4
            elif fl & 0x80:
                m = tuple(v / 16384.0 for v in struct.unpack(">hhhh", d[p:p + 8]))
                p += 8
            dx, dy = (a1, a2) if fl & 2 else (0, 0)
            for c in self.contours(gi, depth + 1):
                out.append([(m[0] * x + m[2] * y + dx, m[1] * x + m[3] * y + dy, on) for x, y, on in c])
            if not fl & 0x20:
                return out

    def glyph(self, ch, px):
        """(coverage rows, left, top, advance) of a character at pixel size px (em height)."""
        key = (ch, px)
        if key in self.cache:
            return self.cache[key]
        g = self.cmap.get(ch, self.cmap.get("?", 0))
        s = px / self.upem
        edges = []
        for c in self.contours(g):
            poly = _ttf_flatten(c)
            for i in range(len(poly)):
                (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % len(poly)]
                if y0 != y1:
                    edges.append((x0 * s, -y0 * s, x1 * s, -y1 * s))
        adv = self.advance(g) * s
        if not edges:
            res = ([], 0, 0, adv)
        else:
            xmin = math.floor(min(min(e[0], e[2]) for e in edges))
            xmax = math.ceil(max(max(e[0], e[2]) for e in edges))
            ymin = math.floor(min(min(e[1], e[3]) for e in edges))
            ymax = math.ceil(max(max(e[1], e[3]) for e in edges))
            w, h, S = xmax - xmin, ymax - ymin, 4
            rows = [[0.0] * (w + 1) for _ in range(h)]
            for yy in range(h):
                row = rows[yy]
                for k in range(S):
                    ys = ymin + yy + (k + 0.5) / S
                    xs = []
                    for x0, y0, x1, y1 in edges:
                        if (y0 <= ys < y1) or (y1 <= ys < y0):
                            xs.append((x0 + (ys - y0) / (y1 - y0) * (x1 - x0) - xmin, 1 if y1 > y0 else -1))
                    xs.sort()
                    wind = 0
                    for i in range(len(xs) - 1):
                        wind += xs[i][1]
                        if wind:
                            _ttf_span(row, xs[i][0], xs[i + 1][0], 1.0 / S)
            res = (rows, xmin, ymin, adv)
        self.cache[key] = res
        return res


def _ttf_flatten(contour, steps=6):
    """TrueType quadratic contour (implied on-curve midpoints) -> closed polyline."""
    pts = [(x, y, on) for x, y, on in contour]
    if not pts:
        return []
    if not any(on for _, _, on in pts):
        x0, y0, _ = pts[0]
        x1, y1, _ = pts[1 % len(pts)]
        pts.insert(0, ((x0 + x1) / 2, (y0 + y1) / 2, True))
    while not pts[0][2]:
        pts.append(pts.pop(0))
    out = [(pts[0][0], pts[0][1])]
    n, i = len(pts), 1
    cur = (pts[0][0], pts[0][1])
    while i <= n:
        x, y, on = pts[i % n]
        if on:
            cur = (x, y)
            out.append(cur)
            i += 1
            continue
        nx, ny, non = pts[(i + 1) % n]
        end = (nx, ny) if non else ((x + nx) / 2, (y + ny) / 2)
        for k in range(1, steps + 1):
            t = k / steps
            out.append(((1 - t) ** 2 * cur[0] + 2 * (1 - t) * t * x + t * t * end[0],
                        (1 - t) ** 2 * cur[1] + 2 * (1 - t) * t * y + t * t * end[1]))
        cur = end
        i += 2 if non else 1
    return out


def _ttf_span(row, xa, xb, amt):
    if xb <= xa:
        return
    ia, ib = int(math.floor(xa)), int(math.floor(xb))
    ia, ib = max(ia, 0), min(ib, len(row) - 1)
    if ia == ib:
        row[ia] += (xb - xa) * amt
        return
    row[ia] += (ia + 1 - xa) * amt
    for i in range(ia + 1, ib):
        row[i] += amt
    row[ib] += (xb - ib) * amt

FONT_FILES = {
    False: ["/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "C:/Windows/Fonts/arial.ttf"],
    True: ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
           "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
           "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"],
}
_fonts = {}


def get_font(bold=False):
    """The first readable font in FONT_FILES (bold falls back to regular); None if there is none."""
    if bold not in _fonts:
        _fonts[bold] = None
        for path in FONT_FILES[bold]:
            try:
                _fonts[bold] = Font(path)
                break
            except (OSError, ValueError, KeyError, IndexError, struct.error):
                continue
        if _fonts[bold] is None and bold:
            _fonts[bold] = get_font(False)
    return _fonts[bold]


def text_width(s, px, bold=False):
    f = get_font(bold)
    return 0 if f is None else sum(f.glyph(ch, px)[3] for ch in s)


def line_height(px):
    return int(round(px * 1.25))


def draw_text(img, x, y, s, px, col, bold=False):
    """Draws s at pixel size px with the top of its line at y; returns the advance width."""
    f = get_font(bold)
    if f is None:
        return 0
    base = int(round(y + f.ascent * px / f.upem))
    x0 = x
    for ch in s:
        rows, left, top, adv = f.glyph(ch, px)
        ox, oy = int(round(x)) + left, base + top
        for j, row in enumerate(rows):
            for i, a in enumerate(row):
                if a > 0.004:
                    _blend(img, ox + i, oy + j, col, a)
        x += adv
    return x - x0


def wrap_text(s, px, width, bold=False):
    lines, cur = [], ""
    for word in s.split():
        t = word if not cur else cur + " " + word
        if cur and text_width(t, px, bold) > width:
            lines.append(cur)
            cur = word
        else:
            cur = t
    return lines + ([cur] if cur else [])


def fill_rect(img, x0, y0, x1, y1, col):
    w, h, d = img
    xa, xb = max(0, int(x0)), min(w, int(x1))
    for y in range(max(0, int(y0)), min(h, int(y1))):
        if xb > xa:
            d[(y * w + xa) * 3:(y * w + xb) * 3] = bytes(col) * (xb - xa)


# ---------------------------------------------------------------- figures
def _render_info(outdir, name):
    """Renderer, resolution, samples per pixel and render time from <name>.log, for title bars."""
    try:
        log = open(os.path.join(outdir, name + ".log")).read()
    except OSError:
        return ""
    parts = []
    m = re.search(r"integrator: (\w+)", log)
    if m:
        parts.append({"whitted": "Whitted ray tracer", "distributed": "distributed ray tracer"}.get(m.group(1),
                                                                                                m.group(1)))
    m = re.search(r"film: (\d+)x(\d+), (\d+) spp", log)
    if m:
        parts.append("%s×%s px, %s spp" % m.groups())
    m = re.search(r"render \(s\):\s+([0-9.]+)", log)
    if m:
        t = float(m.group(1))
        parts.append("render " + ("%.2f s" % t if t < 1 else "%.0f s" % t if t < 600 else "%.0f min" % (t / 60)))
    return " · ".join(parts)


def _labelled(ann, title, info, keys):
    """The annotated image with a title bar above it and a key of the numbered callouts below."""
    if get_font() is None:
        return ann
    W, H = ann[0], ann[1]
    px = max(16, int(round(W / 34)))
    sub = int(round(px * 0.72))
    pad = int(round(px * 0.55))
    lh = line_height(px)
    head_h = pad + lh + (line_height(sub) if info else 0) + pad
    cols = 2 if W >= 900 else 1
    col_w = (W - pad * (cols + 1)) // cols
    r = px * 0.62
    tx = int(round(2 * r + pad))
    entries = [(n, wrap_text(s, px, col_w - tx)) for n, s in keys]
    rows = [entries[i:i + cols] for i in range(0, len(entries), cols)]
    row_h = [max(max(len(lines) * lh for _, lines in row), int(2 * r + 6)) + pad // 2 for row in rows]
    out = new_image(W, head_h + H + pad + sum(row_h) + pad)
    fill_rect(out, 0, 0, W, head_h, (30, 30, 30))
    draw_text(out, pad, pad, title, px, (255, 255, 255), bold=True)
    if info:
        draw_text(out, pad, pad + lh, info, sub, (205, 205, 205))
    paste(out, ann, 0, head_h)
    y = head_h + H + pad
    for row, h in zip(rows, row_h):
        for c, (n, lines) in enumerate(row):
            x0 = pad + c * (col_w + pad)
            block = len(lines) * lh
            cy = y + max(r + 3, block / 2)
            badge(out, x0 + r + 3, cy, r, n)
            for k, line in enumerate(lines):
                draw_text(out, x0 + tx, cy - block / 2 + k * lh, line, px, (0, 0, 0))
        y += h
    return out


def _inset_sheet(tiles, rad):
    """The enlarged regions in rows of three, each with its number, label and zoom factor."""
    pad, cols = 12, 3
    tw = max(t[3][0] for t in tiles)
    th = max(t[3][1] for t in tiles)
    font = get_font() is not None
    cp = max(14, int(round(tw / 16)))
    lh = line_height(cp)
    caps = [(wrap_text("%d  %s" % (n, s), cp, tw, bold=True) + ["zoom ×%d" % z]) if font else []
            for n, s, z, _ in tiles]
    cap_h = max(len(c) for c in caps) * lh + 6 if font else 0
    nrows = (len(tiles) + cols - 1) // cols
    sheet = new_image(cols * (tw + pad) + pad, nrows * (th + cap_h + pad) + pad)
    for k, ((n, s, z, tile), cap) in enumerate(zip(tiles, caps)):
        ox, oy = pad + (k % cols) * (tw + pad), pad + (k // cols) * (th + cap_h + pad)
        paste(sheet, tile, ox, oy)
        draw_rect(sheet, ox, oy, ox + tile[0], oy + tile[1], (0, 0, 0), 2)
        badge(sheet, ox + rad + 6, oy + rad + 6, rad, n)
        for i, line in enumerate(cap):
            last = i == len(cap) - 1
            draw_text(sheet, ox, oy + tile[1] + 4 + i * lh, line, cp, (110, 110, 110) if last else (0, 0, 0),
                      bold=not last)
    return sheet


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
    tiles, legend, keys = [], [], []
    for n, (short, label, anchor, hs, (dx, dy)) in enumerate(FEATURES[name], 1):
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
        z = max(1, round(360 / (x1 - x0)))
        tiles.append((n, short, z, crop_scaled(img, x0, y0, x1, y1, z)))
        legend.append("%d  %s" % (n, label))
        keys.append((n, short))
    os.makedirs(figdir, exist_ok=True)
    save_png(os.path.join(figdir, name + "_annotated_plain.png"), ann)
    save_png(os.path.join(figdir, name + "_annotated.png"), _labelled(ann, name, _render_info(outdir, name), keys))
    save_png(os.path.join(figdir, name + "_insets.png"), _inset_sheet(tiles, rad))
    with open(os.path.join(figdir, name + "_legend.txt"), "w") as f:
        f.write("%s: numbered regions in %s_annotated.png, %s_annotated_plain.png and %s_insets.png\n"
                % (name, name, name, name))
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
        tiles.append((crop_scaled(A, *box, 2), crop_scaled(B, *box, 2)))
    tw, th, pad = max(t[0][0] for t in tiles), max(t[0][1] for t in tiles), 12
    font = get_font() is not None
    tp = 28
    lh = line_height(tp) if font else 0
    head = lh + pad if font else 0
    cap = lh + 4 if font else 0
    sheet = new_image(2 * tw + 3 * pad, pad + head + len(tiles) * (cap + th + pad))
    rad = max(14, W / 48)
    if font:
        draw_text(sheet, pad, pad, "WSRT_creative (Whitted)", tp, (0, 0, 0), bold=True)
        draw_text(sheet, 2 * pad + tw, pad, "DRT_creative (distributed)", tp, (0, 0, 0), bold=True)
    for k, (ta, tb) in enumerate(tiles):
        oy = pad + head + k * (cap + th + pad)
        if font:
            draw_text(sheet, pad, oy, "%d  %s" % (k + 1, COMPARE[k][0]), tp, (60, 60, 60))
        oy += cap
        for j, t in enumerate((ta, tb)):
            ox = pad + j * (tw + pad)
            paste(sheet, t, ox, oy)
            draw_rect(sheet, ox, oy, ox + t[0], oy + t[1], (0, 0, 0), 2)
        badge(sheet, pad + rad + 6, oy + rad + 6, rad, k + 1)
    save_png(os.path.join(figdir, "compare_wsrt_drt.png"), sheet)
    with open(os.path.join(figdir, "compare_wsrt_drt_legend.txt"), "w") as f:
        f.write("compare_wsrt_drt.png: left column WSRT_creative, right column DRT_creative (regions enlarged x2)\n")
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


def _num(v):
    return "%.0f" % v if v >= 100 else "%.3g" % v


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
    imgs, stats, notes = [], [], []
    for title, label, op, md, wp in TONEMAP_VARIANTS:
        img, clipped, used = tonemap(hdr, op, md, scale, white if wp is None else wp)
        imgs.append(img)
        stats.append((used, clipped))
        wtxt = "" if op == "none" else ", white point %s" % _num(used)
        notes.append("%s (exposure %.3g%s): %.2f%% of pixels at white" % (label, scale, wtxt, 100 * clipped))
    # the variant with the scene's own settings must reproduce the rendered PNG
    k = next(i for i, v in enumerate(TONEMAP_VARIANTS) if v[2] == "reinhard" and v[3] == mode and v[4] is None)
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
    # sheet: the four versions at half size (2 x 2) with titles, then one row of enlarged regions per region
    font = get_font() is not None
    pad, pw, ph = 12, W // 2, H // 2
    tp = max(16, int(round(pw / 26)))
    lh = line_height(tp)
    title_h = 2 * lh + 6 if font else 0
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
        rows.append((label, box, crops))
    row_cap = lh + 6 if font else 0
    sheet = new_image(sheet_w, 3 * pad + 2 * (title_h + ph) + sum(row_cap + max(c[1] for c in cr) + pad
                                                                  for _, _, cr in rows))
    for i, im in enumerate(imgs):
        ox, oy = pad + (i % 2) * (pw + pad), pad + (i // 2) * (title_h + ph + pad)
        if font:
            used, clipped = stats[i]
            detail = ("exposure %.3g" % scale) if TONEMAP_VARIANTS[i][2] == "none" else ("white point " + _num(used))
            draw_text(sheet, ox, oy, "%d  %s" % (i + 1, TONEMAP_VARIANTS[i][0]), tp, (0, 0, 0), bold=True)
            draw_text(sheet, ox, oy + lh, "%s · %.2f%% of pixels at white" % (detail, 100 * clipped), tp,
                      (90, 90, 90))
        oy += title_h
        paste(sheet, resize_box(im, pw, ph), ox, oy)
        for _, (x0, y0, x1, y1), _ in rows:
            draw_rect(sheet, ox + x0 // 2, oy + y0 // 2, ox + x1 // 2, oy + y1 // 2, (255, 214, 0), 2)
        draw_rect(sheet, ox, oy, ox + pw, oy + ph, (0, 0, 0), 2)
        badge(sheet, ox + rad + 6, oy + rad + 6, rad, i + 1)
    oy = pad + 2 * (title_h + ph + pad)
    for label, _, crops in rows:
        if font:
            draw_text(sheet, pad, oy, "Enlarged (yellow frame): " + label, tp, (60, 60, 60))
            oy += row_cap
        for j, c in enumerate(crops):
            ox = pad + j * (cell + pad)
            paste(sheet, c, ox, oy)
            draw_rect(sheet, ox, oy, ox + c[0], oy + c[1], (0, 0, 0), 2)
            badge(sheet, ox + srad + 5, oy + srad + 5, srad, j + 1)
        oy += max(c[1] for c in crops) + pad
    os.makedirs(figdir, exist_ok=True)
    save_png(os.path.join(figdir, name + "_tonemap.png"), sheet)
    with open(os.path.join(figdir, name + "_tonemap_legend.txt"), "w") as f:
        f.write("%s_tonemap.png: one HDR render (%s.pfm, max luminance %s, log-average %s) shown with four\\n"
                "tone mappings; panels 1 2 (top) and 3 4 (bottom); the rows under them enlarge the framed\\n"
                "regions with the same numbers\\n" % (name, name, max_lum, log_avg))
        f.write("\\n".join("%d  %s" % (i + 1, t) for i, t in enumerate(notes)) + "\\n")
        f.write("regions, top to bottom: " + "; ".join(t[0] for t in TONEMAP_REGIONS.get(name, [])) + "\\n")
        f.write("check: " + check + "\\n")
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
    tp = 30
    head = line_height(tp) + 6 if get_font() is not None else 0
    sheet = new_image(sum(s[0] for s in scaled) + pad * (len(scaled) + 1), ph + 2 * pad + head)
    ox = pad
    for s, title in zip(scaled, ("Photograph", "WSRT_creative (Whitted)", "DRT_creative (distributed)")):
        draw_text(sheet, ox, pad, title, tp, (0, 0, 0), bold=True)
        paste(sheet, s, ox, pad + head)
        ox += s[0] + pad
    save_png(os.path.join(figdir, "photo_vs_render.png"), sheet)
    print("wrote photo_vs_render.png (photograph | WSRT_creative | DRT_creative)")


def param_strips(outdir, figdir):
    for fig, cam, anchor, hw, hh, z, panels in STRIPS:
        paths = [os.path.join(outdir, stem + ".png") for stem, _ in panels]
        if not all(os.path.exists(p) for p in paths):
            print("skip %s.png: variants not rendered yet (renderReportedImages.sh renders them)" % fig)
            continue
        imgs = [load_png(p) for p in paths]
        W, H = imgs[0][0], imgs[0][1]
        cx, cy = project(cam, anchor, W, H)
        box = (int(cx - hw * W), int(cy - hh * W), int(cx + hw * W), int(cy + hh * W))
        crops = [crop_scaled(im, *box, z) for im in imgs]
        tp, pad, cols = 26, 12, 2
        title_h = line_height(tp) + 4 if get_font() is not None else 0
        cw, ch = max(c[0] for c in crops), max(c[1] for c in crops)
        nrows = (len(crops) + cols - 1) // cols
        sheet = new_image(cols * (cw + pad) + pad, nrows * (title_h + ch + pad) + pad)
        for i, (c, (_, title)) in enumerate(zip(crops, panels)):
            ox, oy = pad + (i % cols) * (cw + pad), pad + (i // cols) * (title_h + ch + pad)
            draw_text(sheet, ox, oy, "%d  %s" % (i + 1, title), tp, (0, 0, 0), bold=True)
            paste(sheet, c, ox, oy + title_h)
            draw_rect(sheet, ox, oy + title_h, ox + c[0], oy + title_h + c[1], (0, 0, 0), 2)
        save_png(os.path.join(figdir, fig + ".png"), sheet)
        print("wrote %s.png" % fig)


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
    param_strips(outdir, figdir)
    if photo:
        photo_vs_render(photo, outdir, figdir)


if __name__ == "__main__":
    main()
