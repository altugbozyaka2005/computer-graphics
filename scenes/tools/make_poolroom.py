#!/usr/bin/env python3
"""Assets for the pool-hall creative scenes (Python 3 standard library only).

Recreates the Module 1 creative photograph. Every position below was measured on the
photograph: a camera (focal length 1760 px on the 1500 px image width = 46.2 deg fov,
height 9.2, pitch 18.5 deg down) was fitted to the image sizes of the eight visible
balls (radius 1), then image points (ball centres, object footprints, rail and cushion
lines) were back-projected onto their known heights.

Units: a pool ball has radius 1 (2.55 cm); y is up; the felt is at y = 0; the camera
is at (0, 9.2, 0) looking along +z.

Writes
  textures/ felt.ppm (weave), railblack.ppm, metal.ppm, grater_alpha.ppm, label.ppm
  meshes/   glass.obj (ribbed rim), water.obj, cap.obj (faceted crystal), grater.obj,
            cue_leather.obj, cue_ferrule.obj, cue_shaft.obj, cue_butt.obj
  include/  poolhall_geometry.pbrt                (shared geometry, named materials)
            poolhall_materials_wsrt.pbrt / _drt   (material values per renderer)
            poolhall_spots_wsrt.pbrt / _drt       (ceiling spot lights)
"""
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(HERE, "..", "textures")
MESH = os.path.join(HERE, "..", "meshes")
INC = os.path.join(HERE, "..", "include")

# ---------------------------------------------------------------- calibrated camera
CAM_EYE = (0.0, 9.2, 0.0)
CAM_PITCH = 18.5  # degrees, looking down
CAM_FOV = 46.2    # degrees across the (shorter) image width


def camera_lookat():
    p = math.radians(CAM_PITCH)
    e = CAM_EYE
    return "LookAt %g %g %g   %g %.4f %.4f   0 1 0" % (e[0], e[1], e[2], e[0], e[1] - 10 * math.sin(p), 10 * math.cos(p))


# ---------------------------------------------------------------- textures
def write_ppm(name, w, h, pixels):
    os.makedirs(TEX, exist_ok=True)
    with open(os.path.join(TEX, name), "wb") as f:
        f.write(b"P6\n%d %d\n255\n" % (w, h))
        f.write(bytes(max(0, min(255, int(round(c)))) for px in pixels for c in px))
    print("wrote scenes/textures/" + name)


def felt_texture():
    """Plain-weave green cloth: 4-px threads alternating over/under, plus fibre noise. Tileable."""
    rnd = random.Random(11)
    W = H = 512
    T = 4
    pixels = []
    for y in range(H):
        for x in range(W):
            i, j = x // T, y // T
            fx, fy = (x % T + 0.5) / T, (y % T + 0.5) / T
            warp_on_top = (i + j) % 2 == 0
            # thread cross-section: brightest along the thread centre line
            prof = math.sin(math.pi * (fy if warp_on_top else fx))
            g = 0.86 + 0.18 * prof + 0.10 * (rnd.random() - 0.5)
            pixels.append((32 * g, 142 * g, 46 * g))
    write_ppm("felt.ppm", W, H, pixels)


def railblack_texture():
    """Matte black frame with fine light speckles (as in the photograph)."""
    rnd = random.Random(9)
    W = H = 256
    pixels = []
    for _ in range(W * H):
        v = 14 + 8 * rnd.random()
        if rnd.random() < 0.06:
            v = 45 + 70 * rnd.random()
        pixels.append((v, v, v))
    write_ppm("railblack.ppm", W, H, pixels)


def metal_texture():
    """Brushed stainless steel (horizontal streaks)."""
    rnd = random.Random(5)
    W = H = 256
    rows = [rnd.random() for _ in range(H)]
    pixels = []
    for y in range(H):
        for x in range(W):
            v = 196 + 18 * (rows[y] - 0.5) + 6 * (rnd.random() - 0.5)
            pixels.append((v, v, v * 1.02))
    write_ppm("metal.ppm", W, H, pixels)


def grater_alpha_texture():
    """Cut-out mask for the grater sleeve (white = metal, black = hole). Atlas: the left
    half is used by the front/back faces (staggered coarse oval holes), the right half
    by the side faces (three horizontal slicing slots)."""
    W, H = 512, 512
    pixels = []
    for y in range(H):
        for x in range(W):
            u, v = (x + 0.5) / W, 1 - (y + 0.5) / H  # v = 0 at the bottom of a face
            solid = True
            if u < 0.5:
                uu = u / 0.5
                if 0.07 < uu < 0.93 and 0.06 < v < 0.94:
                    cols, rows = 5, 10
                    fy = (v - 0.06) / 0.88 * rows
                    r = int(fy)
                    fx = (uu - 0.07) / 0.86 * cols + (0.5 if r % 2 else 0.0)
                    dx, dy = (fx - (math.floor(fx) + 0.5)) / 0.24, (fy - (r + 0.5)) / 0.36
                    if dx * dx + dy * dy < 1 and 0.2 < fx < cols - 0.2 + (0.5 if r % 2 else 0):
                        solid = False
            else:
                uu = (u - 0.5) / 0.5
                if 0.18 < uu < 0.82:
                    for vc in (0.25, 0.5, 0.75):
                        if abs(v - vc) < 0.022:
                            solid = False
            c = 255 if solid else 0
            pixels.append((c, c, c))
    write_ppm("grater_alpha.ppm", W, H, pixels)


def label_texture():
    """Small plain green label with a thin light border (no text or branding)."""
    W, H = 128, 96
    pixels = []
    for y in range(H):
        for x in range(W):
            border = x < 4 or x >= W - 4 or y < 4 or y >= H - 4
            inner = 6 <= x < W - 6 and 6 <= y < H - 6
            if border:
                c = (225, 230, 222)
            elif not inner:
                c = (62, 140, 96)
            else:
                c = (70, 150, 104)
            pixels.append(c)
    write_ppm("label.ppm", W, H, pixels)


# ---------------------------------------------------------------- pool-ball textures
# Styles, colours and proportions measured on the reference sheet (148 x 75 px per ball,
# equirectangular): number circle centred at u = 0.745 on the equator with an angular
# radius of 0.539 rad; stripe band +-0.726 rad around the equator; digits 0.46 tall.
BALL_STYLES = {
    "1": ("solid", (255, 174, 1)), "2": ("solid", (43, 103, 194)), "3": ("solid", (244, 0, 16)),
    "4": ("solid", (82, 31, 146)), "5": ("solid", (241, 95, 0)), "6": ("solid", (18, 144, 38)),
    "7": ("solid", (100, 18, 0)), "8": ("solid", (0, 0, 0)),
    "9": ("stripe", (255, 174, 1)), "10": ("stripe", (43, 103, 194)), "11": ("stripe", (244, 0, 16)),
    "12": ("stripe", (82, 31, 146)), "13": ("stripe", (241, 95, 0)), "14": ("stripe", (18, 144, 38)),
    "15": ("stripe", (100, 18, 0)),
    "cue": ("cue", (255, 244, 218)), "redwhite": ("band", (244, 0, 16)), "gold": ("crown", (235, 169, 14)),
}
BALL_U_CENTRE, BALL_CIRCLE_R, BALL_BAND = 0.745, 0.539, 0.726


