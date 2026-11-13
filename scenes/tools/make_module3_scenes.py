#!/usr/bin/env python3
"""Scene files for Module 3, 2.3.1 (Python 3 standard library only, deterministic).

  scenes/acc_best.pbrt      best case for the BVH ("Phyllotaxis"): 25,000 marbles on a golden-angle
                            spiral around a 120k-triangle torus knot (WSRT, 1920x1080)
  scenes/acc_worst.pbrt     worst case ("Firework"): 4,000 long straws that all cross the same small
                            region (WSRT, 1920x1080)
  scenes/acc_complex.pbrt   a library reading room at dusk: hundreds of objects, eleven area lights
                            (DRT, 1920x1280)
  scenes/include/m3_*.pbrt  the worlds of these scenes
  scenes/meshes/m3_*.ply    generated meshes (binary little-endian PLY with normals and uvs)
  scenes/textures/m3_*.ppm  generated textures (rug, globe)
  scenes/module3/acc/*.pbrt the extra scenes of the timing study (small primitive counts, sweeps)

The three output scenes use the renderer's blinnphong material; every primitive and the
Accelerator directive are standard pbrt-v4 syntax.
"""
import colorsys
import math
import os
import random
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_poolroom as mp  # noqa: E402  (fmt, box, quad)

SCENES = os.path.join(HERE, "..")
INC = os.path.join(SCENES, "include")
MESH = os.path.join(SCENES, "meshes")
M3 = os.path.join(SCENES, "module3", "acc")
fmt = mp.fmt


def vec(v):
    return " ".join(fmt(c) for c in v)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        with open(path) as f:
            if f.read() == text:
                return
    with open(path, "w") as f:
        f.write(text)
    print("wrote", os.path.relpath(path, SCENES))


def write_ply(name, verts, norms, uvs, faces, comment):
    """Binary little-endian PLY (x y z nx ny nz u v, uchar/int faces), as read by pbrt-v4."""
    head = ("ply\nformat binary_little_endian 1.0\ncomment %s\nelement vertex %d\n"
            "property float x\nproperty float y\nproperty float z\n"
            "property float nx\nproperty float ny\nproperty float nz\n"
            "property float u\nproperty float v\n"
            "element face %d\nproperty list uchar int vertex_indices\nend_header\n") % (comment, len(verts), len(faces))
    body = bytearray()
    for p, n, t in zip(verts, norms, uvs):
        body += struct.pack("<8f", p[0], p[1], p[2], n[0], n[1], n[2], t[0], t[1])
    for f in faces:
        body += struct.pack("<B3i", 3, f[0], f[1], f[2])
    data = head.encode() + bytes(body)
    path = os.path.join(MESH, name)
    os.makedirs(MESH, exist_ok=True)
    if not (os.path.exists(path) and open(path, "rb").read() == data):
        with open(path, "wb") as f:
            f.write(data)
        print("wrote scenes/meshes/%s (%d triangles)" % (name, len(faces)))


def add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a):
    l = math.sqrt(dot(a, a))
    return mul(a, 1 / l)


# ---------------------------------------------------------------- torus knot tube
def torus_knot(p, q, R, r_knot, tube, n_seg, n_side):
    """Tube of radius `tube` around the (p, q) torus knot; rotation-minimising frames."""
    def curve(t):
        phi = t * 2 * math.pi
        rr = R + r_knot * math.cos(q * phi)
        return (rr * math.cos(p * phi), r_knot * math.sin(q * phi), rr * math.sin(p * phi))
    pts = [curve(i / n_seg) for i in range(n_seg)]
    tang = [norm(sub(pts[(i + 1) % n_seg], pts[i - 1])) for i in range(n_seg)]
    # Parallel transport of a normal along the closed curve, then spread the closing twist.
    n0 = norm(cross(tang[0], (0, 1, 0)))
    frames = [n0]
    for i in range(1, n_seg):
        n = frames[-1]
        n = norm(sub(n, mul(tang[i], dot(n, tang[i]))))
        frames.append(n)
    nEnd = norm(sub(frames[-1], mul(tang[0], dot(frames[-1], tang[0]))))
    twist = math.atan2(dot(cross(nEnd, n0), tang[0]), dot(nEnd, n0))
    verts, norms, uvs, faces = [], [], [], []
    for i in range(n_seg + 1):
        k = i % n_seg
        t, n = tang[k], frames[k]
        a = twist * i / n_seg
        n = add(mul(n, math.cos(a)), mul(cross(t, n), math.sin(a)))
        b = cross(t, n)
        for j in range(n_side + 1):
            th = 2 * math.pi * j / n_side
            d = add(mul(n, math.cos(th)), mul(b, math.sin(th)))
            verts.append(add(pts[k], mul(d, tube)))
            norms.append(d)
            uvs.append((i / n_seg * 40, j / n_side))
    w = n_side + 1
    for i in range(n_seg):
        for j in range(n_side):
            a, b2, c, d = i * w + j, (i + 1) * w + j, (i + 1) * w + j + 1, i * w + j + 1
            faces.append((a, c, b2))
            faces.append((a, d, c))
    # Orient faces with the vertex normals.
    out = []
    for f in faces:
        gn = cross(sub(verts[f[1]], verts[f[0]]), sub(verts[f[2]], verts[f[0]]))
        out.append(f if dot(gn, norms[f[0]]) > 0 else (f[0], f[2], f[1]))
    return verts, norms, uvs, out


