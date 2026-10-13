#!/usr/bin/env python3
"""Assets for the billiards creative scenes (Python 3 standard library only).

Textures (scenes/textures/):  ball_1/9/11/12.ppm (equirectangular, numbered), felt.ppm
Meshes   (scenes/meshes/):    glass.obj (thick-walled tumbler, closed solid), water.obj,
                              cue_shaft.obj, cue_tip.obj  -- all with normals and UVs.

Sphere UV convention of the renderer (pbrt): u = phi / 2pi around the pole axis (+z
in object space), v = 0 at the -z pole and 1 at the +z pole; image row 0 is v = 1.
"""
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(HERE, "..", "textures")
MESH = os.path.join(HERE, "..", "meshes")

FONT = {  # 5 x 7 bitmap digits
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
}


def write_ppm(name, w, h, pixels):
    os.makedirs(TEX, exist_ok=True)
    with open(os.path.join(TEX, name), "wb") as f:
        f.write(b"P6\n%d %d\n255\n" % (w, h))
        f.write(bytes(max(0, min(255, int(round(c)))) for px in pixels for c in px))
    print("wrote scenes/textures/" + name)


# ------------------------------------------------------------------ ball textures
def ball_texture(number, color, stripe):
    W, H = 512, 256
    white = (240, 236, 222)
    black = (25, 25, 25)
    text = str(number)
    rc = 0.30  # number circle angular radius (radians)
    glyph_h = 1.05 * rc  # digit height (radians)
    cell = glyph_h / 7.0
    glyph_w = 5 * cell
    gap = 1.2 * cell
    total_w = len(text) * glyph_w + (len(text) - 1) * gap
    centres = (0.25, 0.75)  # u of the number circles (front and back)

    def colour_at(u, v):
        theta = math.pi * (1 - v)  # polar angle from +z pole (v=1)
        phi = 2 * math.pi * u
        # band / solid colour
        base = white
        if stripe:
            if abs(theta - math.pi / 2) < 0.62:
                base = color
        else:
            base = color
        # number circles (on the equator, both sides)
        for cu in centres:
            dphi = (phi - 2 * math.pi * cu + math.pi) % (2 * math.pi) - math.pi
            dth = theta - math.pi / 2
            # local tangent-plane coordinates (x right, y up) as seen from outside the
            # ball: increasing phi runs right-to-left there, hence x = -dphi
            x, y = -dphi, -dth
            if x * x + y * y < rc * rc:
                gx = x + total_w / 2
                gy = glyph_h / 2 - y
                for k, ch in enumerate(text):
                    ox = k * (glyph_w + gap)
                    lx, ly = gx - ox, gy
                    if 0 <= lx < glyph_w and 0 <= ly < glyph_h:
                        col, row = int(lx / cell), int(ly / cell)
                        if FONT[ch][row][col] == "1":
                            return black
                return white
        return base

    pixels = []
    ss = 3  # supersampling for smooth edges
    for py in range(H):
        for px in range(W):
            acc = [0.0, 0.0, 0.0]
            for sy in range(ss):
                for sx in range(ss):
                    u = (px + (sx + 0.5) / ss) / W
                    v = 1 - (py + (sy + 0.5) / ss) / H
                    c = colour_at(u, v)
                    for k in range(3):
                        acc[k] += c[k]
            pixels.append(tuple(a / (ss * ss) for a in acc))
    write_ppm("ball_%d.ppm" % number, W, H, pixels)


def felt_texture():
    rnd = random.Random(11)
    W = H = 256
    noise = [[rnd.random() for _ in range(W)] for _ in range(H)]
    pixels = []
    for y in range(H):
        for x in range(W):
            # tileable 3x3 blur of white noise -> fine cloth grain
            n = sum(noise[(y + dy) % H][(x + dx) % W] for dy in (-1, 0, 1) for dx in (-1, 0, 1)) / 9.0
            g = 0.85 + 0.3 * (n - 0.5)
            pixels.append((20 * g, 110 * g, 45 * g))
    write_ppm("felt.ppm", W, H, pixels)


# ------------------------------------------------------------------ lathe meshes
def lathe(profile, segments, smooth_angle_deg=35.0):
    """Revolves a 2D profile [(r, y), ...] about the y axis.

    The profile is split at sharp corners; inside each smooth run the normals are
    averaged, so curved parts shade smoothly and creases stay sharp. The outward
    side is to the right of the direction of travel (dr, dy) -> (dy, -dr).
    Returns (vertices, normals, uvs, faces) with faces as index triples.
    """
    edges = [(profile[i], profile[i + 1]) for i in range(len(profile) - 1)]
    enorm = []
    elen = []
    for (r0, y0), (r1, y1) in edges:
        dr, dy = r1 - r0, y1 - y0
        L = math.hypot(dr, dy)
        enorm.append((dy / L, -dr / L))
        elen.append(L)
    total = sum(elen)
    # split into runs at sharp corners
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
        # profile points of this run with per-point normals
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
                norms.append((nr * ca, ny, nr * sa))
                uvs.append((j / segments, vs[k]))
        n = len(pts)
        for j in range(segments):
            for k in range(n - 1):
                a = base + j * n + k
                b = base + (j + 1) * n + k
                c, d = b + 1, a + 1
                # winding chosen so that the geometric normal matches the outward side
                for tri in ((a, d, c), (a, c, b)):
                    p0, p1, p2 = (verts[t] for t in tri)
                    if (p1 == p0) or (p2 == p0) or (p1 == p2):
                        continue  # degenerate (on the axis)
                    faces.append(tri)
    return verts, norms, uvs, faces