def _arc(cx, cy, rx, ry, a0, a1, n=28):
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * k / n)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * k / n))) for k in range(n + 1)]


def _bezier(p0, p1, p2, n=20):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]) for t in (k / n for k in range(n + 1))]


def _glyphs():
    """Bold digits as stroked polylines in a 0.62 x 1 em box (y up)."""
    g = {
        "0": [_arc(0.31, 0.5, 0.22, 0.385, 0, 360, 48)],
        "1": [[(0.12, 0.75), (0.33, 0.92), (0.33, 0.08)]],
        "2": [_arc(0.31, 0.70, 0.20, 0.20, 160, -35) + [(0.09, 0.08), (0.55, 0.08)]],
        "3": [_arc(0.30, 0.715, 0.185, 0.185, 155, -90), _arc(0.30, 0.29, 0.215, 0.215, 90, -155)],
        "4": [[(0.45, 0.08), (0.45, 0.92), (0.06, 0.34), (0.59, 0.34)]],
        "5": [[(0.54, 0.92), (0.17, 0.92), (0.13, 0.56)], _arc(0.31, 0.32, 0.23, 0.23, 128, -150)],
        "6": [_arc(0.31, 0.30, 0.215, 0.215, 0, 360, 40), _bezier((0.10, 0.33), (0.10, 0.80), (0.47, 0.92))],
        "7": [[(0.07, 0.92), (0.56, 0.92), (0.24, 0.08)]],
        "8": [_arc(0.31, 0.72, 0.175, 0.175, 0, 360, 36), _arc(0.31, 0.285, 0.215, 0.215, 0, 360, 40)],
    }
    g["9"] = [[(0.62 - x, 1 - y) for (x, y) in line] for line in g["6"]]
    return g


def _seg_dist2(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / L2))
    dx, dy = px - (ax + t * vx), py - (ay + t * vy)
    return dx * dx + dy * dy


def _inside_poly(x, y, poly):
    inside = False
    for i in range(len(poly)):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % len(poly)]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def ball_texture(name, W=768, H=384):
    """Equirectangular ball texture in the style of the reference sheet. The circle,
    digits, dot and crown are evaluated on the sphere (great-circle distance and a
    tangent-plane projection around the circle centre), so they are not distorted."""
    style, col = BALL_STYLES[name]
    white, black = (252, 252, 250), (18, 18, 18)
    phc = 2 * math.pi * BALL_U_CENTRE
    c = (math.cos(phc), math.sin(phc), 0.0)
    e = (-math.sin(phc), math.cos(phc), 0.0)  # increasing u (as in the texture image)
    tanR = math.tan(BALL_CIRCLE_R)
    glyphs = _glyphs()
    text = name if style in ("solid", "stripe") else ""
    h = 0.46  # digit height in tangent-plane units
    hw = 0.085 * h  # stroke half-width
    adv = 0.62 * h + 0.10 * h
    total = len(text) * 0.62 * h + max(0, len(text) - 1) * 0.10 * h
    strokes = []  # all digit polylines in tangent-plane coordinates
    for k, ch in enumerate(text):
        x0 = -total / 2 + k * adv
        for line in glyphs[ch]:
            strokes.append([(x0 + x * h, (y - 0.5) * h) for (x, y) in line])
    crown = [(-0.25, -0.13), (0.25, -0.13), (0.27, 0.12), (0.13, -0.01), (0.0, 0.16), (-0.13, -0.01), (-0.27, 0.12)]

    def colour(u, v):
        th, ph = math.pi * (1 - v), 2 * math.pi * u
        d = (math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), math.cos(th))
        base = col
        if style in ("stripe", "band"):
            base = col if abs(th - math.pi / 2) < BALL_BAND else white
        cd = d[0] * c[0] + d[1] * c[1]
        if cd <= 0:
            return base
        X = (d[0] * e[0] + d[1] * e[1]) / cd
        Y = d[2] / cd
        r2 = X * X + Y * Y
        if style == "cue":
            return (215, 25, 30) if r2 < math.tan(0.169) ** 2 else base
        if style == "band" or r2 >= tanR * tanR:
            return base
        if style == "crown":
            Xs, Ys = X / tanR, Y / tanR
            if _inside_poly(Xs, Ys, crown) or any((Xs - px) ** 2 + (Ys - py) ** 2 < 0.045 ** 2
                                                   for px, py in ((-0.27, 0.12), (0.0, 0.16), (0.27, 0.12))):
                return col
            return white
        if abs(X) < total / 2 + hw and abs(Y) < h / 2 + hw:
            for line in strokes:
                for i in range(len(line) - 1):
                    if _seg_dist2(X, Y, line[i][0], line[i][1], line[i + 1][0], line[i + 1][1]) < hw * hw:
                        return black
        return white

    pixels = []
    for py in range(H):
        for px in range(W):
            acc = [0.0, 0.0, 0.0]
            for sy in (0.25, 0.75):
                for sx in (0.25, 0.75):
                    cc = colour((px + sx) / W, 1 - (py + sy) / H)
                    for k in range(3):
                        acc[k] += cc[k] / 4
            pixels.append(acc)
    write_ppm("ball_%s.ppm" % name, W, H, pixels)


