#!/usr/bin/env python3
"""Assets for the pool-room creative scenes (Python 3 standard library only).

Recreates the Module 1 creative photograph: a pool table with red/yellow balls,
a glass of water, a steel box grater, a perfume bottle, a triangle rack and a cue,
in a dim pool hall with windows, ceiling spots and other tables behind.

Textures (scenes/textures/): felt.ppm, cueball.ppm, grater.ppm, label.ppm, railblack.ppm
Meshes   (scenes/meshes/):   glass.obj, water.obj, cue_tip.obj, cue_shaft.obj, grater.obj
Include  (scenes/include/):  poolroom_world.pbrt -- geometry and materials shared by
                             WSRT_creative.pbrt and DRT_creative.pbrt (lights are set
                             in those files).
Units: a pool ball has radius 1; y is up; the felt is at y = 0.
"""
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(HERE, "..", "textures")
MESH = os.path.join(HERE, "..", "meshes")
INC = os.path.join(HERE, "..", "include")


def write_ppm(name, w, h, pixels):
    os.makedirs(TEX, exist_ok=True)
    with open(os.path.join(TEX, name), "wb") as f:
        f.write(b"P6\n%d %d\n255\n" % (w, h))
        f.write(bytes(max(0, min(255, int(round(c)))) for px in pixels for c in px))
    print("wrote scenes/textures/" + name)


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



# ------------------------------------------------------------------ textures
def cueball_texture():
    """White cue ball with six red spots (training 'spot' ball): texture on a sphere."""
    W, H = 512, 256
    dirs = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
    rad = 0.16
    pixels = []
    for py in range(H):
        for px in range(W):
            acc = [0.0, 0.0, 0.0]
            for sy in range(2):
                for sx in range(2):
                    u = (px + (sx + 0.5) / 2) / W
                    v = 1 - (py + (sy + 0.5) / 2) / H
                    phi, theta = 2 * math.pi * u, math.pi * (1 - v)
                    d = (math.sin(theta) * math.cos(phi), math.sin(theta) * math.sin(phi), math.cos(theta))
                    spot = any(math.acos(max(-1, min(1, sum(a * b for a, b in zip(d, c))))) < rad for c in dirs)
                    col = (200, 20, 25) if spot else (238, 236, 228)
                    for k in range(3):
                        acc[k] += col[k] / 4
            pixels.append(acc)
    write_ppm("cueball.ppm", W, H, pixels)


def grater_texture():
    """Brushed steel with staggered oval holes (dark), used on the grater faces."""
    W, H = 256, 512
    rnd = random.Random(5)
    cols, rows = 5, 13
    pixels = []
    for y in range(H):
        for x in range(W):
            v = 205 + 12 * (rnd.random() - 0.5) + 6 * math.sin(y * 0.9)  # brushed streaks
            fy = (y + 0.5) / H * rows
            r = int(fy)
            off = 0.5 if r % 2 else 0.0
            fx = (x + 0.5) / W * cols + off
            cx, cy = math.floor(fx) + 0.5, r + 0.5
            dx, dy = (fx - cx) / 0.28, (fy - cy) / 0.22
            inside = 0.08 < (y + 0.5) / H < 0.94 and 0.06 < (x + 0.5) / W < 0.94
            if inside and dx * dx + dy * dy < 1:
                v = 25 if dy > -0.4 else 120  # hole, with a bright raised lip on top
            pixels.append((v, v, v * 1.01))
    write_ppm("grater.ppm", W, H, pixels)