# ---------------------------------------------------------------- materials and textures
def hsv(h, s, v):
    return colorsys.hsv_to_rgb(h % 1.0, s, v)


def blinn(name, kd, ks=0.0, shininess=32, kr=0.0, ka=1.0, tex=None):
    """MakeNamedMaterial line for the renderer's blinnphong material (kd + ks + kr <= 1 per channel)."""
    one = lambda c: c if isinstance(c, (tuple, list)) else (c, c, c)  # noqa: E731
    s = 'MakeNamedMaterial "%s" "string type" "blinnphong" ' % name
    s += ('"texture Kd" "%s"' % tex) if tex else '"rgb Kd" [ %s ]' % vec(one(kd))
    s += ' "rgb Ka" [ %s ]' % vec(one(ka))
    if ks:
        s += ' "rgb Ks" [ %s ] "float shininess" [ %s ]' % (vec(one(ks)), fmt(shininess))
    if kr:
        s += ' "rgb Kr" [ %s ]' % vec(one(kr))
    return s + "\n"


def rug_texture(name="m3_rug.ppm", W=240, H=360):
    """A woven rug: madder-red field with a lattice of small motifs, a navy border with gold
    lines and a central lozenge medallion (procedural, deterministic)."""
    red, deep, navy, gold, cream = (128, 26, 28), (86, 14, 20), (24, 30, 66), (196, 150, 70), (214, 196, 160)
    px = []
    for y in range(H):
        for x in range(W):
            u, v = (x + 0.5) / W, (y + 0.5) / H
            e = min(u, 1 - u, v * H / W, (1 - v) * H / W)  # distance to the edge in units of the width
            c = red
            if e < 0.012:
                c = deep
            elif e < 0.1:
                c = navy
                if 0.03 < e < 0.04 or 0.075 < e < 0.085:
                    c = gold
                elif 0.045 < e < 0.07 and (int(u * 40) + int(v * 60)) % 2 == 0:
                    c = (150, 34, 34)
            else:
                du, dv = abs(u - 0.5) / 0.32, abs(v - 0.5) * H / W / 0.32
                d = du + dv
                if d < 1:
                    c = navy if d > 0.8 else (gold if d > 0.74 else (deep if d > 0.4 else (gold if d > 0.33 else cream if d < 0.12 else navy)))
                else:
                    gu, gv = (u * 9) % 1, (v * 13.5) % 1
                    m = abs(gu - 0.5) + abs(gv - 0.5)
                    if m < 0.12:
                        c = gold
                    elif 0.2 < m < 0.26:
                        c = deep
            # A little weave noise so the rug does not look printed.
            n = 1 + 0.07 * math.sin(x * 2.3 + y * 0.7) * math.sin(y * 1.9)
            px.append(tuple(ch * n for ch in c))
    mp.write_ppm(name, W, H, px)