# ---------------------------------------------------------------- mesh utilities
def lathe(profile, segments, smooth_angle_deg=35.0, perturb=None):
    """Revolves a 2D profile [(r, y), ...] about the y axis.

    The profile is split at sharp corners; inside each smooth run the normals are
    averaged so curved parts shade smoothly and creases stay sharp. The outward side
    is to the right of the direction of travel (dr, dy) -> (dy, -dr).
    perturb(r, y, angle, (nx, ny, nz)) may return a modified shading normal.
    Returns (vertices, normals, uvs, faces) with faces as index triples.
    """
    edges = [(profile[i], profile[i + 1]) for i in range(len(profile) - 1)]
    enorm, elen = [], []
    for (r0, y0), (r1, y1) in edges:
        dr, dy = r1 - r0, y1 - y0
        L = math.hypot(dr, dy)
        enorm.append((dy / L, -dr / L))
        elen.append(L)
    total = sum(elen)
    runs, cur = [], [0]
    for i in range(1, len(edges)):
        a, b = enorm[i - 1], enorm[i]
        ang = math.degrees(math.acos(max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1]))))
        if ang > smooth_angle_deg:
            runs.append(cur)
            cur = [i]
        else:
            cur.append(i)
    runs.append(cur)
    verts, norms, uvs, faces = [], [], [], []
    arc_before = [sum(elen[:i]) for i in range(len(edges) + 1)]
    for run in runs:
        pts = [edges[run[0]][0]] + [edges[i][1] for i in run]
        pn = []
        for k in range(len(pts)):
            ns = []
            if k > 0:
                ns.append(enorm[run[k - 1]])
            if k < len(run):
                ns.append(enorm[run[k]])
            nr, ny = sum(n[0] for n in ns), sum(n[1] for n in ns)
            L = math.hypot(nr, ny) or 1.0
            pn.append((nr / L, ny / L))
        vs = [arc_before[run[0]] / total] + [arc_before[i + 1] / total for i in run]
        base = len(verts)
        for j in range(segments + 1):
            a = 2 * math.pi * j / segments
            ca, sa = math.cos(a), math.sin(a)
            for k, ((r, y), (nr, ny)) in enumerate(zip(pts, pn)):
                verts.append((r * ca, y, r * sa))
                n = (nr * ca, ny, nr * sa)
                if perturb:
                    n = perturb(r, y, a, n)
                norms.append(n)
                uvs.append((j / segments, vs[k]))
        n = len(pts)
        for j in range(segments):
            for k in range(n - 1):
                a = base + j * n + k
                b = base + (j + 1) * n + k
                c, d = b + 1, a + 1
                for tri in ((a, d, c), (a, c, b)):
                    p0, p1, p2 = (verts[t] for t in tri)
                    if p1 == p0 or p2 == p0 or p1 == p2:
                        continue  # degenerate (on the axis)
                    faces.append(tri)
    return verts, norms, uvs, faces


def tri_normal(p0, p1, p2):
    e1 = [p1[i] - p0[i] for i in range(3)]
    e2 = [p2[i] - p0[i] for i in range(3)]
    return (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])


def fix_winding(mesh):
    """Orients every triangle so its geometric normal agrees with its vertex normals."""
    verts, norms, uvs, faces = mesh
    out = []
    for a, b, c in faces:
        n = tri_normal(verts[a], verts[b], verts[c])
        avg = [norms[a][i] + norms[b][i] + norms[c][i] for i in range(3)]
        out.append((a, c, b) if sum(n[i] * avg[i] for i in range(3)) < 0 else (a, b, c))
    return verts, norms, uvs, out


def write_obj(name, mesh, comment):
    verts, norms, uvs, faces = mesh
    os.makedirs(MESH, exist_ok=True)
    with open(os.path.join(MESH, name), "w") as f:
        f.write("# %s (generated by scenes/tools/make_poolroom.py)\n" % comment)
        for v in verts:
            f.write("v %.6f %.6f %.6f\n" % v)
        for t in uvs:
            f.write("vt %.6f %.6f\n" % t)
        for n in norms:
            f.write("vn %.6f %.6f %.6f\n" % n)
        for a, b, c in faces:
            f.write("f %d/%d/%d %d/%d/%d %d/%d/%d\n" % (a + 1, a + 1, a + 1, b + 1, b + 1, b + 1, c + 1, c + 1, c + 1))
    print("wrote scenes/meshes/%s (%d triangles)" % (name, len(faces)))


def normalize3(v):
    L = math.sqrt(sum(x * x for x in v))
    return tuple(x / L for x in v)


# ---------------------------------------------------------------- meshes
GLASS_R, GLASS_H, GLASS_T, GLASS_B = 1.35, 4.2, 0.08, 0.35  # before the 1.18 scale in the scene


def glass_mesh():
    """Thick-walled tumbler (closed solid) with fine vertical ribs below the rim.
    The ribs are produced by perturbing the shading normals of the outer wall
    (36 ribs, up to 13 degrees), so the geometry stays a smooth, closed surface."""
    R, H, t, b = GLASS_R, GLASS_H, GLASS_T, GLASS_B
    pts = [(0.0, 0.0), (R - 0.06, 0.0)]
    for k in range(1, 5):  # rounded bottom edge
        a = -math.pi / 2 + (math.pi / 2) * k / 4
        pts.append((R - 0.06 + 0.06 * math.cos(a), 0.06 + 0.06 * math.sin(a)))
    top = H - t / 2
    for k in range(1, 15):  # outer wall, subdivided so the ribs can fade in
        y = 0.06 + (top - 0.06) * k / 14
        pts.append((R + 0.05 * (y - 0.06) / (top - 0.06), y))
    for k in range(1, 8):  # rounded rim
        a = math.pi * k / 8
        pts.append((R + 0.05 - t / 2 + (t / 2) * math.cos(a), H - t / 2 + (t / 2) * math.sin(a)))
    pts.append((R + 0.05 - t, H - t / 2))
    pts.append((R - t, b))
    pts.append((0.0, b))
    ribs, amp = 36, 0.23

    def ribbed(r, y, ang, n):
        if n[0] * math.cos(ang) + n[2] * math.sin(ang) < 0.9:  # only the outer wall
            return n
        s = min(1.0, max(0.0, (y - 0.55 * H) / (0.15 * H)))
        if s <= 0:
            return n
        tx, tz = -math.sin(ang), math.cos(ang)
        w = amp * s * math.sin(ribs * ang)
        return normalize3((n[0] + w * tx, n[1], n[2] + w * tz))

    return fix_winding(lathe(pts, 4 * ribs, perturb=ribbed))


def water_mesh():
    R, t, b, level = GLASS_R, GLASS_T, GLASS_B, 2.9
    gap = 0.004
    r_bottom = R - t - gap
    r_top = r_bottom + 0.05 * (level - b) / (GLASS_H - b)  # follow the taper
    return fix_winding(lathe([(0.0, b + gap), (r_bottom, b + gap), (r_top, level), (0.0, level)], 64))


def cue_meshes():
    """Cue along +y: leather tip at y = 0, white ferrule, light shaft, dark butt to y = 14."""
    parts = {
        "cue_leather.obj": [(0.0, 0.0), (0.15, 0.0), (0.16, 0.04), (0.16, 0.12)],
        "cue_ferrule.obj": [(0.16, 0.12), (0.16, 0.55)],
        "cue_shaft.obj": [(0.16, 0.55), (0.24, 8.0)],
        "cue_butt.obj": [(0.24, 8.0), (0.30, 13.6), (0.29, 14.0), (0.0, 14.0)],
    }
    for name, prof in parts.items():
        write_obj(name, fix_winding(lathe(prof, 32)), "pool cue part")