def label_texture():
    """Green perfume label with a white border and abstract 'lettering' bars."""
    W, H = 256, 192
    rnd = random.Random(3)
    bars = []
    for row, (y0, y1, x0, x1) in enumerate([(30, 70, 70, 186), (86, 104, 40, 216), (114, 130, 40, 216),
                                            (146, 162, 78, 178)]):
        x = x0
        while x < x1:
            w = rnd.randint(6, 18)
            bars.append((x, min(x + w, x1), y0, y1))
            x += w + rnd.randint(3, 7)
    pixels = []
    for y in range(H):
        for x in range(W):
            col = (70, 150, 105)
            if x < 6 or x >= W - 6 or y < 6 or y >= H - 6:
                col = (235, 235, 225)
            elif x < 10 or x >= W - 10 or y < 10 or y >= H - 10:
                col = (70, 150, 105)
            elif x < 12 or x >= W - 12 or y < 12 or y >= H - 12:
                col = (220, 220, 210)
            for (a, b, c, d) in bars:
                if a <= x < b and c <= y < d:
                    col = (240, 240, 232)
            pixels.append(col)
    write_ppm("label.ppm", W, H, pixels)


def railblack_texture():
    """Black table frame with fine sparkles (as in the photograph)."""
    rnd = random.Random(9)
    W = H = 256
    pixels = []
    for _ in range(W * H):
        v = 18 + 10 * rnd.random()
        if rnd.random() < 0.02:
            v = 90 + 120 * rnd.random()
        pixels.append((v, v, v))
    write_ppm("railblack.ppm", W, H, pixels)


# ------------------------------------------------------------------ grater mesh
def grater_mesh():
    """Tapered four-sided box grater (flat faces, per-face UVs) with an arched handle."""
    verts, norms, uvs, faces = [], [], [], []
    bx, bz, tx, tz, Hh = 2.5, 1.4, 1.75, 1.0, 9.0

    def quad(p0, p1, p2, p3, n, uv=((0, 0), (1, 0), (1, 1), (0, 1))):
        base = len(verts)
        for p, t in zip((p0, p1, p2, p3), uv):
            verts.append(p)
            norms.append(n)
            uvs.append(t)
        faces.extend([(base, base + 1, base + 2), (base, base + 2, base + 3)])

    def nrm(a, b, c):
        e1 = [b[i] - a[i] for i in range(3)]
        e2 = [c[i] - a[i] for i in range(3)]
        n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        L = math.sqrt(sum(x * x for x in n))
        return tuple(x / L for x in n)

    B = [(-bx, 0, -bz), (bx, 0, -bz), (bx, 0, bz), (-bx, 0, bz)]
    T = [(-tx, Hh, -tz), (tx, Hh, -tz), (tx, Hh, tz), (-tx, Hh, tz)]
    for i in range(4):
        j = (i + 1) % 4
        p0, p1, p2, p3 = B[i], B[j], T[j], T[i]
        n = nrm(p0, p1, p2)
        c = [sum(p[k] for p in (p0, p1, p2, p3)) / 4 for k in range(3)]
        if n[0] * c[0] + n[2] * c[2] < 0:  # make it point outwards
            p0, p1, p2, p3 = p1, p0, p3, p2
            n = nrm(p0, p1, p2)
        quad(p0, p1, p2, p3, n)
    quad(T[0], T[3], T[2], T[1], (0, 1, 0), ((0, 0), (0, 0.15), (0.3, 0.15), (0.3, 0)))  # top lid
    quad(B[0], B[1], B[2], B[3], (0, -1, 0))  # bottom
    # handle: an arched strip over the top, along x
    seg, hw, rise = 20, 0.45, 1.7
    for k in range(seg):
        a0, a1 = math.pi * k / seg, math.pi * (k + 1) / seg
        pts = []
        for a in (a0, a1):
            x, y = -tx * 0.85 * math.cos(a), Hh + rise * math.sin(a)
            pts.append((x, y, a))
        (x0, y0, a0), (x1, y1, a1) = pts
        n0 = (-math.cos(a0) / tx, math.sin(a0) / rise, 0.0)
        n1 = (-math.cos(a1) / tx, math.sin(a1) / rise, 0.0)
        n0 = tuple(v / math.sqrt(sum(w * w for w in n0)) for v in n0)
        n1 = tuple(v / math.sqrt(sum(w * w for w in n1)) for v in n1)
        base = len(verts)
        for p, n, t in (((x0, y0, -hw), n0, (k / seg, 0)), ((x1, y1, -hw), n1, ((k + 1) / seg, 0)),
                        ((x1, y1, hw), n1, ((k + 1) / seg, 0.1)), ((x0, y0, hw), n0, (k / seg, 0.1))):
            verts.append(p)
            norms.append(n)
            uvs.append(t)
        faces.extend([(base, base + 1, base + 2), (base, base + 2, base + 3)])
    return fix_winding((verts, norms, uvs, faces))