def globe_texture(name="m3_globe.ppm", W=256, H=128):
    """Antique globe: parchment continents on a teal sea (random smooth blobs), with graticule lines."""
    rnd = random.Random(7)
    waves = [(rnd.uniform(1, 5), rnd.uniform(1, 4), rnd.uniform(0, 6.3), rnd.uniform(0, 6.3), rnd.uniform(0.5, 1))
             for _ in range(9)]
    px = []
    for y in range(H):
        for x in range(W):
            lon, lat = (x + 0.5) / W * 2 * math.pi, ((y + 0.5) / H - 0.5) * math.pi
            f = sum(a * math.sin(fu * lon + pu) * math.cos(fv * lat + pv) for fu, fv, pu, pv, a in waves) / 3.2
            land = f > 0.18
            c = (196, 170, 118) if land else (46, 92, 98)
            if land and f < 0.24:
                c = (120, 96, 60)
            if (x % (W // 12) == 0) or (y % (H // 6) == 0):
                c = tuple(int(ch * 0.7) for ch in c)
            px.append(c)
    mp.write_ppm(name, W, H, px)


# ---------------------------------------------------------------- acc_best
ARMS = 55  # a Fibonacci number: marbles i, i+55, i+110, ... lie on one spiral arm (about 3.7 turns)


def best_world(n_marbles=25000, seed=3, knot=True, path=None):
    """Phyllotaxis: marbles on a sunflower (golden-angle) spiral, coloured by spiral arm, around a
    polished gold torus knot standing in a black mirror pool. Many small, well separated
    primitives (and a dense mesh): the best case for a BVH."""
    rnd = random.Random(seed)
    if knot:
        verts, norms, uvs, faces = torus_knot(2, 3, 2.0, 0.85, 0.42, 1500, 40)
        write_ply("m3_torusknot.ply", verts, norms, uvs, faces, "(2,3) torus knot tube, make_module3_scenes.py")
    else:
        faces = []
    L = ["# Generated by scenes/tools/make_module3_scenes.py\n",
         ("# Best case for the BVH: %d marbles on a golden-angle spiral and a %d-triangle torus knot.\n" % (n_marbles, len(faces))
          if knot else "# Scaling study: %d marbles on the floor of acc_best (no knot).\n" % n_marbles),
         "WorldBegin\n",
         # warm key spot on the knot (its soft cone edge darkens the rim of the disc), cool back light, faint fill
         'LightSource "spot" "point3 from" [ -7 13 -9 ] "point3 to" [ 0 1.5 0 ] "float coneangle" [ 46 ]\n'
         '    "float conedeltaangle" [ 22 ] "rgb I" [ 250 228 195 ]\n',
         'LightSource "point" "point3 from" [ 5 9 14 ] "rgb I" [ 50 66 120 ]\n',
         'LightSource "distant" "point3 from" [ 6 8 -4 ] "point3 to" [ 0 0 0 ] "rgb L" [ 0.1 0.12 0.18 ]\n',
         blinn("floor", (0.035, 0.035, 0.04), ks=0.2, shininess=120, kr=0.15),
         blinn("pool", 0.01, ks=0.2, shininess=600, kr=0.75),
         blinn("brass", (0.3, 0.22, 0.08), ks=(0.35, 0.3, 0.22), shininess=200, kr=(0.35, 0.3, 0.2)),
         blinn("knot", (0.3, 0.2, 0.05), ks=(0.35, 0.3, 0.25), shininess=300, kr=(0.35, 0.27, 0.1))]
    # Arm j starts at angle j * golden; ordering the arms by that angle gives them neighbouring hues.
    golden = math.pi * (3 - math.sqrt(5))
    order = sorted(range(ARMS), key=lambda j: (j * golden) % (2 * math.pi))
    hue_of = {j: rank / ARMS for rank, j in enumerate(order)}
    for j in range(ARMS):
        kd = tuple(0.72 * c for c in hsv(hue_of[j] + 0.02, 0.78, 1.0))
        L.append(blinn("marble%d" % j, kd, ks=0.24, shininess=220, kr=0.04))
    L.append('NamedMaterial "floor"\n')
    L.append(mp.quad((-80, 0, -80), (80, 0, -80), (80, 0, 80), (-80, 0, 80)))
    R0, R1, POOL = 4.05, 15.0, 3.75
    L.append('AttributeBegin\nTranslate 0 0.003 0\nRotate -90 1 0 0\nNamedMaterial "pool"\n'
             'Shape "disk" "float radius" [ %s ]\nNamedMaterial "brass"\n'
             'Shape "disk" "float radius" [ 3.92 ] "float innerradius" [ %s ] "float height" [ 0.001 ]\nAttributeEnd\n'
             % (fmt(POOL), fmt(POOL)))
    if knot:
        L.append('AttributeBegin\nNamedMaterial "knot"\nTranslate 0 3.45 0\nRotate 75 1 0 0\n'
                 'Shape "plymesh" "string filename" [ "meshes/m3_torusknot.ply" ]\nAttributeEnd\n')
    # Sunflower spiral with uniform density over the ring R0 < r < R1 (spacing ~0.175, radius ~0.074).
    groups = [[] for _ in range(ARMS)]
    for i in range(n_marbles):
        rad = math.sqrt(R0 * R0 + (R1 * R1 - R0 * R0) * (i + 0.5) / n_marbles)
        a = i * golden
        r = 0.074 * (1 + 0.1 * (rnd.random() - 0.5))
        groups[i % ARMS].append((rad * math.cos(a), r, rad * math.sin(a)))
    for k, g in enumerate(groups):
        L.append('NamedMaterial "marble%d"\n' % k)
        for x, r, z in g:
            L.append('AttributeBegin Translate %s %s %s Shape "sphere" "float radius" [ %s ] AttributeEnd\n'
                     % (fmt(x), fmt(r), fmt(z), fmt(r)))
    write(path or os.path.join(INC, "m3_best.pbrt"), "".join(L))
    return n_marbles + len(faces) + 4


# ---------------------------------------------------------------- acc_worst
STRAW_GROUPS = 12


def worst_world(n_straws=4000, seed=5, name="m3_worst.pbrt", note=""):
    """Firework: long thin straws through one small region. Every straw's bounding box covers most
    of the burst, so no split separates them and rays must visit almost every leaf. The straws are
    coloured by direction (12 meshes); a point light at the centre makes the core glow."""
    rnd = random.Random(seed)
    groups = [([], []) for _ in range(STRAW_GROUPS)]
    n_tris = 0
    for s in range(n_straws):
        # Random direction (uniform on the sphere, flattened a little), random centre near 0.
        z = rnd.uniform(-1, 1)
        ph = rnd.uniform(0, 2 * math.pi)
        rr = math.sqrt(1 - z * z)
        d = norm((rr * math.cos(ph), 0.55 * z, rr * math.sin(ph)))
        c = (rnd.uniform(-0.25, 0.25), 2.4 + rnd.uniform(-0.25, 0.25), rnd.uniform(-0.25, 0.25))
        half = rnd.uniform(2.2, 2.8)
        side = norm(cross(d, (0.3, 1, 0.2)))
        w = 0.012
        a = add(c, mul(d, -half))
        b = add(c, mul(d, half))
        # Colour by the straw's direction in the image plane (x, y): a rainbow pinwheel.
        g = int(((math.atan2(d[1], d[0]) / math.pi) % 1.0) * STRAW_GROUPS) % STRAW_GROUPS
        P, I = groups[g]
        base = len(P)
        P += [add(a, mul(side, -w)), add(a, mul(side, w)), add(b, mul(side, w)), add(b, mul(side, -w))]
        I += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
        n_tris += 2
    L = ["# Generated by scenes/tools/make_module3_scenes.py\n",
         "# Worst case for the BVH: %d long straws (%d triangles) crossing one small region%s.\n" % (n_straws, n_tris, note),
         "WorldBegin\n",
         'LightSource "point" "point3 from" [ 0 2.4 0 ] "rgb I" [ 24 21 16 ]\n',
         'LightSource "point" "point3 from" [ -5 7 -7 ] "rgb I" [ 230 230 250 ]\n',
         'LightSource "point" "point3 from" [ 6 3 -6 ] "rgb I" [ 170 130 110 ]\n',
         'LightSource "point" "point3 from" [ 5 6 6 ] "rgb I" [ 160 100 220 ]\n',
         blinn("floor", 0.03, ks=0.2, shininess=150, kr=0.35)]
    for k in range(STRAW_GROUPS):
        kd = tuple(0.62 * c for c in hsv((k + 0.5) / STRAW_GROUPS, 0.8, 1.0))
        L.append(blinn("straw%d" % k, kd, ks=0.35, shininess=90))
    L += ['NamedMaterial "floor"\n', mp.quad((-40, 0, -40), (40, 0, -40), (40, 0, 40), (-40, 0, 40))]
    for k, (P, I) in enumerate(groups):
        if not I:
            continue
        L += ['NamedMaterial "straw%d"\n' % k,
              'Shape "trianglemesh" "point3 P" [ ' + "  ".join(vec(p) for p in P) + " ]\n",
              '    "integer indices" [ ' + " ".join("%d %d %d" % f for f in I) + " ]\n"]
    write(name if os.path.isabs(name) else os.path.join(INC, name), "".join(L))
    return n_tris + 2


# ---------------------------------------------------------------- acc_complex
def herringbone(x0, x1, z0, z1, L=0.6, w=0.1, gap=0.003):
    """Planks of a 45-degree herringbone parquet covering [x0,x1] x [z0,z1] (as world quads at y=0).
    In plank coordinates (u, v) a staircase of alternating horizontal/vertical L x w planks is
    repeated by (L, -L), which tiles the plane exactly."""
    s = 1 / math.sqrt(2)
    us = [(x + z) * s for x in (x0, x1) for z in (z0, z1)]
    vs = [(z - x) * s for x in (x0, x1) for z in (z0, z1)]
    kmin, kmax = int(math.floor((min(us) + min(vs)) / (2 * w))) - 8, int(math.ceil((max(us) + max(vs)) / (2 * w))) + 8
    jmin, jmax = int(math.floor((min(us) - max(vs)) / (2 * L))) - 2, int(math.ceil((max(us) - min(vs)) / (2 * L))) + 2
    out = []
    for j in range(jmin, jmax + 1):
        for k in range(kmin, kmax + 1):
            u0, v0 = k * w + j * L, k * w - j * L
            for (ua, ub, va, vb) in ((u0, u0 + L, v0, v0 + w), (u0 + L, u0 + L + w, v0 + w - L, v0 + w)):
                corners = [((u - v) * s, (u + v) * s) for u, v in
                           ((ua + gap, va + gap), (ub - gap, va + gap), (ub - gap, vb - gap), (ua + gap, vb - gap))]
                if max(c[0] for c in corners) < x0 or min(c[0] for c in corners) > x1 or \
                   max(c[1] for c in corners) < z0 or min(c[1] for c in corners) > z1:
                    continue
                out.append(corners)
    return out


def complex_world(seed=11):
    """Evening reading room of a library: herringbone parquet, bookcases with ~1,300 books,
    reading tables with green banker's lamps, pendant lights, three tall windows at dusk."""
    rnd = random.Random(seed)
    rug_texture()
    globe_texture()
    W, D, H = 10.0, 12.0, 5.0  # room: x in [-W, W], z in [-2, D], y in [0, H]
    L = ["# Generated by scenes/tools/make_module3_scenes.py\n",
         "# Library reading room at dusk: hundreds of objects, eleven area lights (DRT).\n",
         "WorldBegin\n",
         'Texture "rug" "spectrum" "imagemap" "string filename" [ "textures/m3_rug.ppm" ]\n',
         'Texture "globe" "spectrum" "imagemap" "string filename" [ "textures/m3_globe.ppm" ]\n',
         blinn("gap", (0.04, 0.025, 0.015), ka=0),
         blinn("wallpaper", (0.2, 0.3, 0.22), ka=0),
         blinn("ceiling", (0.72, 0.68, 0.6), ka=0),
         blinn("walnut", (0.22, 0.12, 0.06), ks=0.1, shininess=50, ka=0),
         blinn("paint", (0.7, 0.68, 0.62), ks=0.05, shininess=30, ka=0),
         blinn("shelf", (0.28, 0.15, 0.07), ks=0.08, shininess=30, ka=0),
         blinn("table", (0.36, 0.19, 0.08), ks=0.15, shininess=90, kr=0.05, ka=0),
         blinn("leather", (0.3, 0.06, 0.04), ks=0.15, shininess=30, ka=0),
         blinn("brass", (0.32, 0.23, 0.08), ks=(0.45, 0.38, 0.22), shininess=120, ka=0),
         blinn("shade", (0.03, 0.26, 0.1), ks=0.35, shininess=200, ka=0),
         blinn("rug", 0, tex="rug", ka=0),
         blinn("globe", 0, tex="globe", ks=0.2, shininess=80, ka=0)]
    tones = [(0.42, 0.24, 0.11), (0.36, 0.2, 0.09), (0.48, 0.29, 0.14), (0.31, 0.17, 0.08), (0.4, 0.22, 0.09)]
    for i, c in enumerate(tones):
        L.append(blinn("parquet%d" % i, c, ks=0.1, shininess=80, kr=0.04, ka=0))
    book_cols = [(0.45, 0.06, 0.06), (0.08, 0.14, 0.35), (0.08, 0.26, 0.13), (0.55, 0.38, 0.12), (0.28, 0.08, 0.26),
                 (0.07, 0.07, 0.08), (0.62, 0.56, 0.44), (0.42, 0.18, 0.07), (0.12, 0.3, 0.34), (0.55, 0.2, 0.14),
                 (0.2, 0.12, 0.06), (0.5, 0.45, 0.2)]
    for i, c in enumerate(book_cols):
        L.append(blinn("book%d" % i, c, ks=0.08, shininess=25, ka=0))

    # Floor: herringbone parquet (one mesh per wood tone) over a dark base that shows in the joints.
    L.append('NamedMaterial "gap"\n' + mp.quad((-W, -0.002, -2), (W, -0.002, -2), (W, -0.002, D), (-W, -0.002, D)))
    planks = [[] for _ in tones]
    for q in herringbone(-W, W, -2, D):
        planks[rnd.randrange(len(tones))].append(q)
    for i, qs in enumerate(planks):
        P = [(x, 0, z) for q in qs for x, z in q]
        I = [(4 * n, 4 * n + 1, 4 * n + 2, 4 * n, 4 * n + 2, 4 * n + 3) for n in range(len(qs))]
        L.append('NamedMaterial "parquet%d"\nShape "trianglemesh" "point3 P" [ %s ]\n    "integer indices" [ %s ]\n'
                 % (i, "  ".join(vec(p) for p in P), " ".join("%d %d %d %d %d %d" % t for t in I)))
    n_planks = sum(len(p) for p in planks)

    # Ceiling with walnut beams; walls: wallpaper above a walnut wainscot with a chair rail.
    L.append('NamedMaterial "ceiling"\n' + mp.quad((-W, H, D), (W, H, D), (W, H, -2), (-W, H, -2)))
    L.append('NamedMaterial "walnut"\n')
    for x in (-7.5, -2.5, 2.5, 7.5):
        L.append(mp.box((x - 0.16, H - 0.34, -2), (x + 0.16, H, D)))
    L.append('NamedMaterial "wallpaper"\n')
    L.append(mp.quad((-W, 0, D), (-W, H, D), (W, H, D), (W, 0, D)))      # back wall
    L.append(mp.quad((W, 0, -2), (W, H, -2), (W, H, D), (W, 0, D)))      # right wall
    L.append(mp.quad((-W, 0, -2), (W, 0, -2), (W, H, -2), (-W, H, -2)))  # wall behind the camera
    # Left wall with three tall windows (y 1.1..4.1): panels around the openings.
    WY0, WY1 = 1.1, 4.1
    windows = [(0.2, 2.8), (4.1, 6.7), (8.0, 10.6)]
    L.append(mp.quad((-W, 0, -2), (-W, WY0, -2), (-W, WY0, D), (-W, 0, D)))
    L.append(mp.quad((-W, WY1, -2), (-W, H, -2), (-W, H, D), (-W, WY1, D)))
    edges = [-2.0] + [e for wz in windows for e in wz] + [D]
    for za, zb in zip(edges[0::2], edges[1::2]):
        L.append(mp.quad((-W, WY0, za), (-W, WY1, za), (-W, WY1, zb), (-W, WY0, zb)))
    L.append('NamedMaterial "walnut"\n')
    for lo, hi in (((-W, 0, D - 0.04), (W, 1.0, D)), ((W - 0.04, 0, -2), (W, 1.0, D)),
                   ((-W, 0, -2), (-W + 0.04, 1.0, D)), ((-W, 0, -2), (W, 1.0, -1.96))):
        L.append(mp.box(lo, hi))
    for lo, hi in (((-W, 1.0, D - 0.07), (W, 1.06, D)), ((W - 0.07, 1.0, -2), (W, 1.06, D)),
                   ((-W, 1.0, -2), (-W + 0.07, 1.06, D)), ((-W, 1.0, -2), (W, 1.06, -1.93))):
        L.append(mp.box(lo, hi))
    # Window reveals (wall thickness 0.35), sills, glazing bars and the dusk sky behind each opening.
    T = 0.35
    for za, zb in windows:
        L.append('NamedMaterial "paint"\n')
        L.append(mp.quad((-W - T, WY0, za), (-W, WY0, za), (-W, WY1, za), (-W - T, WY1, za)))
        L.append(mp.quad((-W, WY0, zb), (-W - T, WY0, zb), (-W - T, WY1, zb), (-W, WY1, zb)))
        L.append(mp.quad((-W - T, WY1, za), (-W, WY1, za), (-W, WY1, zb), (-W - T, WY1, zb)))
        L.append(mp.box((-W - T, WY0 - 0.06, za - 0.08), (-W + 0.1, WY0, zb + 0.08)))  # sill
        zc = (za + zb) / 2
        L.append(mp.box((-W - 0.2, WY0, zc - 0.03), (-W - 0.14, WY1, zc + 0.03)))
        for y in (WY0 + 0.75, WY0 + 1.5, WY0 + 2.25):
            L.append(mp.box((-W - 0.2, y - 0.025, za), (-W - 0.14, y + 0.025, zb)))
        # The sky is 1 m behind the opening and larger than it: no surface comes close to the
        # emitter (uniform area sampling of a light right next to a surface gives fireflies).
        X, M = -W - T - 1.0, 1.4
        L.append('AttributeBegin\nAreaLightSource "diffuse" "rgb L" [ 2.2 2.8 4.6 ]\n' +
                 mp.quad((X, WY0 - M, zb + M), (X, WY0 - M, za - M), (X, WY1 + M, za - M), (X, WY1 + M, zb + M)) +
                 'AttributeEnd\n')

    def bookcase(x0, x1, z0, z1, along_x):
        """Bookcase occupying [x0,x1] x [z0,z1]; books stand along x (back wall) or along z
        (right wall, back panel at x1)."""
        out = ['NamedMaterial "shelf"\n']
        top = 4.2
        if along_x:
            out.append(mp.box((x0, 0, z1 - 0.05), (x1, top, z1)))
            out.append(mp.box((x0, 0, z0), (x0 + 0.06, top, z1)))
            out.append(mp.box((x1 - 0.06, 0, z0), (x1, top, z1)))
            out.append(mp.box((x0 - 0.05, top, z0 - 0.06), (x1 + 0.05, top + 0.14, z1)))  # cornice
        else:
            out.append(mp.box((x1 - 0.05, 0, z0), (x1, top, z1)))
            out.append(mp.box((x0, 0, z0), (x1, top, z0 + 0.06)))
            out.append(mp.box((x0, 0, z1 - 0.06), (x1, top, z1)))
            out.append(mp.box((x0 - 0.06, top, z0 - 0.05), (x1, top + 0.14, z1 + 0.05)))
        levels = [0.15, 0.95, 1.75, 2.55, 3.35, 4.15]
        for y in levels:
            out.append(mp.box((x0, y - 0.05, z0), (x1, y, z1)))
        for y in levels[:-1]:
            pos = (x0 if along_x else z0) + 0.08
            end = (x1 if along_x else z1) - 0.08
            while True:
                th = rnd.uniform(0.04, 0.11)
                if pos + th > end:
                    break
                ht = rnd.uniform(0.45, 0.72)
                dp = rnd.uniform(0.32, 0.42)
                out.append('NamedMaterial "book%d"\n' % rnd.randrange(len(book_cols)))
                if along_x:
                    out.append(mp.box((pos, y, z1 - 0.06 - dp), (pos + th, y + ht, z1 - 0.06)))
                else:
                    out.append(mp.box((x1 - 0.06 - dp, y, pos), (x1 - 0.06, y + ht, pos + th)))
                pos += th + (0.004 if rnd.random() < 0.9 else rnd.uniform(0.05, 0.25))
        return "".join(out)

    for x0 in (-9.6, -5.6, -1.6, 2.4, 6.4):  # five bookcases along the back wall
        L.append(bookcase(x0, x0 + 3.6, D - 0.5, D, True))
    for z0 in (2.0, 6.5):  # two along the right wall
        L.append(bookcase(W - 0.5, W, z0, z0 + 3.6, False))
    # Brass library rail along the back bookcases and a rolling ladder leaning on it.
    L.append('NamedMaterial "brass"\n' + mp.box((-9.6, 3.95, D - 0.62), (10.0, 3.99, D - 0.58)))
    lean = math.degrees(math.atan2(0.8, 4.0))
    lad = ['NamedMaterial "walnut"\n']
    for x in (-0.28, 0.24):
        lad.append(mp.box((x, 0, -0.03), (x + 0.04, 4.1, 0.03)))
    for k in range(11):
        y = 0.3 + 0.36 * k
        lad.append(mp.box((-0.26, y, -0.04), (0.26, y + 0.03, 0.04)))
    L.append('AttributeBegin\nTranslate 0.9 0 %s\nRotate %s 1 0 0\n%sAttributeEnd\n'
             % (fmt(D - 0.6 - 4.1 * math.sin(math.radians(lean))), fmt(lean), "".join(lad)))

    def table(cx, cz):
        out = ['NamedMaterial "table"\n', mp.box((cx - 1.6, 0.92, cz - 0.7), (cx + 1.6, 1.0, cz + 0.7))]
        for dx in (-1.45, 1.45):
            for dz in (-0.55, 0.55):
                out.append(mp.box((cx + dx - 0.05, 0, cz + dz - 0.05), (cx + dx + 0.05, 0.92, cz + dz + 0.05)))
        out.append(mp.box((cx - 1.4, 0.82, cz - 0.6), (cx + 1.4, 0.92, cz - 0.56)))  # aprons
        out.append(mp.box((cx - 1.4, 0.82, cz + 0.56), (cx + 1.4, 0.92, cz + 0.6)))
        out.append('NamedMaterial "leather"\n')
        for dx in (-0.8, 0.8):
            for side in (-1, 1):
                z = cz + side * 1.05
                out.append(mp.box((cx + dx - 0.25, 0.44, z - 0.25), (cx + dx + 0.25, 0.54, z + 0.25)))
                out.append(mp.box((cx + dx - 0.25, 0.54, z + side * 0.18), (cx + dx + 0.25, 1.15, z + side * 0.25)))
                for lx in (-0.22, 0.22):
                    for lz in (-0.22, 0.22):
                        out.append(mp.box((cx + dx + lx - 0.025, 0, z + lz - 0.025), (cx + dx + lx + 0.025, 0.44, z + lz + 0.025)))
        # Banker's lamp: brass base and stem, green half-dome shade, bulb (area light) under the shade.
        out.append('NamedMaterial "brass"\n')
        out.append(mp.box((cx - 0.13, 1.0, cz + 0.16), (cx + 0.13, 1.04, cz + 0.36)))
        out.append(mp.box((cx - 0.015, 1.04, cz + 0.25), (cx + 0.015, 1.64, cz + 0.28)))
        out.append(mp.box((cx - 0.015, 1.61, cz + 0.02), (cx + 0.015, 1.64, cz + 0.28)))
        out.append('AttributeBegin\nNamedMaterial "shade"\nTranslate %s 1.55 %s\nScale 1.7 0.55 0.75\nRotate -90 1 0 0\n'
                   'Shape "sphere" "float radius" [ 0.2 ] "float zmin" [ 0 ]\nAttributeEnd\n' % (fmt(cx), fmt(cz)))
        # A one-sided disk facing down: it lights the table, not the inside of its own shade.
        out.append('AttributeBegin\nAreaLightSource "diffuse" "rgb L" [ 24 17 9 ]\nTranslate %s 1.54 %s\n'
                   'Rotate 90 1 0 0\nShape "disk" "float radius" [ 0.13 ]\nAttributeEnd\n' % (fmt(cx), fmt(cz)))
        # Pendant light over the table: brass rod and an opal globe.
        out.append('NamedMaterial "brass"\n' + mp.box((cx - 0.015, 4.25, cz - 0.015), (cx + 0.015, H, cz + 0.015)))
        out.append('AttributeBegin\nAreaLightSource "diffuse" "rgb L" [ 7 5.8 4.3 ]\nTranslate %s 3.8 %s\n'
                   'Shape "sphere" "float radius" [ 0.2 ]\nAttributeEnd\n' % (fmt(cx), fmt(cz)))
        # Open books and stacks on the table top.
        for k in range(4):
            bx = cx + rnd.uniform(-1.3, 1.3)
            bz = cz + rnd.uniform(-0.5, 0.5)
            if abs(bx - cx) < 0.3 and bz > cz - 0.1:
                bx += 0.6
            h = 1.0
            for _ in range(rnd.randrange(1, 4)):
                t = rnd.uniform(0.03, 0.06)
                out.append('NamedMaterial "book%d"\n' % rnd.randrange(len(book_cols)))
                out.append(mp.box((bx - 0.14, h, bz - 0.2), (bx + 0.14, h + t, bz + 0.2)))
                h += t
        return "".join(out)

    # Rug under the reading tables.
    L.append('NamedMaterial "rug"\n' + mp.quad((-7.4, 0.008, 0.9), (4.9, 0.008, 0.9), (4.9, 0.008, 9.6), (-7.4, 0.008, 9.6)))
    for cx, cz in ((-4.5, 3.0), (2.0, 3.0), (-4.5, 7.5), (2.0, 7.5)):
        L.append(table(cx, cz))
    # Globe on a brass stand, and a leather armchair with a side table by the windows.
    L.append('NamedMaterial "brass"\n' + mp.box((6.3, 0, 8.9), (6.9, 0.05, 9.5)) + mp.box((6.57, 0.05, 9.17), (6.63, 1.0, 9.23)))
    L.append('AttributeBegin\nNamedMaterial "globe"\nTranslate 6.6 1.42 9.2\nRotate -23 0 0 1\nRotate -90 1 0 0\n'
             'Shape "sphere" "float radius" [ 0.42 ]\nAttributeEnd\n')
    L.append('NamedMaterial "brass"\nAttributeBegin\nTranslate 6.6 1.42 9.2\nRotate -23 0 0 1\n'
             'Shape "disk" "float radius" [ 0.5 ] "float innerradius" [ 0.46 ]\nAttributeEnd\n')
    chair = [mp.box((-0.45, 0.2, -0.45), (0.45, 0.5, 0.45)), mp.box((-0.45, 0.5, 0.3), (0.45, 1.2, 0.45)),
             mp.box((-0.55, 0.2, -0.45), (-0.45, 0.75, 0.45)), mp.box((0.45, 0.2, -0.45), (0.55, 0.75, 0.45))]
    for lx in (-0.5, 0.5):
        for lz in (-0.4, 0.4):
            chair.append(mp.box((lx - 0.03, 0, lz - 0.03), (lx + 0.03, 0.2, lz + 0.03)))
    L.append('AttributeBegin\nTranslate -8.6 0 5.4\nRotate 70 0 1 0\nNamedMaterial "leather"\n%sAttributeEnd\n'
             % "".join(chair))
    L.append('NamedMaterial "table"\n' + mp.box((-8.95, 0.6, 3.55), (-8.35, 0.64, 4.15)) +
             mp.box((-8.68, 0, 3.82), (-8.62, 0.6, 3.88)))
    h = 0.64
    for _ in range(3):
        t = rnd.uniform(0.04, 0.07)
        L.append('NamedMaterial "book%d"\n' % rnd.randrange(len(book_cols)) + mp.box((-8.8, h, 3.7), (-8.5, h + t, 4.0)))
        h += t
    text = "".join(L)
    write(os.path.join(INC, "m3_library.pbrt"), text)
    return text.count("Shape "), n_planks, text.count("AreaLightSource")


SCALE_MARBLES = [4, 16, 64, 256, 1024, 4096, 16384]
SCALE_STRAWS = [250, 500, 1000, 2000, 4000]
BEST_CAM = ("LookAt 0 9.5 -16.5   0 1.6 0.5   0 1 0\n"
            'Camera "perspective" "float fov" [ 34 ]\n')
WORST_CAM = ("LookAt 0 2.1 -9.4   0 2.35 0   0 1 0\n"
             'Camera "perspective" "float fov" [ 36 ]\n')
WHITTED = 'Integrator "whitted" "integer maxdepth" [ 5 ] "rgb ambient" [ 0.06 0.06 0.07 ]\n'


def sweep_scenes():
    """Scenes of the timing study: marble counts (best-case layout) and straw counts (worst case),
    rendered with the cameras of acc_best / acc_worst (module3_study.py sets resolution and spp)."""
    film = 'Film "rgb" "integer xresolution" [ 400 ] "integer yresolution" [ 225 ] "string filename" [ "%s.png" ]\n'
    common = 'Sampler "independent" "integer pixelsamples" [ 1 ]\n' + WHITTED
    for n in SCALE_MARBLES:
        name = "scale_marbles_%d" % n
        prims = best_world(n, knot=False, path=os.path.join(M3, "include", "marbles_%d.pbrt" % n))
        write(os.path.join(M3, name + ".pbrt"),
              "# Module 3 timing study: %d primitives (%d marbles + floor and pool), acc_best layout.\n" % (prims, n) +
              BEST_CAM + film % name + common + '\nInclude "include/marbles_%d.pbrt"\n' % n)
    for n in SCALE_STRAWS:
        name = "scale_straws_%d" % n
        prims = worst_world(n, name=os.path.join(M3, "include", "straws_%d.pbrt" % n))
        write(os.path.join(M3, name + ".pbrt"),
              "# Module 3 timing study: %d primitives (%d straws as triangles + floor), acc_worst layout.\n" % (prims, n) +
              WORST_CAM + film % name + common + '\nInclude "include/straws_%d.pbrt"\n' % n)


def main():
    nb = best_world()
    nw = worst_world()
    sweep_scenes()
    no, nplanks, nlights = complex_world()
    write(os.path.join(SCENES, "acc_best.pbrt"), (
          "# Module 3, 2.3.1 best case, \"Phyllotaxis\": %d primitives (25,000 marbles on a golden-angle spiral,\n"
          "# a 120,000-triangle torus knot), small and spread out, so a ray's path through the BVH only\n"
          "# reaches the few leaves near it. Timing: scenes/tools/module3_study.py (--accel bvh / objects / none).\n"
          + BEST_CAM +
          'Film "rgb" "integer xresolution" [ 1920 ] "integer yresolution" [ 1080 ]\n'
          '    "string filename" [ "acc_best.png" ]\n'
          'Sampler "stratified" "integer xsamples" [ 3 ] "integer ysamples" [ 3 ] "bool jitter" true\n'
          + WHITTED +
          'Accelerator "bvh" "string splitmethod" "sah" "integer maxnodeprims" [ 4 ]\n\n'
          'Include "include/m3_best.pbrt"\n') % nb)
    write(os.path.join(SCENES, "acc_worst.pbrt"), (
          "# Module 3, 2.3.1 worst case, \"Firework\": %d primitives, long thin straws that all cross one small\n"
          "# region. Every straw's bounding box spans most of the burst, so BVH nodes overlap and a ray has to\n"
          "# visit nearly every leaf.\n"
          + WORST_CAM +
          'Film "rgb" "integer xresolution" [ 1920 ] "integer yresolution" [ 1080 ]\n'
          '    "string filename" [ "acc_worst.png" ]\n'
          'Sampler "stratified" "integer xsamples" [ 4 ] "integer ysamples" [ 4 ] "bool jitter" true\n'
          + WHITTED +
          'Accelerator "bvh" "string splitmethod" "sah" "integer maxnodeprims" [ 4 ]\n\n'
          'Include "include/m3_worst.pbrt"\n') % nw)
    write(os.path.join(SCENES, "acc_complex.pbrt"),
          "# Module 3, 2.3.1 complex scene: a library reading room at dusk, %d objects (Shape directives;\n"
          "# about 1,300 books, the herringbone parquet of %d planks as 5 meshes) and %d area lights\n"
          "# (4 banker's lamps, 4 pendants, 3 windows), rendered with the DRT.\n"
          "LookAt 8.6 2.5 -1.5   -3.2 0.85 8.6   0 1 0\n"
          'Camera "perspective" "float fov" [ 52 ] "float lensradius" [ 0.02 ] "float focaldistance" [ 8.3 ]\n'
          'Film "rgb" "integer xresolution" [ 1920 ] "integer yresolution" [ 1280 ] "float exposure" [ 1.6 ]\n'
          '    "string filename" [ "acc_complex.png" ]\n'
          'Sampler "independent" "integer pixelsamples" [ 256 ]\n'
          'Integrator "distributed" "integer maxdepth" [ 3 ] "integer lightsamples" [ 1 ]\n'
          'Accelerator "bvh" "string splitmethod" "sah" "integer maxnodeprims" [ 4 ]\n\n'
          'Include "include/m3_library.pbrt"\n' % (no, nplanks, nlights))


if __name__ == "__main__":
    main()