def grater_mesh():
    """Open tapered sleeve (four perforated faces, open top and bottom) with an arched
    handle. Per-face UVs index the grater_alpha.ppm atlas (front/back: left half,
    sides: right half)."""
    bx, bz, tx, tz, Hh = 2.23, 1.27, 1.95, 1.10, 7.3
    verts, norms, uvs, faces = [], [], [], []

    def quad(p, uv):
        n = normalize3(tri_normal(p[0], p[1], p[2]))
        base = len(verts)
        for q, t in zip(p, uv):
            verts.append(q)
            norms.append(n)
            uvs.append(t)
        faces.extend([(base, base + 1, base + 2), (base, base + 2, base + 3)])

    B = [(-bx, 0, -bz), (bx, 0, -bz), (bx, 0, bz), (-bx, 0, bz)]
    T = [(-tx, Hh, -tz), (tx, Hh, -tz), (tx, Hh, tz), (-tx, Hh, tz)]
    for i in range(4):
        j = (i + 1) % 4
        p = [B[i], B[j], T[j], T[i]]
        n = tri_normal(p[0], p[1], p[2])
        c = [sum(q[k] for q in p) / 4 for k in range(3)]
        if n[0] * c[0] + n[2] * c[2] < 0:  # outward
            p = [p[1], p[0], p[3], p[2]]
        u0 = 0.0 if i % 2 == 0 else 0.5  # faces 0 and 2 are the wide (front/back) faces
        quad(p, [(u0, 0), (u0 + 0.5, 0), (u0 + 0.5, 1), (u0, 1)])
    seg, hw, rise = 20, 0.45, 1.8
    for k in range(seg):
        a0, a1 = math.pi * k / seg, math.pi * (k + 1) / seg
        x0, y0 = -tx * 0.85 * math.cos(a0), Hh + rise * math.sin(a0)
        x1, y1 = -tx * 0.85 * math.cos(a1), Hh + rise * math.sin(a1)
        n0 = normalize3((-math.cos(a0) / tx, math.sin(a0) / rise, 0.0))
        n1 = normalize3((-math.cos(a1) / tx, math.sin(a1) / rise, 0.0))
        base = len(verts)
        for q, n, t in (((x0, y0, -hw), n0, (0.25, 0.01)), ((x1, y1, -hw), n1, (0.25, 0.01)),
                        ((x1, y1, hw), n1, (0.25, 0.02)), ((x0, y0, hw), n0, (0.25, 0.02))):
            verts.append(q)
            norms.append(n)
            uvs.append(t)
        faces.extend([(base, base + 1, base + 2), (base, base + 2, base + 3)])
    return fix_winding((verts, norms, uvs, faces))


def cap_mesh(hx=1.4, hy=0.84, hz=1.4, cells=6, tilt_deg=18.0):
    """Crystal cube with deep diagonal cuts. The geometry is a closed box; each face is
    divided into diagonal bands whose flat shading normals tilt alternately by +-18
    degrees (V-grooves), so refraction and reflection sparkle like cut glass."""
    verts, norms, uvs, faces = [], [], [], []
    th = math.radians(tilt_deg)
    # (centre, axis_u, axis_v) for each face; outward normal = axis_u x axis_v
    face_defs = [
        ((0, 0, -hz), (hx, 0, 0), (0, hy, 0)), ((0, 0, hz), (-hx, 0, 0), (0, hy, 0)),
        ((-hx, 0, 0), (0, 0, -hz), (0, hy, 0)), ((hx, 0, 0), (0, 0, hz), (0, hy, 0)),
        ((0, hy, 0), (hx, 0, 0), (0, 0, hz)), ((0, -hy, 0), (hx, 0, 0), (0, 0, -hz)),
    ]
    for c, eu, ev in face_defs:
        n0 = normalize3(tri_normal((0, 0, 0), eu, ev))
        if sum(n0[k] * c[k] for k in range(3)) < 0:
            n0 = tuple(-x for x in n0)
        uhat, vhat = normalize3(eu), normalize3(ev)
        b = normalize3(tuple(uhat[k] - vhat[k] for k in range(3)))  # across the diagonal bands
        for i in range(cells):
            for j in range(cells):
                def P(ii, jj):
                    su, sv = -1 + 2 * ii / cells, -1 + 2 * jj / cells
                    return tuple(c[k] + su * eu[k] + sv * ev[k] for k in range(3))
                for tri, m in ((((i, j), (i + 1, j), (i, j + 1)), i + j), (((i + 1, j), (i + 1, j + 1), (i, j + 1)), i + j + 1)):
                    sgn = 1 if m % 2 == 0 else -1
                    n = normalize3(tuple(n0[k] * math.cos(th) + sgn * b[k] * math.sin(th) for k in range(3)))
                    base = len(verts)
                    for (ii, jj) in tri:
                        verts.append(P(ii, jj))
                        norms.append(n)
                        uvs.append((ii / cells, jj / cells))
                    faces.append((base, base + 1, base + 2))
    return fix_winding((verts, norms, uvs, faces))


# ---------------------------------------------------------------- pbrt text helpers
def fmt(v):
    s = "%.4f" % v
    s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def box(lo, hi, uv_scale=1.0):
    """Closed axis-aligned box as a trianglemesh: outward winding, per-face UVs."""
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    fs = [[(x0, y0, z1), (x0, y0, z0), (x0, y1, z0), (x0, y1, z1)],
          [(x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0)],
          [(x0, y0, z1), (x1, y0, z1), (x1, y0, z0), (x0, y0, z0)],
          [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)],
          [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)],
          [(x1, y0, z1), (x0, y0, z1), (x0, y1, z1), (x1, y1, z1)]]
    centre = [(lo[k] + hi[k]) / 2 for k in range(3)]
    P, UV, I = [], [], []
    for f in fs:
        n = tri_normal(f[0], f[1], f[2])
        fc = [sum(p[k] for p in f) / 4 for k in range(3)]
        if sum(n[k] * (fc[k] - centre[k]) for k in range(3)) < 0:
            f = [f[1], f[0], f[3], f[2]]
        span = [max(p[k] for p in f) - min(p[k] for p in f) for k in range(3)]
        dims = sorted([s for s in span if s > 0], reverse=True) + [1, 1]
        su, sv = dims[0] * uv_scale, dims[1] * uv_scale
        base = len(P)
        P.extend(f)
        UV.extend([(0, 0), (su, 0), (su, sv), (0, sv)])
        I.extend([base, base + 1, base + 2, base, base + 2, base + 3])
    return ('Shape "trianglemesh" "point3 P" [ ' + "  ".join(" ".join(fmt(c) for c in p) for p in P) +
            ' ]\n    "point2 uv" [ ' + "  ".join(" ".join(fmt(c) for c in t) for t in UV) +
            ' ]\n    "integer indices" [ ' + " ".join(str(i) for i in I) + ' ]\n')


def quad(p0, p1, p2, p3, uv=((0, 0), (1, 0), (1, 1), (0, 1))):
    return ('Shape "trianglemesh" "point3 P" [ ' + "  ".join(" ".join(fmt(c) for c in p) for p in (p0, p1, p2, p3)) +
            ' ]\n    "point2 uv" [ ' + "  ".join(" ".join(fmt(c) for c in t) for t in uv) +
            ' ] "integer indices" [ 0 1 2 0 2 3 ]\n')


def block(lines):
    return "".join(lines)