# ------------------------------------------------------------------ shared world include
def fmt(v):
    return ("%.4f" % v).rstrip("0").rstrip(".") if "." in ("%.4f" % v) else "%d" % v


def box(lo, hi, uv_scale=1.0):
    """Closed axis-aligned box as a trianglemesh with outward winding and per-face UVs."""
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    faces = [  # 4 corners per face (orientation fixed below)
        [(x0, y0, z1), (x0, y0, z0), (x0, y1, z0), (x0, y1, z1)],  # -x
        [(x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0)],  # +x
        [(x0, y0, z1), (x1, y0, z1), (x1, y0, z0), (x0, y0, z0)],  # -y
        [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)],  # +y
        [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)],  # -z
        [(x1, y0, z1), (x0, y0, z1), (x0, y1, z1), (x1, y1, z1)],  # +z
    ]
    P, UV, I = [], [], []
    centre = [(lo[k] + hi[k]) / 2 for k in range(3)]
    for f in faces:
        # orient the face outwards: its normal must point away from the box centre
        e1 = [f[1][k] - f[0][k] for k in range(3)]
        e2 = [f[2][k] - f[0][k] for k in range(3)]
        n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        fc = [sum(p[k] for p in f) / 4 for k in range(3)]
        if sum(n[k] * (fc[k] - centre[k]) for k in range(3)) < 0:
            f = [f[1], f[0], f[3], f[2]]
        # extent of the face for the UV scale
        span = [max(p[k] for p in f) - min(p[k] for p in f) for k in range(3)]
        dims = sorted([s for s in span if s > 0], reverse=True) + [1, 1]
        su, sv = dims[0] * uv_scale, dims[1] * uv_scale
        base = len(P)
        P.extend(f)
        UV.extend([(0, 0), (su, 0), (su, sv), (0, sv)])
        I.extend([base, base + 1, base + 2, base, base + 2, base + 3])
    return ('Shape "trianglemesh"\n    "point3 P" [ ' + "  ".join(" ".join(fmt(c) for c in p) for p in P) + ' ]\n'
            '    "point2 uv" [ ' + "  ".join(" ".join(fmt(c) for c in t) for t in UV) + ' ]\n'
            '    "integer indices" [ ' + " ".join(str(i) for i in I) + ' ]\n')


def quad(p0, p1, p2, p3, uv=((0, 0), (1, 0), (1, 1), (0, 1))):
    """Single quad (two triangles). Corners counter-clockwise seen from the front side."""
    return ('Shape "trianglemesh" "point3 P" [ ' + "  ".join(" ".join(fmt(c) for c in p) for p in (p0, p1, p2, p3)) +
            ' ]\n    "point2 uv" [ ' + "  ".join(" ".join(fmt(c) for c in t) for t in uv) +
            ' ] "integer indices" [ 0 1 2 0 2 3 ]\n')