def fix_winding(mesh):
    """Orients every triangle so its geometric normal agrees with its vertex normals."""
    verts, norms, uvs, faces = mesh
    out = []
    for a, b, c in faces:
        p0, p1, p2 = verts[a], verts[b], verts[c]
        e1 = [p1[i] - p0[i] for i in range(3)]
        e2 = [p2[i] - p0[i] for i in range(3)]
        n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        avg = [norms[a][i] + norms[b][i] + norms[c][i] for i in range(3)]
        if sum(n[i] * avg[i] for i in range(3)) < 0:
            out.append((a, c, b))
        else:
            out.append((a, b, c))
    return verts, norms, uvs, out


def write_obj(name, mesh, comment):
    verts, norms, uvs, faces = mesh
    os.makedirs(MESH, exist_ok=True)
    with open(os.path.join(MESH, name), "w") as f:
        f.write("# %s (generated by scenes/tools/make_billiards.py)\n" % comment)
        for v in verts:
            f.write("v %.6f %.6f %.6f\n" % v)
        for t in uvs:
            f.write("vt %.6f %.6f\n" % t)
        for n in norms:
            f.write("vn %.6f %.6f %.6f\n" % n)
        for a, b, c in faces:
            f.write("f %d/%d/%d %d/%d/%d %d/%d/%d\n" % (a + 1, a + 1, a + 1, b + 1, b + 1, b + 1, c + 1, c + 1, c + 1))
    print("wrote scenes/meshes/%s (%d triangles)" % (name, len(faces)))


def glass_profile():
    """Tumbler (units: ball radius = 1): outer radius 1.35, height 4.2, wall 0.08,
    thick 0.35 base, rounded rim. Closed profile from the axis at the bottom
    to the axis on top of the base; outward = away from the glass material."""
    R, H, t, b = 1.35, 4.2, 0.08, 0.35
    pts = [(0.0, 0.0), (R - 0.06, 0.0)]
    for k in range(1, 5):  # rounded bottom edge
        a = -math.pi / 2 + (math.pi / 2) * k / 4
        pts.append((R - 0.06 + 0.06 * math.cos(a), 0.06 + 0.06 * math.sin(a)))
    # slight taper: wider at the top
    pts.append((R + 0.05, H - t / 2))
    for k in range(1, 8):  # rounded rim (half circle)
        a = (math.pi) * k / 8
        pts.append((R + 0.05 - t / 2 + (t / 2) * math.cos(a), H - t / 2 + (t / 2) * math.sin(a)))
    pts.append((R + 0.05 - t, H - t / 2))
    pts.append((R - t, b))
    pts.append((0.0, b))
    return pts


def water_profile():
    # just inside the glass cavity (tiny gap so the two dielectrics do not coincide)
    R, t, b, level = 1.35, 0.08, 0.35, 2.9
    gap = 0.004
    r_bottom = R - t - gap
    r_top = r_bottom + 0.05 * (level - b) / (4.2 - b)  # follow the taper
    return [(0.0, b + gap), (r_bottom, b + gap), (r_top, level), (0.0, level)]


def cue_profiles():
    # along +y: tip at y = 0, shaft to y = 14 (radius 0.16 -> 0.30)
    tip = [(0.0, 0.0), (0.14, 0.0), (0.155, 0.12), (0.16, 0.55)]
    shaft = [(0.16, 0.55), (0.30, 14.0), (0.0, 14.0)]
    return tip, shaft


def main():
    for number, color, stripe in ((1, (235, 185, 20), False), (9, (235, 185, 20), True),
                                  (11, (170, 25, 30), True), (12, (85, 30, 120), True)):
        ball_texture(number, color, stripe)
    felt_texture()
    write_obj("glass.obj", fix_winding(lathe(glass_profile(), 64)), "thick-walled glass tumbler")
    write_obj("water.obj", fix_winding(lathe(water_profile(), 64)), "water inside the tumbler")
    tip, shaft = cue_profiles()
    write_obj("cue_tip.obj", fix_winding(lathe(tip, 32)), "cue tip and ferrule")
    write_obj("cue_shaft.obj", fix_winding(lathe(shaft, 32)), "cue shaft")


if __name__ == "__main__":
    main()