# ---------------------------------------------------------------- scene layout (measured on the photo)
# Our table: local frame with x from the left cushion line (0) to the right cushion line
# (48) and z from the near-end white strip (0) to the far-end cushion (65.8). In the world
# it is rotated by -36.5 deg about y and translated to (-7.49, 0, 4.18).
TABLE_T = (-7.49, 0.0, 4.18)
TABLE_ROT = -36.5
TABLE_W, TABLE_L = 48.0, 65.8

BALLS = [  # (x, z, texture)  centre height 1; colours follow the photograph (red/yellow/black/white)
    (-1.82, 23.19, "3"),          # front centre, between the bottle and the glass
    (0.25, 27.50, "9"),           # directly behind the glass (left)
    (2.35, 28.00, "8"),           # directly behind the glass (right)
    (5.19, 26.07, "11"),
    (5.88, 21.80, "1"),           # large, in front
    (10.03, 25.67, "15"),         # far right
    (9.43, 30.84, "cue"),         # cue ball
    (13.51, 42.86, "13"),         # back right
    (-5.71, 42.66, "7"),          # in the rack (moved 0.4 towards the centre: clears the bar)
    (-3.75, 44.60, "5"),          # in the rack
]
RACK_CENTROID, RACK_FRONT_ANGLE, RACK_CIRCUMRADIUS = (-4.52, 43.57), -78.5, 6.0
GLASS_POS, GLASS_SCALE = (1.2, 22.4), 1.18
PERFUME_POS, PERFUME_ROT = (-3.7, 19.3), 12.0
GRATER_POS, GRATER_ROT = (-8.72, 27.12), 20.4
CUE_TIP, CUE_BUTT = (8.60, 19.30), (-0.36, 80.40)
OTHER_TABLES = [((-7.04, 258.3), 38.6, 64.0, 34.0), ((66.5, 365.2), 47.6, 70.0, 36.0)]
SPOTS = [(10.0, 320.7), (35.2, 339.3), (65.0, 348.0), (111.6, 374.4), (150.9, 406.5),
         (-30.0, -25.0), (15.0, -30.0), (60.0, -20.0)]  # last three: behind the camera (seen in reflections)
CEILING_Y, FLOOR_Y = 70.0, -31.0


def table_block(local_lines, t, rot):
    return ('AttributeBegin\n  Translate %s 0 %s Rotate %s 0 1 0\n' % (fmt(t[0]), fmt(t[1]), fmt(rot)) +
            "".join("  " + l for l in local_lines) + "AttributeEnd\n")


def our_table():
    W, L = TABLE_W, TABLE_L
    out = []
    a = out.append
    a('AttributeBegin NamedMaterial "felt"\n  ' +
      quad((0, 0, 0), (0, 0, L), (W, 0, L), (W, 0, 0), ((0, 0), (0, L), (W, L), (W, 0))) + "AttributeEnd\n")
    a('AttributeBegin NamedMaterial "cushion"\n')
    for lo, hi in (((0, 0, 0), (W, 1.3, 1.3)), ((0, 0, L - 1.3), (W, 1.3, L)),
                   ((0, 0, 0), (1.3, 1.3, L)), ((W - 1.3, 0, 0), (W, 1.3, L))):
        a("  " + box(lo, hi))
    a("AttributeEnd\n")
    a('AttributeBegin NamedMaterial "whitestrip"\n')
    for lo, hi in (((-0.3, 1.45, -0.3), (W + 0.3, 1.53, 0)), ((W, 1.45, -0.3), (W + 0.3, 1.53, L + 0.3)),
                   ((-0.3, 1.45, L), (W + 0.3, 1.53, L + 0.3)), ((-0.3, 1.45, -0.3), (0, 1.53, L + 0.3))):
        a("  " + box(lo, hi))
    a("AttributeEnd\n")
    a('AttributeBegin NamedMaterial "railblack"\n')
    for lo, hi in (((-4.6, -2.5, -4.6), (W + 4.6, 1.5, -0.3)), ((-4.6, -2.5, L + 0.3), (W + 4.6, 1.5, L + 4.6)),
                   ((-4.6, -2.5, -0.3), (-0.3, 1.5, L + 0.3)), ((W + 0.3, -2.5, -0.3), (W + 4.6, 1.5, L + 0.3))):
        a("  " + box(lo, hi, 0.5))
    a("AttributeEnd\n")
    a('AttributeBegin NamedMaterial "pocket"\n')
    for x, z in ((0, 0), (W, 0), (0, L), (W, L), (0, L / 2), (W, L / 2)):
        a("  " + box((x - 1.4, -0.4, z - 1.4), (x + 1.4, 1.36, z + 1.4)))
    a("AttributeEnd\n")
    a('AttributeBegin NamedMaterial "tablebody"\n  ' + box((-4.3, FLOOR_Y + 6, -4.3), (W + 4.3, -2.5, L + 4.3)) + "AttributeEnd\n")
    return table_block(out, TABLE_T, TABLE_ROT)


def other_table(origin, rot, W, L):
    out = [
        'AttributeBegin NamedMaterial "farfelt"\n  ' + quad((0, 0, 0), (0, 0, L), (W, 0, L), (W, 0, 0),
                                                             ((0, 0), (0, L), (W, L), (W, 0))) + "AttributeEnd\n",
        'AttributeBegin NamedMaterial "cushion"\n',
    ]
    for lo, hi in (((0, 0, 0), (W, 1.3, 1.3)), ((0, 0, L - 1.3), (W, 1.3, L)), ((0, 0, 0), (1.3, 1.3, L)),
                   ((W - 1.3, 0, 0), (W, 1.3, L))):
        out.append("  " + box(lo, hi))
    out.append("AttributeEnd\n")
    out.append('AttributeBegin NamedMaterial "railblack"\n')
    for lo, hi in (((-4, -3, -4), (W + 4, 1.5, 0)), ((-4, -3, L), (W + 4, 1.5, L + 4)),
                   ((-4, -3, 0), (0, 1.5, L)), ((W, -3, 0), (W + 4, 1.5, L))):
        out.append("  " + box(lo, hi, 0.5))
    out.append("AttributeEnd\n")
    out.append('AttributeBegin NamedMaterial "tablebody"\n  ' + box((-3.5, FLOOR_Y, -3.5), (W + 3.5, -3, L + 3.5)) +
               "AttributeEnd\n")
    return table_block(out, origin, rot)