def world_include():
    W = []
    a = W.append
    a("# Pool-room world shared by WSRT_creative.pbrt and DRT_creative.pbrt\n"
      "# (generated by scenes/tools/make_poolroom.py -- edit the script, not this file).\n"
      "# Materials use the Phong family: the WSRT evaluates Blinn-Phong with these parameters,\n"
      "# the DRT the energy-conserving Phong BRDF. Lights are defined in the two scene files,\n"
      "# except the visible emitters of the room (windows, TV, ceiling spots) below.\n\n")
    a('Texture "felt" "spectrum" "imagemap" "string filename" "textures/felt.ppm" "float uscale" [ 0.35 ] "float vscale" [ 0.35 ]\n')
    a('Texture "railblack" "spectrum" "imagemap" "string filename" "textures/railblack.ppm" "float uscale" [ 0.25 ] "float vscale" [ 0.25 ]\n')
    a('Texture "floorwood" "spectrum" "imagemap" "string filename" "textures/wood.ppm" "float uscale" [ 0.05 ] "float vscale" [ 0.02 ]\n')
    a('Texture "cuewood" "spectrum" "imagemap" "string filename" "textures/wood.ppm" "float uscale" [ 1 ] "float vscale" [ 4 ]\n')
    a('Texture "grater" "spectrum" "imagemap" "string filename" "textures/grater.ppm" "float scale" [ 0.3 ]\n')
    a('Texture "label" "spectrum" "imagemap" "string filename" "textures/label.ppm" "string wrap" "clamp"\n')
    a('Texture "cueball" "spectrum" "imagemap" "string filename" "textures/cueball.ppm"\n\n')

    # ---------------- room
    a("# ---------------------------------------------------------------- room\n")
    a('AttributeBegin\n  Material "blinnphong" "texture Kd" "floorwood" "rgb Ks" [ 0.08 0.08 0.08 ] "float shininess" [ 20 ] "rgb Ka" [ 0.06 0.06 0.06 ]\n'
      '  Shape "plane" "point3 p" [ 0 -28 0 ] "normal n" [ 0 1 0 ]\nAttributeEnd\n')
    a('AttributeBegin\n  Material "blinnphong" "rgb Kd" [ 0.07 0.07 0.08 ] "rgb Ka" [ 0.05 0.05 0.05 ]\n')
    a("  " + quad((-120, -28, 95), (-120, 55, 95), (120, 55, 95), (120, -28, 95)))  # back wall (faces -z)
    a("  " + quad((-75, -28, -60), (-75, -28, 95), (-75, 55, 95), (-75, 55, -60)))  # left wall
    a("  " + quad((-120, 55, -60), (-120, 55, 95), (120, 55, 95), (120, 55, -60)))  # ceiling (faces -y)
    a("AttributeEnd\n")
    # window frames: dark mullions in front of the window panes
    a('# daylight windows on the back wall (one-sided emitters facing the room)\n')
    for x0, x1 in ((0, 32), (40, 72)):
        a('AttributeBegin\n  AreaLightSource "diffuse" "rgb L" [ 1.6 1.75 1.95 ] "integer samples" [ 2 ]\n')
        a("  " + quad((x0, 6, 94.9), (x0, 20, 94.9), (x1, 20, 94.9), (x1, 6, 94.9)))
        a("AttributeEnd\n")
        a('AttributeBegin\n  Material "blinnphong" "rgb Kd" [ 0.02 0.02 0.02 ]\n')
        for k in range(1, 4):
            xm = x0 + (x1 - x0) * k / 4
            a("  " + box((xm - 0.5, 6, 94.2), (xm + 0.5, 20, 94.8)))
        a("  " + box((x0, 12.5, 94.2), (x1, 13.5, 94.8)))
        a("AttributeEnd\n")
    a('# TV screen (purple) on the back wall, left\nAttributeBegin\n  AreaLightSource "diffuse" "rgb L" [ 1.1 0.25 1.4 ] "integer samples" [ 1 ]\n')
    a("  " + quad((-48, 4, 94.9), (-48, 18, 94.9), (-24, 18, 94.9), (-24, 4, 94.9)))
    a("AttributeEnd\n")
    a('# ceiling spot lights (small discs facing down)\n')
    for x, z in ((-25, 55), (5, 70), (35, 50), (62, 78), (-50, 30)):
        a('AttributeBegin\n  Translate %s 54.8 %s Rotate 90 1 0 0\n  AreaLightSource "diffuse" "rgb L" [ 40 36 30 ] "integer samples" [ 1 ]\n'
          '  Shape "disk" "float radius" [ 0.8 ]\nAttributeEnd\n' % (x, z))
    # background pool tables
    a("# other pool tables in the hall\n")
    for (cx, cz, hw, hl) in ((8, 68, 12, 7), (52, 62, 14, 8)):
        a('AttributeBegin\n  Material "blinnphong" "rgb Kd" [ 0.03 0.03 0.035 ] "rgb Ks" [ 0.15 0.15 0.15 ] "float shininess" [ 40 ] "rgb Ka" [ 0.05 0.05 0.05 ]\n')
        a("  " + box((cx - hw, -28, cz - hl), (cx + hw, -6, cz + hl)))
        a('  Material "blinnphong" "texture Kd" "felt" "rgb Ka" [ 0.08 0.08 0.08 ]\n')
        a("  " + quad((cx - hw + 1.5, -5.99, cz - hl + 1.5), (cx - hw + 1.5, -5.99, cz + hl - 1.5),
                      (cx + hw - 1.5, -5.99, cz + hl - 1.5), (cx + hw - 1.5, -5.99, cz - hl + 1.5)))
        a("AttributeEnd\n")

    # ---------------- our table
    a("\n# ---------------------------------------------------------------- the table\n")
    a('AttributeBegin\n  Material "blinnphong" "texture Kd" "felt" "rgb Ks" [ 0.02 0.02 0.02 ] "float shininess" [ 8 ] "rgb Ka" [ 0.08 0.08 0.08 ]\n')
    a("  " + quad((-14, 0, -8), (-14, 0, 40), (14, 0, 40), (14, 0, -8), ((0, 0), (0, 48), (28, 48), (28, 0))))
    a("AttributeEnd\n")
    a('# green cushions\nAttributeBegin\n  Material "blinnphong" "rgb Kd" [ 0.03 0.32 0.1 ] "rgb Ks" [ 0.04 0.04 0.04 ] "float shininess" [ 10 ] "rgb Ka" [ 0.08 0.08 0.08 ]\n')
    for lo, hi in (((-14, 0, -9.2), (14, 1.25, -8)), ((-14, 0, 40), (14, 1.25, 41.2)),
                   ((-15.2, 0, -9.2), (-14, 1.25, 41.2)), ((14, 0, -9.2), (15.2, 1.25, 41.2))):
        a("  " + box(lo, hi))
    a("AttributeEnd\n")
    a('# pockets (black)\nAttributeBegin\n  Material "blinnphong" "rgb Kd" [ 0.01 0.01 0.01 ] "rgb Ks" [ 0.2 0.2 0.2 ] "float shininess" [ 30 ]\n')
    for x, z in ((-15.2, -9.2), (13.4, -9.2), (-15.2, 39.4), (13.4, 39.4), (-15.2, 15.1), (13.4, 15.1)):
        a("  " + box((x, 0, z), (x + 1.8, 1.4, z + 1.8)))
    a("AttributeEnd\n")
    a('# sparkly black frame, with a thin white edge line, and the table body\nAttributeBegin\n'
      '  Material "blinnphong" "texture Kd" "railblack" "rgb Ks" [ 0.02 0.02 0.02 ] "float shininess" [ 30 ] "rgb Ka" [ 0.06 0.06 0.06 ]\n')
    for lo, hi in (((-17.5, -1.5, -12.5), (17.5, 1.5, -9.2)), ((-17.5, -1.5, 41.2), (17.5, 1.5, 44.5)),
                   ((-17.5, -1.5, -9.2), (-15.2, 1.5, 41.2)), ((15.2, -1.5, -9.2), (17.5, 1.5, 41.2))):
        a("  " + box(lo, hi))
    a('  Material "blinnphong" "rgb Kd" [ 0.02 0.02 0.025 ] "rgb Ka" [ 0.04 0.04 0.04 ]\n')
    a("  " + box((-17, -26, -12), (17, -1.5, 44)))
    a('  Material "blinnphong" "rgb Kd" [ 0.85 0.85 0.85 ] "rgb Ka" [ 0.1 0.1 0.1 ]\n')
    a("  " + box((-17.5, 1.5, -9.55), (17.5, 1.56, -9.25)))
    a("  " + box((15.25, 1.5, -9.2), (15.55, 1.56, 41.2)))
    a("AttributeEnd\n")

    # ---------------- balls (spheres)
    a("\n# ---------------------------------------------------------------- balls (spheres)\n")
    red = '"rgb Kd" [ 0.62 0.03 0.03 ]'
    yel = '"rgb Kd" [ 0.66 0.42 0.02 ]'
    blk = '"rgb Kd" [ 0.015 0.015 0.015 ]'
    gloss = '"rgb Ks" [ 0.2 0.2 0.2 ] "float shininess" [ 120 ] "rgb Ka" [ 0.1 0.1 0.1 ] "rgb Kr" [ 0.04 0.04 0.04 ]'
    balls = [(-1.4, -0.6, red), (0.9, 2.0, yel), (3.6, 2.6, blk), (6.2, 1.2, red), (6.8, -2.5, yel),
             (11.4, 0.2, red), (11.0, 12.0, yel), (-2.6, 10.6, red), (0.4, 10.2, yel)]
    for x, z, kd in balls:
        a('AttributeBegin\n  Translate %s 1 %s\n  Material "blinnphong" %s %s\n  Shape "sphere" "float radius" [ 1 ]\nAttributeEnd\n'
          % (fmt(x), fmt(z), kd, gloss))
    a('# spotted cue ball: UV-mapped texture on a sphere\nAttributeBegin\n  Translate 9.8 1 5.0  Rotate 35 0 1 0  Rotate -70 1 0 0\n'
      '  Material "blinnphong" "texture Kd" "cueball" %s\n  Shape "sphere" "float radius" [ 1 ]\nAttributeEnd\n' % gloss)

    # ---------------- triangle rack (object instancing of one bar)
    a("\n# ---------------------------------------------------------------- triangle rack (3 instances of one bar)\n")
    a('AttributeBegin\n  Material "blinnphong" "rgb Kd" [ 0.02 0.02 0.02 ] "rgb Ks" [ 0.35 0.35 0.35 ] "float shininess" [ 90 ] "rgb Ka" [ 0.05 0.05 0.05 ]\n'
      '  ObjectBegin "rackbar"\n    ' + box((-4.6, 0, -0.35), (4.6, 0.9, 0.35)).replace("\n", "\n    ").rstrip() + "\n  ObjectEnd\nAttributeEnd\n")
    # equilateral triangle centred at (-1.1, 10.4), apex towards +x (right)
    cx, cz, ri = -1.1, 10.3, 2.75  # inradius of the bar centre lines
    for ang in (90, 210, 330):
        t = math.radians(ang)
        mx, mz = cx + ri * math.cos(t), cz + ri * math.sin(t)
        a('AttributeBegin Translate %s 0 %s Rotate %s 0 1 0 ObjectInstance "rackbar" AttributeEnd\n'
          % (fmt(mx), fmt(mz), fmt(-(ang + 90))))

    # ---------------- glass of water
    a("\n# ---------------------------------------------------------------- glass of water (OBJ lathe meshes)\n")
    a('AttributeBegin\n  Translate 2.2 0 -0.8 Scale 1.35 1.35 1.35\n'
      '  AttributeBegin Material "dielectric" "float eta" [ 1.5 ] Shape "objmesh" "string filename" "meshes/glass.obj" AttributeEnd\n'
      '  AttributeBegin Material "dielectric" "float eta" [ 1.33 ] Shape "objmesh" "string filename" "meshes/water.obj" AttributeEnd\n'
      'AttributeEnd\n')

    # ---------------- perfume bottle
    a("\n# ---------------------------------------------------------------- perfume bottle: crystal cap, glass body, amber liquid, label\n")
    a('AttributeBegin\n  Translate -4.6 0 -3.0 Rotate 22 0 1 0 Scale 0.72 0.72 0.72\n')
    a('  AttributeBegin\n    Material "dielectric" "float eta" [ 1.5 ]\n    ' + box((-1.8, 0, -1.8), (1.8, 3.7, 1.8)).replace("\n", "\n    ").rstrip() + "\n  AttributeEnd\n")
    a('  AttributeBegin\n    Material "dielectric" "float eta" [ 1.4 ] "rgb Kt" [ 0.62 0.48 0.12 ]\n    ' + box((-1.45, 0.35, -1.45), (1.45, 3.2, 1.45)).replace("\n", "\n    ").rstrip() + "\n  AttributeEnd\n")
    a('  AttributeBegin\n    Material "blinnphong" "rgb Kd" [ 0.45 0.36 0.15 ] "rgb Ks" [ 0.3 0.27 0.18 ] "float shininess" [ 80 ] "rgb Kr" [ 0.2 0.17 0.07 ] "rgb Ka" [ 0.1 0.1 0.1 ]\n'
      '    ' + box((-1.2, 3.7, -1.2), (1.2, 4.0, 1.2)).replace("\n", "\n    ").rstrip() + "\n  AttributeEnd\n")
    a('  AttributeBegin\n    Material "dielectric" "float eta" [ 1.55 ]\n    ' + box((-1.9, 4.0, -1.9), (1.9, 6.3, 1.9)).replace("\n", "\n    ").rstrip() + "\n  AttributeEnd\n")
    a('  AttributeBegin\n    Material "blinnphong" "texture Kd" "label" "rgb Ks" [ 0.1 0.1 0.1 ] "float shininess" [ 30 ] "rgb Ka" [ 0.1 0.1 0.1 ]\n'
      '    ' + quad((-1.0, 0.8, -1.82), (1.0, 0.8, -1.82), (1.0, 2.3, -1.82), (-1.0, 2.3, -1.82)).replace("\n", "\n    ").rstrip() + "\n  AttributeEnd\n")
    a("AttributeEnd\n")

    # ---------------- grater
    a("\n# ---------------------------------------------------------------- steel box grater (OBJ mesh, holes texture + mirror)\n")
    a('AttributeBegin\n  Translate -6.6 0 3.6 Rotate 28 0 1 0\n'
      '  Material "blinnphong" "texture Kd" "grater" "rgb Ks" [ 0.2 0.2 0.2 ] "float shininess" [ 120 ] "rgb Kr" [ 0.5 0.5 0.52 ] "rgb Ka" [ 0.08 0.08 0.08 ]\n'
      '  Shape "objmesh" "string filename" "meshes/grater.obj"\nAttributeEnd\n')

    # ---------------- cue
    a("\n# ---------------------------------------------------------------- cue (OBJ meshes) lying on the felt: tip far, butt near\n")
    a('AttributeBegin\n  Translate 1.5 0.32 19  Rotate 64.4 0 1 0  Rotate -90 0 0 1  Scale 1 1.9 1\n'
      '  AttributeBegin Material "blinnphong" "rgb Kd" [ 0.05 0.05 0.06 ] "rgb Ks" [ 0.3 0.3 0.3 ] "float shininess" [ 60 ] "rgb Ka" [ 0.05 0.05 0.05 ]\n'
      '    Shape "objmesh" "string filename" "meshes/cue_tip.obj" AttributeEnd\n'
      '  AttributeBegin Material "blinnphong" "texture Kd" "cuewood" "rgb Ks" [ 0.2 0.2 0.2 ] "float shininess" [ 60 ] "rgb Ka" [ 0.08 0.08 0.08 ]\n'
      '    Shape "objmesh" "string filename" "meshes/cue_shaft.obj" AttributeEnd\n'
      'AttributeEnd\n')
    os.makedirs(INC, exist_ok=True)
    with open(os.path.join(INC, "poolroom_world.pbrt"), "w") as f:
        f.write("".join(W))
    print("wrote scenes/include/poolroom_world.pbrt")


def main():
    felt_texture()
    cueball_texture()
    grater_texture()
    label_texture()
    railblack_texture()
    write_obj("glass.obj", fix_winding(lathe(glass_profile(), 64)), "thick-walled glass tumbler")
    write_obj("water.obj", fix_winding(lathe(water_profile(), 64)), "water inside the tumbler")
    tip, shaft = cue_profiles()
    write_obj("cue_tip.obj", fix_winding(lathe(tip, 32)), "cue tip and ferrule")
    write_obj("cue_shaft.obj", fix_winding(lathe(shaft, 32)), "cue shaft")
    write_obj("grater.obj", grater_mesh(), "tapered box grater with handle")
    world_include()


if __name__ == "__main__":
    main()