def geometry_include():
    g = []
    a = g.append
    a("# Pool-hall geometry shared by WSRT_creative.pbrt and DRT_creative.pbrt\n"
      "# (generated by scenes/tools/make_poolroom.py -- edit the script, not this file).\n"
      "# Materials are named; their values come from poolhall_materials_wsrt/_drt.pbrt.\n\n")
    a('Texture "graterholes" "float" "imagemap" "string filename" "textures/grater_alpha.ppm" "string encoding" "linear"\n'
      '    "string wrap" "clamp"\n\n')
    a("# ---------------------------------------------------------------- room (dark pool hall)\n")
    a('AttributeBegin NamedMaterial "floor"\n  Shape "plane" "point3 p" [ 0 %s 0 ] "normal n" [ 0 1 0 ]\nAttributeEnd\n' % fmt(FLOOR_Y))
    a('AttributeBegin NamedMaterial "wall"\n')
    a("  " + quad((-220, FLOOR_Y, 470), (-220, CEILING_Y, 470), (260, CEILING_Y, 470), (260, FLOOR_Y, 470)))
    a("  " + quad((-220, FLOOR_Y, -40), (-220, FLOOR_Y, 470), (-220, CEILING_Y, 470), (-220, CEILING_Y, -40)))
    a("  " + quad((260, FLOOR_Y, 470), (260, FLOOR_Y, -40), (260, CEILING_Y, -40), (260, CEILING_Y, 470)))
    a("AttributeEnd\n")
    a('# the hall behind the camera (only seen in reflections)\nAttributeBegin NamedMaterial "backwall"\n  ' +
      quad((260, FLOOR_Y, -40), (-220, FLOOR_Y, -40), (-220, CEILING_Y, -40), (260, CEILING_Y, -40)) + "AttributeEnd\n")
    a('AttributeBegin NamedMaterial "ceiling"\n  ' +
      quad((-220, CEILING_Y, -40), (260, CEILING_Y, -40), (260, CEILING_Y, 470), (-220, CEILING_Y, 470)) + "AttributeEnd\n")
    a("# other pool tables in the hall (in shadow)\n")
    for origin, rot, W, L in OTHER_TABLES:
        a(other_table(origin, rot, W, L))
    a("\n# ---------------------------------------------------------------- our table\n")
    a(our_table())

    a("\n# ---------------------------------------------------------------- balls (spheres)\n")
    a("# Each ball is turned so that its number circle (u = %.3f) faces the camera, tipped up\n"
      "# towards it, with a little random yaw/tilt. Scale -1 1 1: pbrt's sphere (u,v) runs\n"
      "# right-to-left seen from outside; mirroring makes the textures read as authored.\n" % BALL_U_CENTRE)
    rnd = random.Random(42)
    phc = 2 * math.pi * BALL_U_CENTRE
    for x, z, tex in BALLS:
        dist = math.hypot(x - CAM_EYE[0], z - CAM_EYE[2])
        tilt = math.degrees(math.atan2(CAM_EYE[1] - 1, dist)) + rnd.uniform(-8, 8)
        t = math.radians(tilt)
        # circle centre (cos phc, sin phc, 0) after Scale(-1,1,1) and Rotate(-(90 + tilt)) about x:
        # (-cos phc, -sin phc sin t, -sin phc cos t); its horizontal direction is atan2(x, z)
        cx, cz = -math.cos(phc), -math.sin(phc) * math.cos(t)
        a0 = math.atan2(cx, cz)
        a_t = math.atan2(CAM_EYE[0] - x, CAM_EYE[2] - z)
        yaw = math.degrees(a_t - a0) + rnd.uniform(-20, 20)
        a('AttributeBegin Translate %s 1 %s Rotate %s 0 1 0 Rotate %s 1 0 0 Scale -1 1 1 NamedMaterial "ball_%s"\n'
          '  Shape "sphere" "float radius" [ 1 ]\nAttributeEnd\n' % (fmt(x), fmt(z), fmt(yaw), fmt(-(90 + tilt)), tex))

    a("\n# ---------------------------------------------------------------- triangle rack: three instances of one bar\n")
    side = RACK_CIRCUMRADIUS * math.sqrt(3)
    a('AttributeBegin\n  NamedMaterial "rack"\n  ObjectBegin "rackbar"\n    ' +
      box((-side / 2 - 0.35, 0, -0.35), (side / 2 + 0.35, 0.9, 0.35)).replace("\n", "\n    ").rstrip() +
      "\n  ObjectEnd\nAttributeEnd\n")
    cx, cz = RACK_CENTROID
    vtx = []
    for k in range(3):
        t = math.radians(RACK_FRONT_ANGLE + 120 * k)
        vtx.append((cx + RACK_CIRCUMRADIUS * math.cos(t), cz + RACK_CIRCUMRADIUS * math.sin(t)))
    for k in range(3):
        (x0, z0), (x1, z1) = vtx[k], vtx[(k + 1) % 3]
        mx, mz = (x0 + x1) / 2, (z0 + z1) / 2
        ang = math.degrees(math.atan2(-(z1 - z0), x1 - x0))  # Rotate about y maps x to (cos, 0, -sin)
        a('AttributeBegin Translate %s 0 %s Rotate %s 0 1 0 ObjectInstance "rackbar" AttributeEnd\n'
          % (fmt(mx), fmt(mz), fmt(ang)))

    a("\n# ---------------------------------------------------------------- glass of water (ribbed rim), two-thirds full\n")
    a('AttributeBegin\n  Translate %s 0 %s Scale %s %s %s\n' % (fmt(GLASS_POS[0]), fmt(GLASS_POS[1]), GLASS_SCALE, GLASS_SCALE, GLASS_SCALE) +
      '  AttributeBegin NamedMaterial "glass" Shape "objmesh" "string filename" "meshes/glass.obj" AttributeEnd\n'
      '  AttributeBegin NamedMaterial "water" Shape "objmesh" "string filename" "meshes/water.obj" AttributeEnd\n'
      'AttributeEnd\n')

    a("\n# ---------------------------------------------------------------- perfume bottle\n")
    bh, bw = 2.3, 1.38
    a('AttributeBegin\n  Translate %s 0 %s Rotate %s 0 1 0\n' % (fmt(PERFUME_POS[0]), fmt(PERFUME_POS[1]), fmt(PERFUME_ROT)))
    a('  AttributeBegin NamedMaterial "bottleglass"\n    ' + box((-bw, 0, -bw), (bw, bh, bw)).replace("\n", "\n    ").rstrip() + "\n  AttributeEnd\n")
    a('  AttributeBegin NamedMaterial "perfume"\n    ' + box((-bw + 0.2, 0.3, -bw + 0.2), (bw - 0.2, bh - 0.22, bw - 0.2)).replace("\n", "\n    ").rstrip() + "\n  AttributeEnd\n")
    a('  AttributeBegin NamedMaterial "collar"\n    ' + box((-0.85, bh, -0.85), (0.85, bh + 0.12, 0.85)).replace("\n", "\n    ").rstrip() + "\n  AttributeEnd\n")
    a('  AttributeBegin Translate 0 %s 0 NamedMaterial "crystal" Shape "objmesh" "string filename" "meshes/cap.obj" AttributeEnd\n'
      % fmt(bh + 0.12 + 0.84))
    a('  AttributeBegin NamedMaterial "label"\n    ' +
      quad((-0.5, 0.75, -bw - 0.006), (0.5, 0.75, -bw - 0.006), (0.5, 1.55, -bw - 0.006), (-0.5, 1.55, -bw - 0.006)).replace("\n", "\n    ").rstrip() +
      "\n  AttributeEnd\nAttributeEnd\n")

    a("\n# ---------------------------------------------------------------- stainless steel box grater (holes = alpha cut-outs)\n")
    a('AttributeBegin\n  Translate %s 0 %s Rotate %s 0 1 0\n  NamedMaterial "metal"\n'
      '  Shape "objmesh" "string filename" "meshes/grater.obj" "texture alpha" "graterholes"\nAttributeEnd\n'
      % (fmt(GRATER_POS[0]), fmt(GRATER_POS[1]), fmt(GRATER_ROT)))

    a("\n# ---------------------------------------------------------------- cue lying on the felt (tip near, dark butt far)\n")
    dx, dz = CUE_BUTT[0] - CUE_TIP[0], CUE_BUTT[1] - CUE_TIP[1]
    Lc = math.hypot(dx, dz)
    theta = math.degrees(math.atan2(-dz, dx))
    tip_r, butt_r = 0.25, 0.47
    sr = tip_r / 0.16
    tilt = math.degrees(math.asin((butt_r - tip_r) / Lc))
    a('AttributeBegin\n  Translate %s %s %s Rotate %s 0 1 0 Rotate %s 0 0 1 Rotate -90 0 0 1 Scale %s %s %s\n'
      % (fmt(CUE_TIP[0]), fmt(tip_r), fmt(CUE_TIP[1]), fmt(theta), fmt(tilt), fmt(sr), fmt(Lc / 14.0), fmt(sr)))
    for part, mat in (("cue_leather", "cueleather"), ("cue_ferrule", "cueferrule"), ("cue_shaft", "cuewood"), ("cue_butt", "cuebutt")):
        a('  AttributeBegin NamedMaterial "%s" Shape "objmesh" "string filename" "meshes/%s.obj" AttributeEnd\n' % (mat, part))
    a("AttributeEnd\n")
    os.makedirs(INC, exist_ok=True)
    with open(os.path.join(INC, "poolhall_geometry.pbrt"), "w") as f:
        f.write("".join(g))
    print("wrote scenes/include/poolhall_geometry.pbrt")


def textures_block():
    return ('Texture "felt" "spectrum" "imagemap" "string filename" "textures/felt.ppm" "float uscale" [ 0.08 ] "float vscale" [ 0.08 ]\n'
            'Texture "railblack" "spectrum" "imagemap" "string filename" "textures/railblack.ppm" "float uscale" [ 0.3 ] "float vscale" [ 0.3 ]\n'
            'Texture "floorwood" "spectrum" "imagemap" "string filename" "textures/wood.ppm" "float uscale" [ 0.02 ] "float vscale" [ 0.006 ] "float scale" [ 0.5 ]\n'
            'Texture "metal" "spectrum" "imagemap" "string filename" "textures/metal.ppm" "float scale" [ 0.35 ]\n'
            'Texture "cuewood" "spectrum" "imagemap" "string filename" "textures/wood.ppm" "float uscale" [ 1 ] "float vscale" [ 6 ] "float scale" [ 1.35 ]\n'
            'Texture "label" "spectrum" "imagemap" "string filename" "textures/label.ppm" "string wrap" "clamp"\n' +
            "".join('Texture "tex_ball_%s" "spectrum" "imagemap" "string filename" "textures/ball_%s.ppm" "float scale" [ 0.85 ]\n'
                    % (t, t) for t in sorted({b[2] for b in BALLS}, key=str)) + "\n")


def materials_include(name, mats, header):
    lines = [header, textures_block()]
    for mname, mtype, params in mats:
        lines.append('MakeNamedMaterial "%s" "string type" "%s" %s\n' % (mname, mtype, params))
    with open(os.path.join(INC, name), "w") as f:
        f.write("".join(lines))
    print("wrote scenes/include/" + name)


def materials():
    # Phong-family materials: the WSRT evaluates normalised Blinn-Phong (Kd/pi diffuse,
    # (n+8)/(8 pi) specular) for these; the DRT the energy-conserving Phong BRDF.
    common = [
        ("glass", "dielectric", '"float eta" [ 1.5 ]'),
        ("water", "dielectric", '"float eta" [ 1.33 ]'),
        ("crystal", "dielectric", '"float eta" [ 1.55 ]'),
        ("bottleglass", "dielectric", '"float eta" [ 1.5 ] "rgb Kt" [ 0.78 0.74 0.45 ]'),
        ("perfume", "dielectric", '"float eta" [ 1.4 ] "rgb Kt" [ 0.6 0.34 0.09 ]'),
    ]
    def bp(kd, ks, n, ka="0.1 0.1 0.1", kr=None, tex=False):
        s = ('"texture Kd" "%s"' % kd) if tex else ('"rgb Kd" [ %s ]' % kd)
        s += ' "rgb Ks" [ %s ] "float shininess" [ %s ] "rgb Ka" [ %s ] "bool normalized" true' % (ks, n, ka)
        if kr:
            s += ' "rgb Kr" [ %s ]' % kr
        return s
    wsrt = common + [
        ("felt", "blinnphong", bp("felt", "0.02 0.02 0.02", 8, tex=True)),
        ("farfelt", "blinnphong", bp("felt", "0.02 0.02 0.02", 8, tex=True)),
        ("cushion", "blinnphong", bp("0.03 0.3 0.08", "0.03 0.03 0.03", 10)),
        ("whitestrip", "blinnphong", bp("0.85 0.85 0.85", "0.05 0.05 0.05", 30)),
        ("railblack", "blinnphong", bp("railblack", "0.03 0.03 0.03", 20, "0.08 0.08 0.08", tex=True)),
        ("pocket", "blinnphong", bp("0.01 0.01 0.01", "0.1 0.1 0.1", 40)),
        ("tablebody", "blinnphong", bp("0.02 0.02 0.02", "0.05 0.05 0.05", 30, "0.05 0.05 0.05")),
        ("floor", "blinnphong", bp("floorwood", "0.04 0.04 0.04", 20, "0.06 0.06 0.06", tex=True)),
        ("wall", "blinnphong", bp("0.05 0.05 0.055", "0 0 0", 1, "0.05 0.05 0.05")),
        ("backwall", "blinnphong", bp("0.35 0.34 0.33", "0 0 0", 1, "0.6 0.6 0.6")),
        ("ceiling", "blinnphong", bp("0.03 0.03 0.03", "0 0 0", 1, "0.05 0.05 0.05")),
        ("spot", "blinnphong", '"rgb Kd" [ 1 1 1 ] "rgb Ka" [ 1 1 0.95 ] "bool normalized" true'),
    ] + [("ball_" + t, "blinnphong", bp("tex_ball_" + t, "0.35 0.35 0.35", 600, kr="0.05 0.05 0.05", tex=True))
         for t in sorted({b[2] for b in BALLS}, key=str)] + [
        ("rack", "blinnphong", bp("0.015 0.015 0.015", "0.3 0.3 0.3", 150, kr="0.04 0.04 0.04")),
        ("collar", "blinnphong", bp("0.35 0.27 0.09", "0.4 0.34 0.18", 200, kr="0.2 0.17 0.07")),
        ("label", "blinnphong", bp("label", "0.05 0.05 0.05", 30, tex=True)),
        ("metal", "blinnphong", bp("metal", "0.15 0.15 0.15", 400, "0.06 0.06 0.06", kr="0.75 0.75 0.77", tex=True)),
        ("cueleather", "blinnphong", bp("0.04 0.06 0.12", "0.1 0.1 0.1", 30)),
        ("cueferrule", "blinnphong", bp("0.8 0.8 0.78", "0.15 0.15 0.15", 80)),
        ("cuewood", "blinnphong", bp("cuewood", "0.2 0.2 0.2", 120, tex=True)),
        ("cuebutt", "blinnphong", bp("0.035 0.025 0.02", "0.35 0.35 0.35", 200, "0.05 0.05 0.05")),
    ]
    materials_include("poolhall_materials_wsrt.pbrt", wsrt,
                      "# Materials for WSRT_creative (normalised Blinn-Phong; generated by make_poolroom.py)\n")
    def ph(kd, ks, n, kr=None, tex=False):
        s = ('"texture Kd" "%s"' % kd) if tex else ('"rgb Kd" [ %s ]' % kd)
        s += ' "rgb Ks" [ %s ] "float exponent" [ %s ]' % (ks, n)
        if kr:
            s += ' "rgb Kr" [ %s ]' % kr
        return s
    drt = common + [
        ("felt", "phong", ph("felt", "0.02 0.02 0.02", 8, tex=True)),
        ("farfelt", "phong", ph("felt", "0.02 0.02 0.02", 8, tex=True)),
        ("cushion", "phong", ph("0.03 0.3 0.08", "0.03 0.03 0.03", 10)),
        ("whitestrip", "phong", ph("0.85 0.85 0.85", "0.05 0.05 0.05", 30)),
        ("railblack", "phong", ph("railblack", "0.02 0.02 0.02", 20, tex=True)),
        ("pocket", "phong", ph("0.01 0.01 0.01", "0.1 0.1 0.1", 40)),
        ("tablebody", "phong", ph("0.02 0.02 0.02", "0.05 0.05 0.05", 30)),
        ("floor", "phong", ph("floorwood", "0.04 0.04 0.04", 20, tex=True)),
        ("wall", "diffuse", '"rgb reflectance" [ 0.05 0.05 0.055 ]'),
        ("backwall", "diffuse", '"rgb reflectance" [ 0.35 0.34 0.33 ]'),
        ("ceiling", "diffuse", '"rgb reflectance" [ 0.03 0.03 0.03 ]'),
        ("spot", "diffuse", '"rgb reflectance" [ 0.8 0.8 0.8 ]'),
    ] + [  # clear coat as an ideal mirror (Kr) + a broader Phong lobe for the light highlights
        ("ball_" + t, "phong", ph("tex_ball_" + t, "0.15 0.15 0.15", 80, kr="0.06 0.06 0.06", tex=True))
        for t in sorted({b[2] for b in BALLS}, key=str)] + [
        ("rack", "phong", ph("0.015 0.015 0.015", "0.25 0.25 0.25", 100, kr="0.03 0.03 0.03")),
        ("collar", "phong", ph("0.3 0.24 0.08", "0.3 0.26 0.14", 120, kr="0.2 0.17 0.07")),
        ("label", "phong", ph("label", "0.05 0.05 0.05", 30, tex=True)),
        ("metal", "phong", ph("metal", "0.1 0.1 0.1", 300, kr="0.75 0.75 0.77", tex=True)),
        ("cueleather", "phong", ph("0.04 0.06 0.12", "0.1 0.1 0.1", 30)),
        ("cueferrule", "phong", ph("0.8 0.8 0.78", "0.15 0.15 0.15", 80)),
        ("cuewood", "phong", ph("cuewood", "0.15 0.15 0.15", 80, tex=True)),
        ("cuebutt", "phong", ph("0.035 0.025 0.02", "0.3 0.3 0.3", 150)),
    ]
    materials_include("poolhall_materials_drt.pbrt", drt,
                      "# Materials for DRT_creative (energy-conserving Phong BRDF; generated by make_poolroom.py)\n")


def spots():
    w = ["# Ceiling spots for the WSRT: bright self-coloured discs (ambient term only), so that\n"
         "# they show in the image without adding extra shadow-casting lights.\n"]
    d = ["# Ceiling spots for the DRT: small emissive discs. \"samples 0\": visible and emitting, but\n"
         "# not sampled with shadow rays (they add < 0.1 % of the light; sampling them cost half of\n"
         "# all shadow rays). Their light still reaches the scene through paths that hit them.\n"]
    for x, z in SPOTS:
        w.append('AttributeBegin Translate %s %s %s Rotate 90 1 0 0 NamedMaterial "spot" Shape "disk" "float radius" [ 1.6 ] AttributeEnd\n'
                 % (fmt(x), fmt(CEILING_Y - 0.1), fmt(z)))
        d.append('AttributeBegin Translate %s %s %s Rotate 90 1 0 0 NamedMaterial "spot"\n'
                 '  AreaLightSource "diffuse" "blackbody L" [ 3500 ] "float scale" [ 40 ] "integer samples" [ 0 ]\n'
                 '  Shape "disk" "float radius" [ 1.6 ]\nAttributeEnd\n' % (fmt(x), fmt(CEILING_Y - 0.1), fmt(z)))
    for name, lines in (("poolhall_spots_wsrt.pbrt", w), ("poolhall_spots_drt.pbrt", d)):
        with open(os.path.join(INC, name), "w") as f:
            f.write("".join(lines))
        print("wrote scenes/include/" + name)


def main():
    import sys
    names = list(BALL_STYLES) if "--all" in sys.argv else sorted({b[2] for b in BALLS}, key=str)
    for n in names:
        ball_texture(n)
    felt_texture()
    railblack_texture()
    metal_texture()
    grater_alpha_texture()
    label_texture()
    write_obj("glass.obj", glass_mesh(), "thick-walled glass tumbler, ribbed below the rim")
    write_obj("water.obj", water_mesh(), "water inside the tumbler (two-thirds full)")
    write_obj("cap.obj", cap_mesh(), "faceted crystal cap")
    write_obj("grater.obj", grater_mesh(), "box grater sleeve with handle")
    cue_meshes()
    geometry_include()
    materials()
    spots()
    print("camera: " + camera_lookat() + '  Camera "perspective" "float fov" [ %s ]' % CAM_FOV)


if __name__ == "__main__":
    main()
